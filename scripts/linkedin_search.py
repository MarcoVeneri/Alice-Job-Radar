"""Primary discovery on public LinkedIn and Indeed Italy vacancy pages.

Each provider is queried independently. An index result is never a verified vacancy:
we require an individual, still-open detail page with explicit remote/hybrid evidence.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import html
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from jobsora_extract import clean, field
from tuscany_scope import PROVINCES, in_tuscany

TERMS = (
    "tender office", "ufficio gare", "gare e appalti", "tender specialist",
    "bid proposal", "proposal specialist", "responsabile ufficio gare", "tender contract",
    "sales support", "segreteria commerciale", "back office commerciale", "sales operations",
    "PMO", "project coordinator", "order management",
)
AREAS = ("Toscana, Italia",) + tuple(p + ", Toscana, Italia" for p in PROVINCES)
MODE = re.compile(
    r"\b(?:smart[\s-]?working|lavoro\s+(?:ibrido|da remoto|agile)|"
    r"modalit[aà]\s+(?:di\s+lavoro\s+)?ibrid[ao]|"
    r"hybrid(?:\s+(?:work(?:ing)?|model|role))?|remote(?:\s+work(?:ing)?)?|"
    r"work\s+from\s+home|home\s+office|"
    r"(?:uno|due|tre|quattro|[1-5])\s+giorn[io]\s+(?:a settimana\s+)?"
    r"(?:di\s+)?smart[\s-]?working)\b", re.I,
)
NEGATIVE = re.compile(
    r"(?:\b(?:non|no|senza|esclus[oa])\b.{0,45}"
    r"(?:smart[\s-]?working|ibrid|hybrid|remot)|"
    r"(?:smart[\s-]?working|remoto|hybrid).{0,24}"
    r"non\s+(?:previst[oa]|possibile|consentit[oa])|"
    r"(?:esclusivamente|solo)\s+in\s+(?:sede|presenza))", re.I,
)
EXPIRED = re.compile(
    r"(?:annuncio\s+di\s+lavoro\s+scaduto|no longer accepting applications|"
    r"non\s+accetta\s+pi[uù]\s+candidature|posizione\s+non\s+pi[uù]\s+disponibile)", re.I,
)
JOBKEY = re.compile(
    r"(?:data-jk\s*=\s*['\"]|['\"](?:jobkey|jk)['\"]\s*:\s*['\"]|[?&]jk=)"
    r"([0-9a-f]{12,})", re.I,
)
LI_ID = re.compile(
    r"(?:urn:li:jobPosting:|/jobs/view/(?:[^/\"'?\s]*?-)?)(\d{9,})", re.I,
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def page(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AliceJobRadar/6.48; public vacancy discovery)",
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.6",
        "Accept": "text/html,application/xhtml+xml",
    }
    with urlopen(Request(url, headers=headers), timeout=10) as response:
        return response.read(600000).decode("utf-8", "replace")


def _json_ld_jobs(body):
    jobs = []
    for raw in re.findall(
        r"<script\b[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
        body, re.I | re.S,
    ):
        try:
            root = json.loads(html.unescape(raw))
        except (ValueError, TypeError):
            continue
        queue = [root]
        while queue:
            node = queue.pop()
            if isinstance(node, list):
                queue.extend(node)
            elif isinstance(node, dict):
                if node.get("@type") == "JobPosting" or (
                    isinstance(node.get("@type"), list)
                    and "JobPosting" in node["@type"]
                ):
                    jobs.append(node)
                if "@graph" in node:
                    queue.append(node["@graph"])
    return jobs


def _linkedin_card_ids(body):
    # LinkedIn lists Italian cities (Firenze, Milano, etc.), not necessarily
    # the literal word "Italia". Search geography is already constrained.
    out = {}
    for block in re.findall(r"<li\b[^>]*>(.*?)</li>", body, re.I | re.S):
        match = LI_ID.search(block)
        if not match:
            continue
        location = field(block, "span", "job-search-card__location")
        out[match.group(1)] = location or "Italia (località da verificare)"
    return out


def _indeed_card_ids(body):
    return list(dict.fromkeys(JOBKEY.findall(body)))


def _verified_mode(description):
    match = MODE.search(description or "")
    return match if match and not NEGATIVE.search(description or "") else None


def _linked_job(item):
    ident, listed_location = item
    try:
        body = page("https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/" + ident)
    except (OSError, ValueError):
        return None
    if EXPIRED.search(body):
        return None
    desc = field(body, "div", "show-more-less-html__markup")
    if not desc:
        desc = field(body, "div", "description__text")
    title = field(body, "h2", "topcard__title") or field(body, "h2", "top-card-layout__title")
    company = field(body, "a", "topcard__org-name-link") or field(body, "a", "top-card-layout__first-subline")
    # Some public detail templates expose JSON-LD rather than topcard fields.
    jobs = _json_ld_jobs(body)
    if jobs:
        first = jobs[0]
        desc = desc or clean(first.get("description"))
        title = title or clean(first.get("title"))
        company = company or clean((first.get("hiringOrganization") or {}).get("name"))
        # The indexed search area is not the actual job location. Prefer the
        # original posting's structured location and refuse known non-IT jobs.
        location = first.get("jobLocation") or {}
        if isinstance(location, list):
            location = location[0] if location else {}
        address = location.get("address") or {} if isinstance(location, dict) else {}
        country = address.get("addressCountry") if isinstance(address, dict) else ""
        if isinstance(country, dict):
            country = country.get("name") or ""
        if country and str(country).lower() not in ("it", "ita", "italia", "italy"):
            eligible = clean(first.get("applicantLocationRequirements"))
            if not re.search(r"\\b(?:Italia|Italy|Europe|EU)\\b", eligible, re.I):
                return None
        if isinstance(address, dict):
            listed_location = clean(address.get("addressLocality") or address.get("addressRegion")) or listed_location
    mode = _verified_mode(desc)
    if not (title and company and mode and in_tuscany(listed_location)):
        return None
    return {
        "title": title, "company": company, "place": listed_location,
        "url": "https://www.linkedin.com/jobs/view/" + ident,
        "mode": "Smart working/ibrido documentato",
        "details": desc[max(0, mode.start()-110):mode.end()+160],
    }


def _indeed_job(key):
    url = "https://it.indeed.com/viewjob?jk=" + key
    try:
        body = page(url)
    except (OSError, ValueError):
        return None
    if EXPIRED.search(body[:120000]):
        return None
    for job in _json_ld_jobs(body):
        if str(job.get("validThrough") or "9999")[:10] < date.today().isoformat():
            continue
        desc = clean(job.get("description"))
        mode = _verified_mode(desc)
        if not mode:
            continue
        location = job.get("jobLocation") or {}
        if isinstance(location, list):
            location = location[0] if location else {}
        address = location.get("address") or {}
        country = address.get("addressCountry") or ""
        if isinstance(country, dict):
            country = country.get("name") or ""
        # Never publish an international vacancy without explicit Italy eligibility.
        if str(country).strip().lower() not in ("it", "ita", "italia", "italy"):
            eligible = clean(job.get("applicantLocationRequirements"))
            if not re.search(r"\b(?:Italia|Italy)\b", eligible, re.I):
                continue
        company = clean((job.get("hiringOrganization") or {}).get("name"))
        title = clean(job.get("title"))
        if not (company and title and in_tuscany(clean(address.get("addressLocality")) or clean(address.get("addressRegion")))):
            continue
        return {
            "title": title, "company": company,
            "place": clean(address.get("addressLocality")) or "Italia",
            "url": url, "mode": "Smart working/ibrido documentato",
            "details": desc[max(0,mode.start()-110):mode.end()+160],
        }
    return None


def _search_linkedin(pair):
    term, area = pair
    params = {"keywords": term, "location": area, "start": 0, "sortBy": "DD"}
    url = ("https://www.linkedin.com/jobs-guest/jobs/api/"
           "seeMoreJobPostings/search?" + urlencode(params))
    log = dict(source="LinkedIn Jobs", query=term, area=area, method="direct_public_cards",
               checkedAt=_now(), evidenceUrls=[url])
    try:
        body = page(url)
        found = _linkedin_card_ids(body)
        for start in range(25, 100, 25):
            if not found or len(found) < start:
                break
            next_url = url.rsplit("?", 1)[0] + "?" + urlencode({**params, "start": start})
            log["evidenceUrls"].append(next_url)
            try:
                more = _linkedin_card_ids(page(next_url))
            except (OSError, ValueError) as exc:
                log["paginationError"] = str(exc)[:140]
                break
            if not set(more) - set(found):
                break
            found.update(more)
        log["outcome"] = ("success: " + str(len(found)) + " public vacancy cards"
                          if found else "unconfirmed: no readable vacancy cards")
        log["candidateLinksFound"] = len(found)
        return log, found
    except (OSError, ValueError) as exc:
        log["outcome"] = "unavailable: " + str(exc)[:140]
        return log, {}


def _search_indeed(pair):
    term, area = pair
    url = "https://it.indeed.com/jobs?" + urlencode({
        "q": term, "l": area.replace(", Italia", ""),
        "sort": "date",
    })
    log = dict(source="Indeed Italia", query=term, area=area, method="direct_public_cards",
               checkedAt=_now(), evidenceUrls=[url])
    try:
        body = page(url)
        keys = _indeed_card_ids(body)
        log["outcome"] = ("success: " + str(len(keys)) + " public vacancy cards"
                          if keys else "unconfirmed: no readable vacancy cards")
        log["candidateLinksFound"] = len(keys)
        return log, keys
    except (OSError, ValueError) as exc:
        log["outcome"] = "unavailable: " + str(exc)[:140]
        return log, []


def discover(previous_logs=()):
    """Search both major portals on every run, regardless of the other's result."""
    pairs = [(term, area) for term in TERMS for area in AREAS]
    linkedin = {}
    indeed = []
    logs = []
    # Search two portals independently: no success/previous-error shortcuts.
    with ThreadPoolExecutor(max_workers=6) as pool:
        for log, cards in pool.map(_search_linkedin, pairs):
            logs.append(log)
            linkedin.update(cards)
    with ThreadPoolExecutor(max_workers=6) as pool:
        for log, keys in pool.map(_search_indeed, pairs):
            logs.append(log)
            indeed.extend(keys)
    # Indexed fallback is independent of guest-HTML access. Even a public
    # search with readable cards is not exhaustive: discover additional posting
    # identifiers for each role cluster and Tuscany/Valdarno/Italy.
    from indexed_jobs import discover_indexed
    indexed_li, indexed_indeed, indexed_logs = discover_indexed()
    for ident, area in indexed_li.items():
        linkedin.setdefault(ident, area)
    indeed.extend(indexed_indeed)
    logs.extend(indexed_logs)
    linkedin_items = list(linkedin.items())
    indeed_keys = list(dict.fromkeys(indeed))
    with ThreadPoolExecutor(max_workers=4) as pool:
        linked = [job for job in pool.map(_linked_job, linkedin_items) if job]
    with ThreadPoolExecutor(max_workers=4) as pool:
        verified_indeed = [job for job in pool.map(_indeed_job, indeed_keys) if job]
    logs.append({
        "source": "LinkedIn Jobs", "method": "individual_detail_verification",
        "checkedAt": _now(), "candidateLinksFound": len(linkedin),
        "specificJobPagesOpened": len(linkedin_items),
        "indexedFallback": bool(indexed_logs),
        "specificJobPagesVerified": len(linked),
        "outcome": "success: verified " + str(len(linked)) + " individual vacancies"
                   if linked else "unconfirmed: no verified hybrid/remote vacancy",
    })
    logs.append({
        "source": "Indeed Italia", "method": "individual_detail_verification",
        "checkedAt": _now(), "candidateLinksFound": len(set(indeed)),
        "specificJobPagesOpened": len(indeed_keys),
        "specificJobPagesVerified": len(verified_indeed),
        "outcome": "success: verified " + str(len(verified_indeed)) + " individual vacancies"
                   if verified_indeed else "unconfirmed: no verified hybrid/remote vacancy",
    })
    return (
        [("LinkedIn Jobs", "linkedin", job) for job in linked]
        + [("Indeed Italia", "employer", job) for job in verified_indeed],
        logs,
    )


def self_test():
    assert _linkedin_card_ids(
        '<li><a href="/jobs/view/bid-specialist-at-foo-4491829304"></a>'
        '<span class="job-search-card__location">Firenze, Toscana</span></li>'
    ) == {"4491829304": "Firenze, Toscana"}
    assert _indeed_card_ids(
        '<div data-jk="51921db8917b2edf"></div><a href="/viewjob?jk=abcdefabcdef1234">'
    ) == ["51921db8917b2edf", "abcdefabcdef1234"]
    assert _verified_mode("Possibilità di smart working per due giorni")
    assert _verified_mode("Solo in sede, senza smart working") is None
    from indexed_jobs import self_test as indexed_self_test
    indexed_self_test()
    assert len(AREAS) == 11 and 'Italia' not in AREAS
    print("LinkedIn city parsing and independent Indeed discovery: OK")


if __name__ == "__main__":
    self_test()
