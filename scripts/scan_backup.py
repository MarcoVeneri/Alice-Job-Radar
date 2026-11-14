#!/usr/bin/env python3
"""Alice Radar: fallback scanner of public, documented job feeds (no credentials)."""
from __future__ import annotations

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
    r"sales\s+(?:support|operation|enablement|administrator|coordinator)|"
    r"commercial\s+(?:support|operation|coordinator|assistant)|"
    r"revenue\s+operation|order\s+management|procurement\s+(?:support|coordinator)|"
    r"contract\s+(?:support|administrator|coordinator)|"
    r"customer\s+(?:operation|support|success)|back[\s-]?office|"
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


def feed_rows():
    sources = [
        ("Jobicy", "https://jobicy.com/api/jobs?count=200&geo=europe", "jobicy"),
        ("Jobicy-anywhere", "https://jobicy.com/api/jobs?count=200&geo=anywhere", "jobicy"),
        ("Arbeitnow", "https://www.arbeitnow.com/api/job-board-api?page=1", "arbeitnow"),
        ("Remotive", "https://remotive.com/api/remote-jobs?limit=200", "remotive"),
    ]
    logs, rows = [], []
    for name, url, kind in sources:
        start = datetime.now(timezone.utc).isoformat()
        try:
            data = get_json(url)
            entries = data.get("jobs", data.get("data", []))
            if not isinstance(entries, list):
                raise ValueError("Feed did not return a jobs list")
            logs.append({"source": name, "method": "public_feed_api", "checkedAt": start,
                         "outcome": f"success: {len(entries)} raw postings",
                         "evidenceUrls": [url]})
            for raw in entries:
                if isinstance(raw, dict):
                    rows.append((name, kind, raw))
        except Exception as exc:
            logs.append({"source": name, "method": "public_feed_api", "checkedAt": start,
                         "outcome": "unavailable: " + str(exc)[:180], "evidenceUrls": [url]})
        time.sleep(0.4)
    return rows, logs


REGIONAL_ROLES = ("ufficio-gare", "back-office-commerciale", "pmo", "sales-operations", "project-coordinator")

def _check_listing(task):
    """A listing-page response confirms only a working regional query, not any vacancy."""
    region, slug, role = task
    url = f"https://it.jobsora.com/lavoro-{role}-{slug}"
    stamp = datetime.now(timezone.utc).isoformat()
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; AliceJobRadar/6.40)",
                          "Accept": "text/html"})
        with urllib.request.urlopen(request, timeout=7) as res:
            page = res.read(160_000).decode("utf-8", "replace")
            status = res.status
        if status == 200 and "<html" in page.lower() and "jobsora" in page.lower():
            outcome = "index_page_accessible; no individual vacancy verified from listing"
        else:
            outcome = f"invalid_or_unrelated_listing_{status}"
    except Exception as exc:
        outcome = "unavailable: " + str(exc)[:130]
    return {"source": "Jobsora regional indexed listings",
            "method": "regional_index_discovery_only",
            "region": region, "query": role, "checkedAt": stamp,
            "outcome": outcome, "evidenceUrls": [url]}

def region_discovery():
    """Five distinct keyword searches across all 20 regions (100 attempted URLs).
    Failed sources are logged; failures cannot masquerade as successful searches.
    """
    tasks = [(region, slug, role) for region, slug in REGIONS for role in REGIONAL_ROLES]
    with ThreadPoolExecutor(max_workers=5) as pool:
        logs = list(pool.map(_check_listing, tasks))
    coverage = {}
    for region, _ in REGIONS:
        items = [x for x in logs if x["region"] == region]
        accessible = sum(x["outcome"].startswith("index_page_accessible") for x in items)
        coverage[region] = {
            "attempted": len(items), "indexPagesAccessible": accessible,
            "unavailable": len(items) - accessible,
            "status": "indexed_search_only_not_vacancy_verified"
        }
    return coverage, logs


def mapped_job(source, kind, raw, today, now):
    if kind == "jobicy":
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
    if not (title and company and url.startswith("https://") and ROLE.search(title)):
        return None
    if remote:
        if place and not LOC.search(place):
            return None
    elif not LOC.search(place):
        return None
    parsed = urllib.parse.urlparse(url)
    if parsed.path.strip("/") in ("", "jobs", "careers", "remote-jobs"):
        return None
    key = hashlib.sha256(url.split("?")[0].encode("utf-8")).hexdigest()[:18]
    category = ("Tender" if re.search(r"bid|tender|proposal", title, re.I) else
                "Project Support / PMO" if re.search(r"pmo|project", title, re.I) else
                "Sales Support")
    score = 8.6 if re.search(r"firenze|toscana|italia|italy", place, re.I) else 7.5
    source_note = "Attiva nel feed API al momento del controllo; verificare requisiti e disponibilità prima della candidatura."
    return {"id": f"feed-{key}", "company": company, "title": title,
            "location": place or "Remote (requisiti geografici da verificare)",
            "category": category, "url": url, "workMode": "Da remoto" if remote else "Da verificare",
            "contract": contract or "Da verificare", "salary": salary or "Non indicata",
            "remote": bool(remote), "active": True, "date": today, "firstSeenAt": now,
            "firstSeenRun": "Scansione automatica fallback", "verifiedAt": now,
            "source": source, "summary": details[:450],
            "checks": [source_note, f"Fonte: {source}. Lingue e località da verificare."],
            "score": score}


def main():
    rome = datetime.now(ROME)
    today = rome.date().isoformat()
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    # GitHub runs in UTC; scheduled times can be delayed, and summer/winter CRON
    # requires a redundant UTC slot. Never let the redundant trigger overwrite a slot.
    scheduled = os.environ.get("GITHUB_EVENT_NAME") == "schedule"
    mins = rome.hour * 60 + rome.minute
    if scheduled:
        if 570 <= mins <= 624:  # 09:30-10:24 Italy
            slot = "09:30"
        elif 930 <= mins <= 984:  # 15:30-16:24 Italy
            slot = "15:30"
        else:
            print(f"Skipping redundant UTC schedule at {rome.isoformat()}")
            return
    else:
        slot = "automated_fallback"
    data = json.loads(BASE.read_text(encoding="utf-8"))
    previous = data.get("audit")
    if not isinstance(previous, dict) or previous.get("date") != today:
        if isinstance(previous, dict) and previous.get("date"):
            hist = data.setdefault("auditHistory", [])
            if not any(x.get("date") == previous["date"] for x in hist if isinstance(x, dict)):
                hist.append(previous)
        data["audit"] = {"date": today, "runs": {}}
    catalog_file = Path("data/source_catalog.json")
    try:
        required_sources_total = len(json.loads(catalog_file.read_text(encoding="utf-8")).get("sources", [])) or 238
    except (OSError, ValueError, TypeError):
        required_sources_total = 238
    rows, logs = feed_rows()
    regional_coverage, regional_logs = region_discovery()
    successes = [x for x in logs if x["outcome"].startswith("success:")]
    found_accessible = any(x["indexPagesAccessible"] for x in regional_coverage.values())
    if not successes and not found_accessible:
        print("All national sources unavailable: recording a failed audit honestly")
    old = data.get("jobs", [])
    ids = {str(j.get("id")) for j in old}
    links = {str(j.get("url", "")).split("?")[0].lower() for j in old}
    added = []
    for source, kind, raw in rows:
        candidate = mapped_job(source, kind, raw, today, now)
        if candidate is None:
            continue
        link = candidate["url"].split("?")[0].lower()
        if candidate["id"] in ids or link in links:
            continue
        old.insert(0, candidate)
        added.append(candidate)
        ids.add(candidate["id"])
        links.add(link)
    data["jobs"] = old
    run = {"scheduledFor": now, "startedAt": now, "completedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
           "status": "partial" if (successes or found_accessible) else "failed", "coverageMode": "national_20_region_discovery_plus_verified_public_feeds",
           "requiredSourcesTotal": required_sources_total, "requiredSourcesChecked": len(successes),
           "sourcesExplored": len(successes) + int(any(x["indexPagesAccessible"] for x in regional_coverage.values())), "sourcesChecked": [x["source"] for x in successes] + (["Jobsora regional indexed listings"] if any(x["indexPagesAccessible"] for x in regional_coverage.values()) else []),
           "directSourcesChecked": [], "siteRestrictedSourcesChecked": [],
           "indexedFallbackSourcesChecked": [x["source"] for x in successes],
           "sourcesUnavailable": [x["source"] for x in logs if not x["outcome"].startswith("success:")],
           "queriesRun": len(logs) + len(regional_logs), "newJobs": len(added),
           "regionsTarget": 20, "regionsAttempted": [x[0] for x in REGIONS],
           "regionCoverage": regional_coverage,
           "activeJobs": sum(j.get("active", True) is not False for j in old),
           "searchLog": logs + regional_logs, "note": "Nationwide 20-region indexed search attempts plus public feeds; regional listing searches do NOT verify individual vacancies. Partial coverage, not a full scan of all providers."}
    existing = data["audit"].setdefault("runs", {}).get(slot)
    if existing is not None and slot == "automated_fallback":
        data["audit"]["runs"]["automated_fallback_previous"] = existing
    data["audit"]["runs"][slot] = run
    if successes or found_accessible:
        data["generatedAt"] = now
    data["manualRefresh"] = data.get("manualRefresh")  # do not alter separate manual scan
    BASE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Fallback: {len(successes)} sources checked, {len(added)} new, {len(old)} total, slot={slot}")


if __name__ == "__main__":
    main()
