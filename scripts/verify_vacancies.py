"""Uniform publication gate for jobs from ANY source.

Index pages, RSS hits and search-result cards are discovery only. A new vacancy
needs an individual, accessible detail (or public single-posting API response),
matching title/employer, active status and explicit remote/hybrid evidence.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
import html
import json
import re
from urllib.parse import urlparse, quote
from urllib.request import Request, urlopen

from jobsora_extract import ROLE, clean, norm
from linkedin_search import MODE, NEGATIVE, EXPIRED, _json_ld_jobs

GENERIC_PATHS = {"", "jobs", "job", "careers", "search", "results", "offerte", "lavoro"}
BLOCKED = re.compile(r"(?:captcha|access denied|verify you are human|too many requests)", re.I)
ON_SITE = re.compile(r"\b(?:solo|esclusivamente)\s+in\s+(?:sede|presenza)\b", re.I)

def _role(job):
    title = str(job.get("title") or "")
    return bool(ROLE.search(title) or re.search(
        r"\b(?:sales operations|revenue operations|event coordinator|event specialist|"
        r"MICE|inside sales|customer operations|customer success|"
        r"segreteria commerciale|amministrazione commerciale|ufficio commerciale|"
        r"supporto alle vendite|supporto amministrativo|contract administrator|"
        r"vendor administration|proposal specialist|gestione ordini)\b",
        title, re.I))

def _mode(desc, structured=None):
    if NEGATIVE.search(desc or "") or ON_SITE.search(desc or ""):
        return False
    if MODE.search(desc or ""):
        return True
    return bool(structured and str(structured.get("jobLocationType") or "").upper() == "TELECOMMUTE")

def _eligible_country(node):
    location = node.get("jobLocation") or {}
    if isinstance(location, list):
        location = location[0] if location else {}
    address = location.get("address") or {} if isinstance(location, dict) else {}
    country = address.get("addressCountry") if isinstance(address, dict) else ""
    if isinstance(country, dict):
        country = country.get("name") or ""
    if str(country or "").lower() in ("it", "ita", "italia", "italy"):
        return True
    elig = clean(node.get("applicantLocationRequirements"))
    return bool(re.search(r"\b(?:Italia|Italy|European Union|EU|Europe)\b", elig, re.I))

def _matching(candidate, found_title, found_company):
    a = norm(candidate.get("title", ""))
    b = norm(found_title)
    c = norm(candidate.get("company", ""))
    d = norm(found_company)
    if not a or not b or not c or not d:
        return False
    return SequenceMatcher(None, a, b).ratio() >= 0.68 and (
        c == d or c in d or d in c or SequenceMatcher(None, c, d).ratio() >= 0.70)

def _fetch_html(url):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; AliceJobRadar/6.48; vacancy verification)",
        "Accept": "text/html,application/xhtml+xml", "Accept-Language": "it-IT,it;q=0.9,en;q=0.7",
    })
    with urlopen(req, timeout=9) as response:
        if response.status != 200:
            raise ValueError("HTTP " + str(response.status))
        final_url = response.geturl()
        body = response.read(550000).decode("utf-8", "replace")
    return final_url, body

def _fetch_json(url):
    req = Request(url, headers={
        "User-Agent": "AliceJobRadar/6.48 (+public-single-job-verification)",
        "Accept": "application/json",
    })
    with urlopen(req, timeout=10) as response:
        if response.status != 200:
            raise ValueError("HTTP " + str(response.status))
        return json.loads(response.read(1500000).decode("utf-8"))

def _smartrecruiters(candidate, raw):
    company = raw.get("company") or {}
    ident = str(raw.get("id") or "")
    account = str(company.get("identifier") or "")
    if not (ident.isdigit() and account):
        return "unconfirmed", "missing single-posting identifier"
    url = "https://api.smartrecruiters.com/v1/companies/" + quote(account) + "/postings/" + ident
    try:
        detail = _fetch_json(url)
    except Exception as exc:
        return "unavailable", str(exc)[:100]
    if str(detail.get("id") or "") != ident:
        return "unconfirmed", "posting identifier mismatch"
    if str(detail.get("status") or "").lower() in ("inactive", "closed", "archived", "deleted"):
        return "expired", "individual posting no longer open"
    if str(detail.get("visibility") or "PUBLIC") != "PUBLIC":
        return "unconfirmed", "posting is not public"
    loc = detail.get("location") or {}
    country = str(loc.get("country") or "").lower()
    if country != "it":
        return "unconfirmed", "Italian location not confirmed"
    if not (loc.get("remote") is True or loc.get("hybrid") is True):
        return "unconfirmed", "remote/hybrid not confirmed in individual posting"
    name = clean(detail.get("name"))
    employer = clean((detail.get("company") or {}).get("name"))
    if not _matching(candidate, name, employer):
        return "unconfirmed", "posting title/company mismatch"
    return "verified", url

def _html_detail(candidate):
    url = candidate["url"]
    try:
        final_url, body = _fetch_html(url)
    except Exception as exc:
        return "unavailable", str(exc)[:100]
    if urlparse(final_url).path.strip("/").lower() in GENERIC_PATHS:
        return "unconfirmed", "redirected to generic listing page"
    if BLOCKED.search(body[:3000]):
        return "unavailable", "site challenges automation"
    if EXPIRED.search(body[:120000]):
        return "expired", "individual vacancy is closed"
    schema = _json_ld_jobs(body)
    for job in schema:
        expiry = str(job.get("validThrough") or "9999")[:10]
        if expiry < date.today().isoformat():
            continue
        title = clean(job.get("title"))
        employer = clean((job.get("hiringOrganization") or {}).get("name"))
        if not _matching(candidate, title, employer):
            continue
        if not _eligible_country(job):
            return "unconfirmed", "no Italy/EU eligibility on original posting"
        description = clean(job.get("description"))
        if not _mode(description, job):
            return "unconfirmed", "remote/hybrid arrangement not documented"
        return "verified", final_url

    # Some official employer boards contain no JSON-LD. Require both title
    # and employer to occur on the individual page, plus explicit modality.
    text = clean(body)
    if not (norm(candidate["title"]) in norm(text) and norm(candidate["company"]) in norm(text)):
        return "unconfirmed", "original detail missing matching title/company"
    if not _mode(text):
        return "unconfirmed", "work arrangement not confirmed in original detail"
    return "verified", final_url

def verify_candidate(candidate, kind, raw):
    """Return (status, evidence): verified only after single-posting proof."""
    if not isinstance(candidate, dict):
        return "unconfirmed", "not a vacancy"
    url = candidate.get("url") or ""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path.strip("/").lower() in GENERIC_PATHS:
        return "unconfirmed", "not a valid individual vacancy URL"
    if not (candidate.get("company") and candidate.get("title") and _role(candidate)):
        return "unconfirmed", "role, title, or employer not confirmed"
    if not candidate.get("remote") or not candidate.get("workMode"):
        return "unconfirmed", "remote/hybrid not confirmed"
    if kind == "smartrecruiters":
        return _smartrecruiters(candidate, raw)
    if kind in ("linkedin", "employer"):
        # These adapters opened the individual posting, parsed the full
        # description and confirmed its status and modality already.
        desc = str(raw.get("details") or "")
        if not (_mode(desc) or raw.get("telecommuteEvidence") is True):
            return "unconfirmed", "source adapter lacks remote/hybrid evidence"
        return "verified", candidate["url"]
    # Generic feeds/aggregators are discovery only until the actual detail
    # page has been opened. No assumption that a feed entry is still live.
    return _html_detail(candidate)

def verify_many_mapped(entries, max_per_source=35):
    """Each entry: (source,kind,raw,mapped_job); never assert 263 sources checked."""
    counters = Counter()
    to_check = []
    per_source = Counter()
    for source, kind, raw, candidate in entries:
        if candidate is None:
            counters[(source,"filtered_by_role_or_location")] += 1
            continue
        if per_source[source] >= max_per_source:
            counters[(source,"deferred_after_cap")] += 1
            continue
        per_source[source] += 1
        to_check.append((source, kind, raw, candidate))
    def run(item):
        source, kind, raw, candidate = item
        status, evidence = verify_candidate(candidate, kind, raw)
        if status == "verified":
            candidate["verificationLevel"] = "individual_original_posting"
            candidate["verificationEvidenceUrl"] = evidence
            candidate["checks"] = [
                "Annuncio individuale, azienda, ruolo e smart working verificati alla fonte.",
                "Annuncio consultato durante la scansione; ricontrollare prima di candidarsi.",
            ]
        return source, status, candidate if status == "verified" else None
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(run, to_check))
    jobs = []
    for source, status, candidate in results:
        counters[(source,status)] += 1
        if candidate:
            jobs.append(candidate)
    log = [
        {"source": src, "method": "universal_individual_vacancy_gate",
         "checkedAt": datetime.now(timezone.utc).isoformat(),
         "outcome": ("success: verified original vacancy" if status=="verified" else
                     "unavailable: individual detail not accessible" if status=="unavailable" else
                     "excluded: " + status),
         "status":status, "candidateCount":number,
         "specificJobPagesVerified":number if status=="verified" else 0}
        for (src,status),number in sorted(counters.items())
    ]
    return jobs, log, counters

def self_test():
    candidate = {"title":"Bid Specialist", "company":"Esempio", "url":"https://esempio.it/jobs/1234",
                 "workMode":"Ibrido", "remote":True}
    assert _role(candidate)
    assert _role({**candidate, "title":"Amministrazione Commerciale"})
    assert not _role({**candidate, "title":"Programmatore Java"})
    assert _mode("Sono previsti due giorni di smart working a settimana")
    assert not _mode("Esclusivamente in sede, senza smart working")
    assert not _matching(candidate, "Developer Java", "Esempio")
    assert verify_candidate({**candidate,"url":"https://esempio.it/careers"}, "employer",
                            {"details":"lavoro ibrido"})[0] != "verified"
    assert verify_candidate(candidate,"employer",{"details":"lavoro ibrido"})[0]=="verified"
    assert verify_candidate(candidate,"employer",{"details":"Descrizione", "telecommuteEvidence":True})[0]=="verified"
    print("Universal original-vacancy gate and exclusion rules: OK")

if __name__=="__main__":
    self_test()
