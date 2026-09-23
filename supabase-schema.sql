-- Alice Job Radar shared state
create table if not exists public.job_state (
  job_id text primary key,
  status text not null default 'Nuova',
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
create policy "Alice Job Radar shared access"
on public.job_state
for all
to anon
using (true)
with check (true);

grant select, insert, update on public.job_state to anon;
