-- Alice Job Radar shared state (secured)
-- The browser publishable key is public by design.
-- Access to job_state requires the high-entropy shared token already used by the Spesa PWA.
-- Never replace these policies with USING (true) / WITH CHECK (true).

create table if not exists public.job_state (
  job_id text primary key,
  status text not null default 'Nuova'
    check (status in ('Nuova','Interessante','Candidata','Colloquio','Scartata')),
  saved boolean not null default false,
  applied boolean not null default false,
  dismissed boolean not null default false,
  dismissed_at timestamptz,
  company text not null default '',
  title text not null default '',
  url text not null default '',
  updated_at timestamptz not null default now()
);

alter table public.job_state enable row level security;

drop policy if exists "Alice Job Radar shared access" on public.job_state;
drop policy if exists job_state_insert_shared on public.job_state;
drop policy if exists job_state_select_shared on public.job_state;
drop policy if exists job_state_update_shared on public.job_state;
drop policy if exists job_state_token_select on public.job_state;
drop policy if exists job_state_token_insert on public.job_state;
drop policy if exists job_state_token_update on public.job_state;

create policy job_state_token_select
on public.job_state
for select
to anon, authenticated
using (
  exists (
    select 1
    from shopping_private.lists l
    where l.access_token = (
      select nullif(current_setting('app.shopping_token', true), '')
    )
  )
);

create policy job_state_token_insert
on public.job_state
for insert
to anon, authenticated
with check (
  exists (
    select 1
    from shopping_private.lists l
    where l.access_token = (
      select nullif(current_setting('app.shopping_token', true), '')
    )
  )
);

create policy job_state_token_update
on public.job_state
for update
to anon, authenticated
using (
  exists (
    select 1
    from shopping_private.lists l
    where l.access_token = (
      select nullif(current_setting('app.shopping_token', true), '')
    )
  )
)
with check (
  exists (
    select 1
    from shopping_private.lists l
    where l.access_token = (
      select nullif(current_setting('app.shopping_token', true), '')
    )
  )
);

revoke delete on public.job_state from anon, authenticated;
grant select, insert, update on public.job_state to anon, authenticated;

create or replace function public.alice_get_state(p_token text)
returns table(
  job_id text,
  status text,
  saved boolean,
  applied boolean,
  dismissed boolean,
  dismissed_at timestamptz,
  company text,
  title text,
  url text,
  updated_at timestamptz
)
language plpgsql
set search_path to ''
as $function$
begin
  perform pg_catalog.set_config('app.shopping_token', coalesce(p_token,''), true);

  if not exists (
    select 1
    from shopping_private.lists l
    where l.access_token = p_token
  ) then
    raise insufficient_privilege using message = 'Token non valido';
  end if;

  return query
  select
    j.job_id, j.status, j.saved, j.applied, j.dismissed, j.dismissed_at,
    j.company, j.title, j.url, j.updated_at
  from public.job_state j
  order by j.updated_at desc;
end;
$function$;

create or replace function public.alice_upsert_state(p_token text, p_rows jsonb)
returns integer
language plpgsql
set search_path to ''
as $function$
declare
  r jsonb;
  v_job_id text;
  v_status text;
  v_count integer := 0;
begin
  perform pg_catalog.set_config('app.shopping_token', coalesce(p_token,''), true);

  if not exists (
    select 1
    from shopping_private.lists l
    where l.access_token = p_token
  ) then
    raise insufficient_privilege using message = 'Token non valido';
  end if;

  if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
    raise exception 'Payload non valido';
  end if;

  if jsonb_array_length(p_rows) > 500 then
    raise exception 'Troppi record';
  end if;

  for r in select value from jsonb_array_elements(p_rows)
  loop
    v_job_id := left(trim(coalesce(r->>'job_id','')), 300);
    v_status := coalesce(nullif(trim(coalesce(r->>'status','')), ''), 'Nuova');

    if v_job_id = '' then raise exception 'job_id non valido'; end if;
    if v_status not in ('Nuova','Interessante','Candidata','Colloquio','Scartata') then
      raise exception 'status non valido';
    end if;

    insert into public.job_state as j (
      job_id, status, saved, applied, dismissed, dismissed_at,
      company, title, url, updated_at
    )
    values (
      v_job_id,
      v_status,
      coalesce((r->>'saved')::boolean, false),
      coalesce((r->>'applied')::boolean, false),
      coalesce((r->>'dismissed')::boolean, false),
      case when nullif(r->>'dismissed_at','') is null
           then null else (r->>'dismissed_at')::timestamptz end,
      left(coalesce(r->>'company',''), 300),
      left(coalesce(r->>'title',''), 500),
      left(coalesce(r->>'url',''), 2000),
      now()
    )
    on conflict (job_id) do update set
      status = excluded.status,
      saved = excluded.saved,
      applied = excluded.applied,
      dismissed = excluded.dismissed,
      dismissed_at = excluded.dismissed_at,
      company = excluded.company,
      title = excluded.title,
      url = excluded.url,
      updated_at = now();

    v_count := v_count + 1;
  end loop;

  return v_count;
end;
$function$;

revoke all on function public.alice_get_state(text) from public;
revoke all on function public.alice_upsert_state(text, jsonb) from public;
grant execute on function public.alice_get_state(text) to anon, authenticated, service_role;
grant execute on function public.alice_upsert_state(text, jsonb) to anon, authenticated, service_role;
