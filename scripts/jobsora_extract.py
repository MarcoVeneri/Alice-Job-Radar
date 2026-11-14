#!/usr/bin/env python3
"""Jobsora public-listing verifier: never treats search pages as verified offers."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from difflib import SequenceMatcher
import html
import re
import unicodedata
import urllib.request

ROLE = re.compile(
    r"\b(?:ufficio\s+gare|gare\s+(?:e\s+)?appalti|tender|proposal|"
    r"bid\s+(?:specialist|manager|coordinator)|back[\s-]?office|"
    r"pmo|project\s+(?:support|coordinator|administrator|operations)|"
    r"sales\s+(?:support|operations|administration|coordinator)|"
    r"commercial\s+(?:operations|support|administration|coordinator)|"
    r"gestione\s+ordini|order\s+management|supporto\s+commerciale|"
    r"segreteria\s+commerciale|procurement\s+support)\b", re.I
)

def clean(value):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).split())

def norm(value):
    raw = unicodedata.normalize("NFKD", str(value or "")).encode("ascii","ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", raw)).strip()

def field(block, tag, cls):
    pattern = rf'<{tag}\b[^>]*class="[^"]*{re.escape(cls)}[^"]*"[^>]*>(.*?)</{tag}>'
    m = re.search(pattern, block, re.S | re.I)
    return clean(m.group(1)) if m else ""

def listing_candidates(page, region, limit=3):
    out = []
    for m in re.finditer(r'<article\b[^>]*data-id="(\d+)"[^>]*>.*?</article>',page,re.I|re.S):
        block = m.group(0)
        title = field(block,"h2","c-job-title")
        company = field(block,"div","c-job-company__name")
        location = field(block,"div","c-job-location__city")
        summary = field(block,"p","c-job-card__description")
        if not (title and company and location and ROLE.search(title)):
            continue
        if norm(company) in ("riservato","altro","confidenziale","anonimo"):
            continue
        out.append({"id":m.group(1),"title":title,"company":company,
                    "location":location,"region":region,"summary":summary,
                    "url":f"https://it.jobsora.com/offerta-{m.group(1)}?source=1"})
        if len(out)>=limit:
            break
    return out

def verify_one(candidate,today,stamp):
    """Check individual Jobsora detail; original employer candidability remains unverified."""
    try:
        req=urllib.request.Request(candidate["url"],
            headers={"User-Agent":"Mozilla/5.0 (compatible; AliceJobRadar/6.41)"})
        with urllib.request.urlopen(req,timeout=9) as response:
            if response.status != 200 or "/offerta-" not in response.geturl():
                return None
            body=response.read(125_000).decode("utf-8","replace")
        match=re.search(r"<h1\b[^>]*>(.*?)</h1>",body,re.I|re.S)
        title=clean(match.group(1)) if match else ""
        if not title or SequenceMatcher(None,norm(title),norm(candidate["title"])).ratio() < .70:
            return None
        if re.search(r"annuncio (?:non pi[uù] disponibile|scaduto)|offerta di lavoro scaduta",body,re.I):
            return None
        if not re.search(r"candidati|candidatura|apply",body,re.I):
            return None
        role=candidate["title"]
        category=("Tender" if re.search(r"gare|appalt|tender|bid|proposal",role,re.I)
                  else "Project Support / PMO" if re.search(r"pmo|project",role,re.I)
                  else "Sales Support")
        return {"id":"jobsora-"+candidate["id"],"title":role,
                "company":candidate["company"],"location":candidate["location"],
                "region":candidate["region"],"url":candidate["url"],
                "category":category,"summary":candidate["summary"][:420],"score":7.7,
                "remote":False,"workMode":"Da verificare","contract":"Da verificare",
                "salary":"Non indicata","active":True,"date":today,
                "firstSeenAt":stamp,"firstSeenRun":"Scansione automatica nazionale",
                "verifiedAt":stamp,"source":"Jobsora (aggregatore)",
                "verificationLevel":"aggregator_detail",
                "checks":["Annuncio specifico raggiungibile su Jobsora: HTTP 200, titolo corrispondente.",
                    "L'aggregatore non certifica che l'annuncio sia ancora candidabile sul sito originale.",
                    "Modalità, sede effettiva, retribuzione e condizioni da confermare con l'azienda."]}
    except Exception:
        return None

def verify_many(candidates,today,stamp):
    if not candidates:
        return []
    with ThreadPoolExecutor(max_workers=7) as executor:
        results=list(executor.map(lambda c:verify_one(c,today,stamp),candidates))
    return [x for x in results if x is not None]

def self_test():
    page = ('<article data-id="123">'
        '<h2 class="c-job-title"><a>Back Office Commerciale</a></h2>'
        '<div class="c-job-location__city">Prato</div>'
        '<div class="c-job-company__name">Azienda Test</div>'
        '<p class="c-job-card__description">Gestione ordini</p></article>')
    rows=listing_candidates(page,"Toscana")
    assert len(rows)==1 and rows[0]["company"]=="Azienda Test"
    assert rows[0]["url"]=="https://it.jobsora.com/offerta-123?source=1"
    assert listing_candidates(page.replace("Back Office Commerciale","Sviluppatore Java"),"Toscana")==[]
    print("Jobsora vacancy parser self-test: OK")

if __name__=="__main__":
    self_test()
