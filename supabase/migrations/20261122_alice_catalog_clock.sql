create extension if not exists pg_net;
create table alice_clock.catalog_run (
 due timestamptz primary key, kind text not null, started timestamptz, finished timestamptz
);
create table alice_clock.catalog_task (
 due timestamptz references alice_clock.catalog_run, source text, position int, url text not null,
 request bigint, sent timestamptz, attempts int not null default 0, outcome text, links text[], primary key(due,source)
);
create table alice_clock.catalog_settings(installed timestamptz default now(), refreshed timestamptz, sources jsonb);
insert into alice_clock.catalog_settings(sources) values ('[]');
create function alice_clock.catalog_tick() returns void language plpgsql set search_path='' as $$
declare
 cfg alice_clock.catalog_settings; r record; entry record; q record; resp record;
 docs jsonb; nm text; domain text; target text; result text; urls text[]; at_day date:=(now() at time zone 'Europe/Rome')::date;
begin
 if not pg_try_advisory_xact_lock(703130098) then return; end if;
 select * into strict cfg from alice_clock.catalog_settings;
 if cfg.refreshed is null or cfg.refreshed < now()-interval '6 hours' then
  begin
   perform set_config('http.curlopt_timeout_ms','4000',true);
   select * into resp from extensions.http_get('https://raw.githubusercontent.com/MarcoVeneri/Alice-Job-Radar/main/data/source_catalog.json');
   if resp.status=200 then
    docs:=resp.content::jsonb->'sources';
    if jsonb_array_length(docs)>0 then update alice_clock.catalog_settings set sources=docs,refreshed=now();cfg.sources:=docs;end if;
   end if;
  exception when others then raise warning 'Catalogue refresh failed: %',sqlerrm;end;
 end if;
 insert into alice_clock.catalog_run(due,kind)
 select (at_day+t) at time zone 'Europe/Rome','scheduled' from (values(time '09:30'),(time '15:30')) slots(t)
 where (at_day+t) at time zone 'Europe/Rome' between cfg.installed and now() on conflict do nothing;
 for r in select * from alice_clock.catalog_run where due<=now() and started is null loop
  for entry in select value,ordinality from jsonb_array_elements(cfg.sources) with ordinality loop
   nm:=entry.value->>'name';domain:=coalesce(entry.value->>'searchDomain',substring(entry.value->>'url' from '^https://([^/?]+)'));
   target:=case nm when 'LinkedIn Jobs' then 'https://it.linkedin.com/jobs/search/?keywords=ufficio%20gare%20OR%20PMO&location=Italia&f_WT=2%2C3'
    when 'Indeed Italia' then 'https://it.indeed.com/jobs?q=%28ufficio+gare+OR+PMO%29+%28ibrido+OR+remoto%29&l=Italia'
    else 'https://www.bing.com/search?format=rss&q='||extensions.urlencode(concat_ws(' ',case when domain is not null then 'site:'||domain end,split_part(nm,' / ',1),'Italia ("ufficio gare" OR PMO OR "back office") ("smart working" OR ibrido OR remoto)')::varchar) end;
   insert into alice_clock.catalog_task(due,source,position,url) values(r.due,nm,entry.ordinality,target) on conflict do nothing;
  end loop;
 end loop;
 for q in select * from alice_clock.catalog_task where request is not null and outcome is null loop
  select * into resp from net._http_response where id=q.request;
  if not found and q.sent>now()-interval '2 minutes' then continue;end if;
  urls:='{}'; result:='unavailable';
  if resp.status_code=200 and resp.content ~* '<rss[ >]' then
   select array(select x[1] from regexp_matches(resp.content,'<item>.*?<link>(https?://[^<]+)</link>','g') x limit 10) into urls;
   result:=case when cardinality(urls)>0 then 'indexed_candidates' else 'no_indexed_results' end;
  elsif resp.status_code=200 and resp.content ~* '(base-search-card|job_seen_beacon|data-jk=)' then
   result:='direct_results';
   if q.source='Indeed Italia' then select array(select distinct 'https://it.indeed.com/viewjob?jk='||x[1] from regexp_matches(resp.content,'data-jk="([a-f0-9]+)"','g') x limit 10) into urls;
   else select array(select distinct x[1] from regexp_matches(resp.content,'(https://[a-z.]*linkedin.com/jobs/view/[^" <>]+)','g') x limit 10) into urls;end if;
  end if;
  if result='unavailable' and q.attempts<2 and coalesce(resp.status_code,0) in (0,408,429,500,502,503,504) then
   update alice_clock.catalog_task set request=null where due=q.due and source=q.source;
  else update alice_clock.catalog_task set outcome=result,links=urls where due=q.due and source=q.source;
  end if;
 end loop;
 for q in select * from alice_clock.catalog_task where request is null and outcome is null and (attempts=0 or sent<now()-interval '90 seconds') order by due desc,attempts,position limit 12 loop
  update alice_clock.catalog_task set request=net.http_get(q.url,timeout_milliseconds:=9000),sent=clock_timestamp(),attempts=attempts+1 where due=q.due and source=q.source;
  update alice_clock.catalog_run set started=clock_timestamp() where due=q.due and started is null;
 end loop;
 update alice_clock.catalog_run r0 set finished=clock_timestamp() where started is not null and finished is null and not exists(select 1 from alice_clock.catalog_task t where t.due=r0.due and t.outcome is null);
end;$$;
revoke all on function alice_clock.catalog_tick() from public,anon,authenticated;
select cron.schedule('alice-catalog-clock','15 seconds','select alice_clock.catalog_tick()');
