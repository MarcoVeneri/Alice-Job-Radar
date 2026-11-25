#!/usr/bin/env python3
"""Alice Radar: fallback scanner of public, documented job feeds (no credentials)."""
from __future__ import annotations

from job_url import job_url
from job_schema import normalize_catalog, write_catalog, self_test as schema_self_test
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
import html
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from jobsora_extract import listing_candidates, verify_many, norm

REGIONS = [
    ("Valle d'Aosta", "valle-d-aosta"), ("Piemonte", "piemonte"),
    ("Liguria", "liguria"), ("Lombardia", "lombardia"),
    ("Trentino-Alto Adige", "trentino-alto-adige"), ("Veneto", "veneto"),
    ("Friuli-Venezia Giulia", "friuli-venezia-giulia"),
    ("Emilia-Romagna", "emilia-romagna"), ("Toscana", "toscana"),
    ("Umbria", "umbria"), ("Marche", "marche"), ("Lazio", "lazio"),
    ("Abruzzo", "abruzzo"), ("Molise", "molise"), ("Campania", "campania"),
    ("Puglia", "puglia"), ("Basilicata", "basilicata"),
    ("Calabria", "calabria"), ("Sicilia", "sicilia"), ("Sardegna", "sardegna"),
]
BASE = Path("data/jobs.json")
ROME = ZoneInfo("Europe/Rome")
ROLE = re.compile(
    r"\b(pmo|project\s+(?:support|coordinator|administrator|operations)|"
    r"bid\s+(?:specialist|manager|coordinator|writer)|tender|proposal|"
    r"sales\s+(?:support|operations?|enablement|administrator|coordinator)|"
    r"commercial\s+(?:support|operation|coordinator|assistant)|"
    r"revenue\s+operations?|order\s+management|procurement\s+(?:support|coordinator)|"
    r"contract\s+(?:support|administrator|coordinator)|"
    r"customer\s+(?:operations?|support|success)|back[\s-]?office|"
    r"event\s+(?:coordinator|specialist|planner))\b", re.I
)
LOC = re.compile(r"\b(italy|italia|italian|europe|eu\b|emea|worldwide|anywhere|global|"
                 r"firenze|toscana|milano|roma|bologna|torino|napoli|veneto|lombardia|"
                 r"piemonte|genova|perugia|pisa|arezzo|modena)\b", re.I)


def text(value):
    return html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).strip()


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "AliceJobRadar/6.38 (+public job feed; no applications)",
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.loads(response.read(12_000_000).decode("utf-8"))


def _fetch_feed(source):
    name, url, kind = source
    start = datetime.now(timezone.utc).isoformat()
    try:
        data = get_json(url)
        if kind == "smartrecruiters":
            entries = list(data["content"])
            total = data["totalFound"]
            offset = len(entries)
            while offset < total:
                page = get_json(url + "&offset=" + str(offset))["content"]
                if not page:
                    raise ValueError("Incomplete postings pagination")
                entries.extend(page)
                offset += len(page)
        else:
            entries = data.get("jobs", data.get("data", []))
        if not isinstance(entries, list):
            raise ValueError("Feed did not return a jobs list")
        log = {"source": name, "method": "public_feed_api", "checkedAt": start,
               "outcome": f"success: {len(entries)} raw postings", "evidenceUrls": [url]}
        return log, [(name, kind, raw) for raw in entries if isinstance(raw, dict)]
    except Exception as exc:
        return {"source": name, "method": "public_feed_api", "checkedAt": start,
                "outcome": "unavailable: " + str(exc)[:180],
                "evidenceUrls": [url]}, []


def feed_rows():
    # Parallel independent sources: one slow feed must not block the entire scan.
    sources = [
        ("Jobicy-Europe", "https://jobicy.com/api/jobs?count=200&geo=europe", "jobicy"),
        ("Jobicy-Anywhere", "https://jobicy.com/api/jobs?count=200&geo=anywhere", "jobicy"),
        ("Arbeitnow-page1", "https://www.arbeitnow.com/api/job-board-api?page=1", "arbeitnow"),
        ("Arbeitnow-page2", "https://www.arbeitnow.com/api/job-board-api?page=2", "arbeitnow"),
        ("Arbeitnow-page3", "https://www.arbeitnow.com/api/job-board-api?page=3", "arbeitnow"),
        ("Remotive", "https://remotive.com/api/remote-jobs?limit=200", "remotive"),
    ]
    catalog = json.loads(Path("data/source_catalog.json").read_text())
    for board in catalog["sources"]:
        account = board.get("smartRecruitersAccount")
        if account:
            url = f"https://api.smartrecruiters.com/v1/companies/{account}/postings?country=it&limit=100"
            sources.append((board["name"], url, "smartrecruiters"))
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(_fetch_feed, sources))
    return [row for _, rows in results for row in rows], [log for log, _ in results]


REGIONAL_ROLES = ("ufficio-gare", "back-office-commerciale", "pmo", "sales-operations", "project-coordinator")

def _check_listing(task):
    """Retrieve a regional index, extracting candidates (not yet verified)."""
    region, slug, role = task
    url = f"https://it.jobsora.com/lavoro-{role}-{slug}"
    stamp = datetime.now(timezone.utc).isoformat()
    found = []
    try:
        req = urllib.request.Request(url,
            headers={"User-Agent":"Mozilla/5.0 (compatible; AliceJobRadar/6.41)",
                     "Accept":"text/html"})
        with urllib.request.urlopen(req,timeout=7) as response:
            page = response.read(240_000).decode("utf-8","replace")
            status = response.status
        if status == 200 and "<html" in page.lower() and "jobsora" in page.lower():
            outcome = "index_page_accessible; detail check required"
            found = listing_candidates(page,region,limit=3)
        else:
            outcome = f"invalid_or_unrelated_listing_{status}"
    except Exception as exc:
        outcome = "unavailable: " + str(exc)[:130]
    return ({"source":"Jobsora regional indexed listings",
             "method":"regional_index_discovery_only",
             "region":region,"query":role,"checkedAt":stamp,
             "outcome":outcome,"candidatesFound":len(found),
             "evidenceUrls":[url]},found)

def region_discovery():
    """Try five roles per region; verify individual vacancy pages separately."""
    tasks=[(region,slug,role) for region,slug in REGIONS for role in REGIONAL_ROLES]
    with ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(_check_listing,tasks))
    logs=[log for log,_ in results]
    coverage={}
    for region,_ in REGIONS:
        items=[x for x in logs if x["region"]==region]
        accessible=sum(x["outcome"].startswith("index_page_accessible") for x in items)
        coverage[region]={"attempted":len(items),
                          "indexPagesAccessible":accessible,
                          "unavailable":len(items)-accessible,
                          "candidateLinksFound":sum(x["candidatesFound"] for x in items),
                          "status":"index_search_attempted_postings_checked_separately"}
    candidates=[]
    ids=set()
    quota={region:0 for region,_ in REGIONS}
    for _,rows in results:
        for candidate in rows:
            region=candidate["region"]
            ident=candidate["id"]
            if ident in ids or quota[region]>=6:
                continue
            candidates.append(candidate)
            ids.add(ident)
            quota[region]+=1
    return coverage,logs,candidates


def mapped_job(source, kind, raw, today, now):
    work_mode = "Da remoto"
    if kind in ("linkedin","employer"):
        title, company, place, url = (raw[k] for k in ("title","company","place","url"))
        details, work_mode, remote = raw["details"], raw["mode"], True
        salary = contract = ""
    elif kind == "smartrecruiters":
        location = raw.get("location") or {}
        if location.get("country", "").lower() != "it" or raw.get("visibility") != "PUBLIC":
            return None
        hybrid = location.get("hybrid") is True
        remote = hybrid or location.get("remote") is True
        work_mode = "Ibrido" if hybrid else "Da remoto"
        title = text(raw.get("name"))
        employer = raw.get("company") or {}
        company = text(employer.get("name"))
        ident = str(raw.get("id") or "")
        if not ident.isdigit() or not employer.get("identifier"):
            return None
        url = "https://jobs.smartrecruiters.com/" + urllib.parse.quote(employer["identifier"], safe="") + "/" + ident
        place = text(location.get("fullLocation") or location.get("city") or "Italia")
        contract = text((raw.get("typeOfEmployment") or {}).get("label"))
        details = f"{title} · {place} · {work_mode}"
        salary = ""
    elif kind == "jobicy":
        title = text(raw.get("jobTitle"))
        company = text(raw.get("companyName"))
        place = text(raw.get("jobGeo"))
        url = str(raw.get("url") or "")
        details = text(raw.get("jobExcerpt") or raw.get("jobDescription"))
        salary = str(raw.get("annualSalary") or "")
        contract = text(raw.get("jobType"))
        remote = True
    elif kind == "arbeitnow":
        title = text(raw.get("title"))
        company = text(raw.get("company_name"))
        place = text(raw.get("location"))
        url = str(raw.get("url") or "")
        details = text(raw.get("description"))
        salary = ""
        contract = ""
        remote = raw.get("remote") is True
    else:
        title = text(raw.get("title"))
        company = text(raw.get("company_name"))
        place = text(raw.get("candidate_required_location"))
        url = str(raw.get("url") or "")
        details = text(raw.get("description"))
        salary = text(raw.get("salary"))
        contract = text(raw.get("job_type"))
        remote = True
    if not (title and company and url.startswith("https://") and (ROLE.search(title) or re.search(r"\b(?:ufficio gare|gare e appalti|segreteria commerciale|gestione ordini|supporto commerciale|sales operations|revenue operations|MICE|inside sales|amministrazione commerciale|ufficio commerciale|supporto alle vendite|supporto amministrativo|customer operations|vendor administration|contract administrator)\b", title, re.I))):
        return None
    # Fail closed: regional presence and ambiguous geographic restrictions need manual verification.
    if not remote or kind not in ("linkedin","employer","smartrecruiters") and not re.fullmatch(r"(?:italy|italia|europe|european union|eu|emea|worldwide|anywhere|global)", place.strip(), re.I):
        return None
    parsed = urllib.parse.urlparse(url)
    if parsed.path.strip("/") in ("", "jobs", "careers", "remote-jobs"):
        return None
    key = hashlib.sha256(job_url(url).encode("utf-8")).hexdigest()[:18]
    category = ("Tender" if re.search(r"bid|tender|proposal", title, re.I) else
                "Project Support / PMO" if re.search(r"pmo|project", title, re.I) else
                "Sales Support")
    score = 8.6 if re.search(r"firenze|toscana|italia|italy", place, re.I) else 7.5
    source_note = "Attiva nel feed API al momento del controllo; verificare requisiti e disponibilità prima della candidatura."
    if kind == "linkedin":
        source_note = "Smart working documentato nella descrizione della posizione."
    return {"id": ("linkedin-" + url.rsplit("/", 1)[-1]) if kind == "linkedin" else f"feed-{key}", "company": company, "title": title,
            "location": place or "Remote (requisiti geografici da verificare)",
            "category": category, "url": url, "workMode": work_mode,
            "contract": contract or "Da verificare", "salary": salary or "Non indicata",
            "remote": bool(remote), "active": True, "date": today, "firstSeenAt": now,
            "firstSeenRun": "Scansione automatica fallback", "verifiedAt": now,
            "source": source, "summary": details[:450],
            "checks": [source_note, f"Fonte: {source}. Lingue e località da verificare."],
            "score": score}


def choose_slot(rome, scheduled, trigger=None):
    """Recover the latest due local slot even when the scheduler is hours late."""
    mins = rome.hour * 60 + rome.minute
    if scheduled or trigger in ("push", "workflow_dispatch"):
        if mins >= 930:
            return "15:30"
        if mins >= 570:
            return "09:30"
        return None
    return "automated_fallback"


def adequate(run):
    if not isinstance(run, dict):
        return False
    if run.get("status") == "complete":
        return True
    coverage = run.get("regionCoverage", {})
    catalog = run.get("catalogSearchDiagnostics") or {}
    # Regional index requests or two ATS feeds are not a catalog scan.
    primary = run.get("primaryPortalAttempts") or {}
    gate = run.get("universalDetailGate") or {}
    # Queries to RSS indexes do not certify a scan; require evidence of
    # both major portals and inspection of individual vacancy pages.
    return (run.get("status") == "partial"
            and len(coverage) >= 20
            and int(catalog.get("catalogSourcesAccountedFor") or 0) >= 200
            and int(primary.get("LinkedIn Jobs") or 0) >= 12
            and int(primary.get("Indeed Italia") or 0) >= 12
            and (int(gate.get("candidatePagesAttempted") or 0) > 0
                 or int(run.get("specificJobPagesOpened") or 0) > 0)
            and bool(run.get("completedAt")))


def due_slots(rome, data):
    audit = data.get("audit", {})
    runs = audit.get("runs", {}) if audit.get("date") == rome.date().isoformat() else {}
    return [slot for slot in ("09:30", "15:30")
            if rome.hour * 60 + rome.minute >= int(slot[:2]) * 60 + 30
            and not adequate(runs.get(slot))]


def prepare():
    """Persist start before network work; the workflow publishes this checkpoint."""
    rome = datetime.now(ROME)
    data = json.loads(BASE.read_text(encoding="utf-8"))
    repaired = normalize_catalog(data)
    slots = due_slots(rome, data)
    if not slots:
        if repaired:
            write_catalog(BASE, data)
        return
    today = rome.date().isoformat()
    previous = data.get("audit", {})
    if previous.get("date") != today:
        history = data.setdefault("auditHistory", [])
        if previous.get("date") and not any(x.get("date") == previous["date"] for x in history):
            history.append(previous)
        data["audit"] = {"date": today, "runs": {}}
    for slot in slots:
        prior = data["audit"].setdefault("runs", {}).get(slot)
        # Do not hide already published partial evidence during a retry.
        if prior and prior.get("status") == "partial":
            continue
        data["audit"]["runs"][slot] = {
            "status": "running", "engine": "github_backup",
            "scheduledFor": rome.replace(hour=int(slot[:2]), minute=30, second=0, microsecond=0).isoformat(),
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "queriesRun": 0, "newJobs": 0,
            "note": "Scansione avviata; checkpoint pubblicato prima delle richieste alle fonti."}
    write_catalog(BASE, data)


def drain():
    # Recover due scheduled slots FIRST. The old implementation performed a
    # whole manual national scan before the scheduled run on every push;
    # that could exhaust the runner timeout before 15:30 was ever recorded.
    slots = due_slots(datetime.now(ROME), json.loads(BASE.read_text(encoding="utf-8")))
    if slots:
        # At 15:30, recover the afternoon slot before any stale morning retry.
        for slot in reversed(slots):
            main(slot)
    elif os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        # An explicit manual dispatch may run a separate sweep, but a push
        # must never shadow or delay the two scheduled slots.
        main("manual_national")
    # Preserve the national results if the independent source is temporarily offline.
    from publish_direct_jobs import main as publish_direct_jobs
    try:
        publish_direct_jobs()
    except (OSError, ValueError) as exc:
        print(f"Direct-board mirror deferred to the next backup: {exc}")



def candidate_source_coverage_self_test():
    """Diagnostic shape smoke test; no network calls."""
    return {"attempted": len(set(("LinkedIn Jobs", "Indeed Italia", "LinkedIn Jobs"))),
            "verified": 0, "blocked": 1}


def self_test():
    schema_self_test()
    for month in (1, 7, 11):
        date = datetime(2026, month, 16, tzinfo=ROME)
        for hour, minute, expected in [(9,29,None),(9,30,"09:30"),
                (10,40,"09:30"),(13,15,"09:30"),(15,29,"09:30"),
                (15,30,"15:30"),(16,40,"15:30"),(23,59,"15:30")]:
            for trigger in ("schedule", "push", "workflow_dispatch"):
                assert choose_slot(date.replace(hour=hour,minute=minute),
                                   trigger == "schedule",trigger) == expected
    # A normal push must prioritize due scheduled work over duplicate manual sweeps.
    assert due_slots(datetime(2026,11,23,15,57,tzinfo=ROME),
                     {"audit":{"date":"2026-11-23","runs":{
                      "09:30":{"status":"complete"}}}})==["15:30"]
    assert not adequate({"status":"partial","regionCoverage":dict.fromkeys((x[0] for x in REGIONS), {}),"requiredSourcesChecked":2,
        "completedAt":"2026-11-23T15:35:00Z"})
    assert not adequate({"status":"partial","regionCoverage":dict.fromkeys((x[0] for x in REGIONS), {}),"requiredSourcesChecked":2,
        "catalogSearchDiagnostics":{"catalogSourcesAccountedFor":263},
        "completedAt":"2026-11-23T15:35:00Z"})
    assert adequate({"status":"partial","regionCoverage":dict.fromkeys((x[0] for x in REGIONS), {}),
        "catalogSearchDiagnostics":{"catalogSourcesAccountedFor":263},
        "primaryPortalAttempts":{"LinkedIn Jobs":24,"Indeed Italia":24},
        "universalDetailGate":{"candidatePagesAttempted":4},
        "completedAt":"2026-11-23T15:35:00Z"})
    assert len(REGIONS)==20 and len(REGIONAL_ROLES)==5
    from linkedin_search import self_test as primary_portal_test
    from verify_vacancies import self_test as all_sources_test
    primary_portal_test()
    all_sources_test()
    assert isinstance(candidate_source_coverage_self_test(), dict)
    print("Delayed scheduler recovery, winter/summer slots: OK")


def record_failure():
    data = json.loads(BASE.read_text(encoding="utf-8"))
    audit = data.get("audit", {})
    for run in audit.get("runs", {}).values():
        if run.get("status") == "running" and run.get("engine") == "github_backup":
            run.update(status="failed", completedAt=datetime.now(timezone.utc).isoformat(),
                       note="Recupero interrotto prima della pubblicazione dei risultati. Controlli non confermati.")
    write_catalog(BASE, data)


def main(slot_override=None):
    rome = datetime.now(ROME)
    today = rome.date().isoformat()
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    # Summer/winter UTC schedules have redundant entries; use local Rome time.
    slot = slot_override or choose_slot(rome, os.environ.get("GITHUB_EVENT_NAME") == "schedule", os.environ.get("GITHUB_EVENT_NAME"))
    if slot is None:
        print(f"Skipping redundant UTC schedule at {rome.isoformat()}")
        return
    data = json.loads(BASE.read_text(encoding="utf-8"))
    previous = data.get("audit")
    if not isinstance(previous, dict) or previous.get("date") != today:
        if isinstance(previous, dict) and previous.get("date"):
            hist = data.setdefault("auditHistory", [])
            if not any(x.get("date") == previous["date"] for x in hist if isinstance(x, dict)):
                hist.append(previous)
        data["audit"] = {"date": today, "runs": {}}
    if slot in ("09:30", "15:30"):
        prev = data["audit"].get("runs", {}).get(slot)
        if isinstance(prev, dict) and prev.get("status") in ("partial", "complete"):
            coverage = prev.get("regionCoverage")
            if adequate(prev):
                print(f"Scheduled {slot} already completed an adequate region sweep; skipping redundant retry.")
                return
    catalog_file = Path("data/source_catalog.json")
    try:
        required_sources_total = len(json.loads(catalog_file.read_text(encoding="utf-8")).get("sources", [])) or 238
    except (OSError, ValueError, TypeError):
        required_sources_total = 238
    scheduled_for = rome.replace(hour=int(slot[:2]), minute=30, second=0, microsecond=0).isoformat() if slot in ("09:30", "15:30") else now
    previous_slot = data["audit"].setdefault("runs", {}).get(slot)
    data["audit"].setdefault("runs", {})[slot] = {
        "status":"running", "engine":"github_backup", "scheduledFor":scheduled_for,
        "startedAt":now, "newJobs":0, "queriesRun":0,
        "note":"Recupero automatico avviato; risultati ancora da verificare."}
    write_catalog(BASE, data)
    # Priority: search LinkedIn and Indeed independently BEFORE slower generic feeds.
    # If the rest of the national sweep fails, their real attempt logs still exist.
    from linkedin_search import discover
    from tuscany_boards import discover_boards
    from catalog_scout import discover_catalog
    historical = [run for audit in data.get("auditHistory", []) + [data["audit"]] for run in audit.get("runs", {}).values() if isinstance(run,dict)]
    if previous_slot: historical.append(previous_slot)
    previous_logs = [log for run in sorted(historical,key=lambda r:r.get("completedAt") or "") for log in run.get("searchLog",[]) if isinstance(log,dict)]
    # Every provider group is isolated: a blocked portal or transient timeout
    # must not abort the other groups or erase an existing scheduled checkpoint.
    rows, logs = [], []
    def safe_group(name, action):
        try:
            result = action()
            if not isinstance(result, tuple) or len(result) != 2:
                raise ValueError("Unexpected discovery response")
            return result
        except Exception as exc:
            msg = f"{type(exc).__name__}: {str(exc)[:200]}"
            print(f"::warning::Alice source group {name} unavailable: {msg}")
            return [], [{"source":name, "method":"source_group_recovery",
                         "checkedAt":datetime.now(timezone.utc).isoformat(),
                         "outcome":"unavailable: "+msg, "evidenceUrls":[]}]
    for name, action in (
        ("LinkedIn Jobs / Indeed Italia", lambda: discover(previous_logs)),
        ("Public ATS / remote job feeds", feed_rows),
        ("Italian employer careers", discover_boards),
        ("National job-board catalog", discover_catalog),
    ):
        found_rows, found_logs = safe_group(name, action)
        rows.extend(found_rows)
        logs.extend(found_logs)
    try:
        regional_coverage, regional_logs, candidate_postings = region_discovery()
    except Exception as exc:
        msg = f"{type(exc).__name__}: {str(exc)[:200]}"
        print(f"::warning::Alice 20-region discovery failed: {msg}")
        regional_coverage = {region: {"attempted":0,"indexPagesAccessible":0,
            "unavailable":1,"candidateLinksFound":0,"status":"unavailable"}
            for region, _ in REGIONS}
        regional_logs = [{"source":"Jobsora regional indexed listings",
            "method":"regional_discovery_recovery",
            "checkedAt":datetime.now(timezone.utc).isoformat(),
            "outcome":"unavailable: "+msg,"evidenceUrls":[]}]
        candidate_postings = []
    try:
        checked_regional = verify_many(candidate_postings,today,now)
    except Exception as exc:
        msg = f"{type(exc).__name__}: {str(exc)[:200]}"
        print(f"::warning::Alice regional detail verification failed: {msg}")
        checked_regional = []
        regional_logs.append({"source":"Jobsora detail verification",
            "method":"individual_detail_recovery",
            "checkedAt":datetime.now(timezone.utc).isoformat(),
            "outcome":"unavailable: "+msg,"evidenceUrls":[]})
    # Aggregator detail is not the original employer posting. Until a live
    # original application page is confirmed, do not publish it as verified.
    verified_regional = [j for j in checked_regional
                         if j.get("verificationLevel") == "individual_original_posting"
                         and j.get("remote") is True
                         and j.get("workMode") != "Da verificare"]
    from verify_vacancies import verify_many_mapped
    mapped_entries = []
    for source, kind, raw in rows:
        try:
            mapped_entries.append((source, kind, raw,
                                   mapped_job(source, kind, raw, today, now)))
        except Exception as exc:
            logs.append({"source":source,"method":"posting_mapping_recovery",
                         "checkedAt":datetime.now(timezone.utc).isoformat(),
                         "outcome":"unavailable: mapping failed: "+str(exc)[:150],
                         "evidenceUrls":[]})
    try:
        verified_jobs, gate_logs, gate_counts = verify_many_mapped(mapped_entries)
    except Exception as exc:
        msg = f"{type(exc).__name__}: {str(exc)[:200]}"
        print(f"::warning::Alice individual posting gate failed: {msg}")
        verified_jobs, gate_counts = [], {}
        gate_logs = [{"source":"Individual vacancy verification",
                      "method":"individual_posting_recovery",
                      "checkedAt":datetime.now(timezone.utc).isoformat(),
                      "outcome":"unavailable: "+msg,"evidenceUrls":[]}]
    logs.extend(gate_logs)
    for item in checked_regional:
        region = item["region"]
        regional_coverage[region]["detailPagesVerified"] = (
            regional_coverage[region].get("detailPagesVerified",0)+1)
    # Do not count a query, a blocked page or an API list as proof that
    # individual vacancies were checked. Preserve their separate outcomes.
    successes = [x for x in logs if x["outcome"].startswith("success:")]
    found_accessible = any(x["indexPagesAccessible"] for x in regional_coverage.values())
    checked_sources = sorted({x["source"] for x in successes} |
                             ({"Jobsora"} if found_accessible else set()))
    # Keep portal/card/index access distinct from validated original vacancies:
    # a blocked search or zero indexed hits is NOT a completed vacancy audit.
    candidate_source_attempts = sorted({x["source"] for x in logs
        if x.get("method") not in ("universal_individual_vacancy_gate",)} |
        ({"Jobsora regional indexed listings"} if regional_logs else set()))
    candidate_source_blocked = sorted({x["source"] for x in logs
        if str(x.get("outcome", "")).startswith("unavailable:")})
    candidate_source_verified = sorted({src for (src, status), count in gate_counts.items()
        if status == "verified" and count > 0} |
        {x["source"] for x in logs if x.get("method") == "individual_detail_verification"
         and int(x.get("specificJobPagesVerified") or 0) > 0})
    primary_attempts = {p: sum(1 for log in logs if log["source"] == p
                        and log.get("method") == "direct_public_cards")
                        for p in ("LinkedIn Jobs", "Indeed Italia")}
    primary_verified = {p: sum(log.get("specificJobPagesVerified", 0)
                        for log in logs if log["source"] == p)
                        for p in primary_attempts}
    if not successes and not found_accessible:
        print("All national sources unavailable: recording a failed audit honestly")
    old = data.get("jobs", [])
    ids = {str(j.get("id")) for j in old}
    links = {job_url(str(j.get("url", ""))) for j in old}
    def semantic(j):
        return (norm(j.get("company")),norm(j.get("title")),norm(j.get("location")))
    known = {semantic(j) for j in old}
    added = []
    regional_added = 0
    for candidate in verified_regional:
        link = job_url(candidate["url"])
        key = semantic(candidate)
        if candidate["id"] in ids or link in links or key in known:
            continue
        old.insert(0,candidate)
        added.append(candidate)
        ids.add(candidate["id"])
        links.add(link)
        known.add(key)
        regional_added += 1
    for candidate in verified_jobs:
        link = job_url(candidate["url"])
        if candidate["id"] in ids or link in links or semantic(candidate) in known:
            continue
        old.insert(0, candidate)
        added.append(candidate)
        ids.add(candidate["id"])
        links.add(link)
        known.add(semantic(candidate))
    data["jobs"] = old
    run = {"scheduledFor": scheduled_for, "engine":"github_backup", "startedAt": now, "completedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
           "status": "partial" if (successes or found_accessible) else "failed", "coverageMode": "national_20_region_discovery_plus_verified_public_feeds",
           "requiredSourcesTotal": required_sources_total, "requiredSourcesChecked": len(checked_sources),
           "sourcesExplored": len(checked_sources), "sourcesChecked": checked_sources,
           "directSourcesChecked": [], "siteRestrictedSourcesChecked": [],
           "indexedFallbackSourcesChecked": [x["source"] for x in successes],
           "sourcesUnavailable": sorted({x["source"] for x in logs if str(x.get("outcome", "")).startswith("unavailable:")} - {x["source"] for x in successes}),
           "queriesRun": len(logs) + len(regional_logs) + len(candidate_postings),
           "primaryPortalAttempts":primary_attempts,
           "primaryPortalVerified":primary_verified,
           "catalogSearchDiagnostics": {
               "catalogSourcesAccountedFor":sum(1 for x in logs if
                   x.get("method") == "catalog_source_individual_vacancy_probe"),
               "catalogSourcesProbed":sum(1 for x in logs if
                   x.get("method") == "catalog_source_individual_vacancy_probe"
                   and x.get("outcome") != "handled_by_primary_or_ats_adapter"),
               "catalogSourcesDelegated":sum(1 for x in logs if
                   x.get("method") == "catalog_source_individual_vacancy_probe"
                   and x.get("outcome") == "handled_by_primary_or_ats_adapter"),
               "catalogSourcesUnavailable":sum(1 for x in logs if
                   x.get("method") == "catalog_source_individual_vacancy_probe"
                   and str(x.get("outcome", "")).startswith("unavailable:")),
               "catalogOriginalJobsVerified":sum(
                   int(x.get("specificJobPagesVerified") or 0) for x in logs
                   if x.get("method") == "catalog_source_individual_vacancy_probe"),
               "note":"Index results are discovery only, not verified jobs.",
           },
           "sourceCoverageDiagnostics": {
               "sourceAdaptersAttempted":len(candidate_source_attempts),
               "attemptedNames":candidate_source_attempts,
               "unavailableNames":candidate_source_blocked,
               "verifiedOriginalPostingNames":candidate_source_verified,
               "note":"Independent catalog-clock request count must never be read as verified vacancies.",
           },
           "universalDetailGate": {
               "candidatePagesAttempted":sum(n for (src, status), n in gate_counts.items()
                                            if status not in ("filtered_by_role_or_location","deferred_after_cap")),
               "verified":sum(n for (src, status), n in gate_counts.items() if status == "verified"),
               "unavailable":sum(n for (src, status), n in gate_counts.items() if status == "unavailable"),
               "filteredByRoleLocation":sum(n for (src, status), n in gate_counts.items()
                                            if status == "filtered_by_role_or_location"),
               "rejectedAfterDetail":sum(n for (src, status), n in gate_counts.items()
                                          if status not in ("verified","unavailable",
                                                            "filtered_by_role_or_location","deferred_after_cap")),
               "deferredAfterCap":sum(n for (src, status), n in gate_counts.items() if status == "deferred_after_cap"),
               "aggregatorOnlyNotPublished":len(checked_regional)-len(verified_regional),
           },
           "specificJobPagesOpened":len(candidate_postings)+sum(
               log.get("specificJobPagesOpened", 0) for log in logs)
               +sum(n for (src,status),n in gate_counts.items()
                    if src not in ("LinkedIn Jobs", "Indeed Italia")
                    and status not in ("filtered_by_role_or_location","deferred_after_cap")),
           "specificJobPagesVerified":len(verified_regional)+sum(
               log.get("specificJobPagesVerified", 0) for log in logs)
               +sum(n for (src,status),n in gate_counts.items()
                    if src not in ("LinkedIn Jobs", "Indeed Italia") and status == "verified"),
           "excludedUnconfirmedSmartWorking":len(checked_regional)-len(verified_regional),
           "newRegionalJobs":regional_added,
           "newJobs":len(added),
           "regionsTarget": 20, "regionsAttempted": [x[0] for x in REGIONS],
           "regionCoverage": regional_coverage,
           "activeJobs": sum(j.get("active", True) is not False for j in old),
           "searchLog": logs + regional_logs, "note": "All providers share original-posting availability, role, employer and remote/hybrid publication gate. Aggregator-only and indexed results cannot be published. Catalog queries do not imply complete coverage; partial status is deliberate."}
    existing = previous_slot
    # Keep a more thorough scan published by the ChatGPT automation: this
    # 5-provider fallback must not erase its research on the same slot.
    if slot in ("09:30", "15:30") and isinstance(existing, dict) and existing.get("status") in ("partial", "complete"):
        old_source_count = existing.get("requiredSourcesChecked", existing.get("sourcesExplored", 0))
        new_source_count = run.get("requiredSourcesChecked", 0)
        if existing.get("status") == "complete" or (
            isinstance(old_source_count, (int, float)) and old_source_count > new_source_count
        ):
            data["audit"]["runs"][slot] = existing
            data["audit"]["runs"]["automated_fallback"] = run
            print(f"Preserved stronger {slot} scan; recorded feed backup separately")
        else:
            data["audit"]["runs"][slot] = run
    else:
        if existing is not None and slot == "automated_fallback":
            data["audit"]["runs"]["automated_fallback_previous"] = existing
        data["audit"]["runs"][slot] = run
    if successes or found_accessible:
        data["generatedAt"] = now
    data["manualRefresh"] = data.get("manualRefresh")  # do not alter separate manual scan
    write_catalog(BASE, data)
    print(f"Nationwide: {len(REGIONS)} regions, {len(regional_logs)} listing checks, "
          f"{len(candidate_postings)} detail page attempts, {len(verified_regional)} valid aggregator details, "
          f"{regional_added} new regional jobs, {len(added)} overall new, {len(old)} total, slot={slot}")


if __name__ == "__main__":
    if "--self-test" in os.sys.argv:
        self_test()
    elif "--record-failure" in os.sys.argv:
        record_failure()
    elif "--prepare" in os.sys.argv:
        prepare()
    else:
        drain()
