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
        read("alice_direct_jobs", "select=job&order=job_id")
      ]);
    }
    const [slots, listings] = await cached;
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
