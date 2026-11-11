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
  applied_at timestamptz,
  updated_at timestamptz not null default now()
);

-- Compatible upgrade for databases created before candidate timestamps existed.
alter table public.job_state add column if not exists applied_at timestamptz;
update public.job_state set applied_at = updated_at where applied = true and applied_at is null;

alter table public.job_state enable row level security;

drop policy if exists "Alice Job Radar shared access" on public.job_state;
create policy "Alice Job Radar shared access"
on public.job_state
for all
to anon
using (true)
with check (true);

grant select, insert, update on public.job_state to anon;
