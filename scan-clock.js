(() => {
  let cached;
  let expires = 0;
  let cachedDay;
  async function read(table, query) {
    const cfg = window.ALICE_RADAR_CONFIG.sync;
    const response = await fetch(cfg.url + "/rest/v1/" + table + "?" + query, {
      headers: {apikey: cfg.publishableKey}, cache: "no-store", signal: AbortSignal.timeout(6000)
    });
    if (!response.ok) throw new Error("HTTP " + response.status);
    return response.json();
  }
  const dayInRome = () => new Intl.DateTimeFormat("sv-SE", {timeZone:"Europe/Rome"}).format(new Date());
  const rank = run => ({complete:4, partial:3, running:2, in_progress:2, failed:1, queued:0})[run?.status] ?? -1;
  window.mergeAliceClock = async function(payload) {
    const day = dayInRome();
    if (day !== cachedDay || Date.now() >= expires) {
      cachedDay = day;
      expires = Date.now() + 20000;
      cached = Promise.allSettled([
        read("alice_scan_slots", "select=slot,run&day=eq." + day),
        read("alice_direct_jobs", "select=job&order=job_id"),
        read("rpc/alice_catalog_timing", "")
      ]);
    }
    const [slots, listings, timing] = await cached;
    const formatter = new Intl.DateTimeFormat("it-IT", {timeZone:"Europe/Rome", hour:"2-digit", minute:"2-digit", second:"2-digit"});
    for (const [slot, id] of [["09:30","catalog08"],["15:30","catalog15"]]) {
      const line = document.getElementById(id);
      if (!line) continue;
      const row = timing.status === "fulfilled" && timing.value.find(x => x.slot === slot);
      line.hidden = !row?.started_at;
      if (!line.hidden) {
        const progress = row.finished_at ? "terminata" : "in corso";
        line.textContent = "Ricerca catalogo avviata alle " + formatter.format(new Date(row.started_at)) +
          " · " + progress + " · " + row.attempted + "/" + row.sources + " richieste inviate · " +
          row.unavailable + " indisponibili";
      }
    }
    const result = {...payload};
    const directJobs = [];
    if (listings.status === "fulfilled" && listings.value.length) {
      const jobs = [...(payload.jobs || [])];
      const key = value => {
        try {
          const u = new URL(value);
          if (/(^|\.)indeed\.com$/.test(u.hostname)) {
            const jk = u.searchParams.get("jk") || u.searchParams.get("vjk");
            if (jk) return "indeed:" + jk;
          }
          u.hash = "";
          for (const k of [...u.searchParams.keys()]) {
            if (/^(utm_|source$|from$|trackingid$|refid$|trk$)/i.test(k)) u.searchParams.delete(k);
          }
          u.searchParams.sort();
          return u.href.replace(/\/$/, "");
        } catch { return String(value || ""); }
      };
      const byId = new Map(jobs.map((j, i) => [j.id, i]));
      const urls = new Set(jobs.map(j => key(j.url)));
      for (const {job} of listings.value) {
        if (byId.has(job.id)) {
          const i = byId.get(job.id);
          jobs[i] = {...jobs[i], ...job};
          directJobs.push(job);
          continue;
        }
        if (urls.has(key(job.url))) continue;
        jobs.push(job);
        directJobs.push(job);
        byId.set(job.id, jobs.length - 1);
        urls.add(key(job.url));
      }
      result.jobs = jobs;
    }
    if (slots.status === "fulfilled" && slots.value.length) {
      const runs = {...(payload.audit?.date === day ? payload.audit.runs : {})};
      for (const {slot,run} of slots.value) {
        const primary = runs[slot];
        const newListings = directJobs.filter(j => j.date === day && j.firstSeenRun === slot).length;
        // A user-requested replacement scan supersedes the earlier slot record,
        // even when the former had a higher adapter count. Never claim full coverage.
        if (run.supersedesScheduled === true && ['partial','complete'].includes(run.status)) {
          runs[slot] = {...run, newJobs: listings.status === 'fulfilled' ? newListings : run.newJobs};
          continue;
        }
        // An explicitly requested rescan replaces the scheduled slot audit with
        // its real completion time and result; older counters must not be added.
        if (run.replacesScheduledSlot === slot || run.supersedesScheduled === true) {
          runs[slot] = {...run, newJobs: listings.status === "fulfilled" ? newListings : run.newJobs};
          continue;
        }
        if (run.status === "partial" && ["complete","partial"].includes(primary?.status) && primary.engine !== run.engine) {
          const sourcesChecked = [...new Set([...(primary.sourcesChecked || []), ...run.sourcesChecked])];
          runs[slot] = {...primary, sourcesChecked,
            sourcesExplored: Math.max(primary.sourcesExplored || 0, sourcesChecked.length),
            queriesRun: (primary.queriesRun || 0) + run.queriesRun,
            newJobs: (primary.newJobs || 0) + (listings.status === "fulfilled" ? newListings - (primary.directNewJobsIncluded || 0) : 0)};
          continue;
        }
        if (rank(run) > rank(runs[slot]) ||
           (rank(run) === rank(runs[slot]) && run.sourcesExplored > (runs[slot]?.sourcesExplored ?? 0))) {
          runs[slot] = listings.status === "fulfilled" && run.status === "partial" ? {...run,newJobs:newListings} : run;
        }
      }
      result.audit = {date:day, runs};
    }
    return result;
  };
})();
