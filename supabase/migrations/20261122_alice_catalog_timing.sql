create function public.alice_catalog_timing() returns table(slot text, started_at timestamptz, finished_at timestamptz, sources int, attempted int, processed int, unavailable int) language sql stable security definer set search_path='' as $$
 select to_char(r.due at time zone 'Europe/Rome','HH24:MI'),r.started,r.finished,count(t.source)::int,count(t.sent)::int,count(t.outcome)::int,count(*) filter(where t.outcome='unavailable')::int
 from alice_clock.catalog_run r left join alice_clock.catalog_task t using(due)
 where r.kind='scheduled' and (r.due at time zone 'Europe/Rome')::date=(now() at time zone 'Europe/Rome')::date
 group by r.due order by r.due
$$;
revoke all on function public.alice_catalog_timing() from public;
grant execute on function public.alice_catalog_timing() to anon,authenticated;