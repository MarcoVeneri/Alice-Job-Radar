create extension if not exists pg_cron;
create extension if not exists http with schema extensions;
create schema if not exists alice_clock;
revoke all on schema alice_clock from public, anon, authenticated;

create table public.alice_scan_slots (
  day date not null, slot text not null, run jsonb not null,
  attempts int not null default 0, primary key(day,slot)
);
create table public.alice_direct_jobs (
  board text not null, job_id text primary key, job jsonb not null
);
alter table public.alice_scan_slots enable row level security;
alter table public.alice_direct_jobs enable row level security;
revoke all on public.alice_scan_slots, public.alice_direct_jobs from public, anon, authenticated;
grant select on public.alice_scan_slots, public.alice_direct_jobs to anon, authenticated;
create policy read_scan_slots on public.alice_scan_slots for select to anon, authenticated using (true);
create policy read_direct_jobs on public.alice_direct_jobs for select to anon, authenticated using (true);

create function alice_clock.register_due() returns void language sql as $$
  insert into public.alice_scan_slots(day,slot,run)
  select d, to_char(t,'HH24:MI'), jsonb_build_object(
    'engine','direct_ats','status','queued','scheduledFor',(d+t) at time zone 'Europe/Rome')
  from (select (now() at time zone 'Europe/Rome')::date d) days
  cross join (values (time '09:30'),(time '15:30')) slots(t)
  where d+t <= now() at time zone 'Europe/Rome'
  on conflict do nothing;
$$;

create function alice_clock.scan_due() returns void language plpgsql as $$
declare
  s public.alice_scan_slots%rowtype;
  b text; endpoint text; response extensions.http_response; listings jsonb; item jsonb;
  loc text; title text; link text; ident text; started timestamptz; added int; total_added int:=0;
  sources text[]:='{}'; evidence jsonb:='[]'; seen text[]; run_state text;
begin
  select * into s from public.alice_scan_slots
    where day=(now() at time zone 'Europe/Rome')::date and
      (run->>'status'='queued' or (run->>'status'='failed' and
        (run->>'completedAt')::timestamptz < now()-interval '10 minutes'))
    order by attempts,slot limit 1 for update skip locked;
  if not found then return; end if;
  started:=clock_timestamp();
  perform set_config('http.curlopt_timeout_ms','10000',true);
  foreach b in array array['gitlab','canonical'] loop
    endpoint:='https://boards-api.greenhouse.io/v1/boards/'||b||'/jobs';
    begin
      response:=extensions.http_get(endpoint);
      if response.status<>200 then raise exception 'HTTP %', response.status; end if;
      listings:=response.content::jsonb->'jobs';
      if jsonb_typeof(listings) is distinct from 'array' then raise exception 'Missing jobs array'; end if;
      seen:='{}'; added:=0;
      for item in select value from jsonb_array_elements(listings) loop
        loc:=item#>>'{location,name}'; title:=item->>'title'; link:=item->>'absolute_url';
        if coalesce(title,'') !~* '(tender|proposal|\mbid\M|\mpmo\M|project (support|coordinator|administrator)|sales (support|operations)|order management|contract admin|procurement support|back office|event coordinator)' or
           coalesce(loc,'') !~* '(remote|home based)' or coalesce(loc,'') !~* '\m(Italy|Italia|EMEA|Europe|worldwide)\M' or
           coalesce(link,'') !~ '^https://' or coalesce(item->>'id','') !~ '^[0-9]+$' then continue; end if;
        ident:='gh-'||b||'-'||(item->>'id'); seen:=array_append(seen,ident);
        insert into public.alice_direct_jobs values (b,ident,jsonb_build_object(
          'id',ident,'company',case b when 'gitlab' then 'GitLab' else 'Canonical' end,
          'title',title,'url',link,'location',loc,'category','Operations','workMode','Da remoto',
          'active',true,'remote',true,'source',b,'score',8,'firstSeenAt',started,
          'firstSeenRun',s.slot,'date',s.day,'verifiedAt',started,'checks',jsonb_build_array(endpoint)))
          on conflict do nothing;
        if found then added:=added+1; end if;
        update public.alice_direct_jobs set job=job||jsonb_build_object('active',true,'title',title,
          'url',link,'location',loc,'verifiedAt',started) where job_id=ident;
      end loop;
      update public.alice_direct_jobs set job=job||'{"active":false}'::jsonb
        where board=b and not(job_id=any(seen)) and job->>'active'='true';
      sources:=array_append(sources,b); total_added:=total_added+added;
      evidence:=evidence||jsonb_build_array(jsonb_build_object('url',endpoint,'openListings',jsonb_array_length(listings),'matched',cardinality(seen)));
    exception when others then
      evidence:=evidence||jsonb_build_array(jsonb_build_object('url',endpoint,'error',sqlerrm));
    end;
  end loop;
  run_state:=case when cardinality(sources)>0 then 'partial' else 'failed' end;
  update public.alice_scan_slots set attempts=attempts+1,run=run||jsonb_build_object(
    'status',run_state,'startedAt',started,'completedAt',clock_timestamp(),'queriesRun',2,
    'newJobs',total_added,'sourcesChecked',sources,'sourcesExplored',cardinality(sources),
    'searchLog',evidence,'requiredSourcesTotal',238) where day=s.day and slot=s.slot;
end;
$$;
select cron.schedule('alice-register-slots','* * * * *','select alice_clock.register_due()');
select cron.schedule('alice-scan-due','* * * * *','select alice_clock.scan_due()');
