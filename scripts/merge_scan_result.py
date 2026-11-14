#!/usr/bin/env python3
"""Safely merge a completed scan with a newer GitHub main after a rejected push."""
from __future__ import annotations
import json
import sys
from pathlib import Path

def strength(run):
    if not isinstance(run, dict):
        return (-1, -1, -1, -1)
    status = run.get("status", "")
    ok = {"complete": 3, "partial": 2, "running": 1, "failed": 0}.get(status, 0)
    def number(key):
        try: return int(run.get(key) or 0)
        except (ValueError, TypeError): return 0
    return (ok, number("requiredSourcesChecked"), number("newJobs"), number("queriesRun"))

def combine(latest, scanned):
    out = dict(latest)
    existing = list(out.get("jobs", []))
    ids = {str(j.get("id")) for j in existing}
    links = {str(j.get("url", "")).split("?")[0].lower() for j in existing}
    new_jobs = []
    for job in scanned.get("jobs", []):
        if not isinstance(job, dict):
            continue
        ident = str(job.get("id", ""))
        link = str(job.get("url", "")).split("?")[0].lower()
        if not ident or ident in ids or (link and link in links):
            continue
        ids.add(ident)
        if link: links.add(link)
        new_jobs.append(job)
    out["jobs"] = new_jobs + existing
    la = latest.get("audit")
    sa = scanned.get("audit")
    if isinstance(sa, dict) and sa.get("date"):
        if not isinstance(la, dict) or la.get("date") != sa.get("date"):
            history = list(out.get("auditHistory", []))
            if isinstance(la, dict) and la.get("date") and not any(
                x.get("date") == la["date"] for x in history if isinstance(x, dict)
            ):
                history.append(la)
            out["auditHistory"] = history
            out["audit"] = sa
        else:
            merged = dict(la)
            old_runs = dict(la.get("runs") or {})
            for slot, run in (sa.get("runs") or {}).items():
                old_run = old_runs.get(slot)
                if old_run is None or strength(run) > strength(old_run):
                    old_runs[slot] = run
                elif slot == "automated_fallback" and run != old_run:
                    old_runs.setdefault("automated_fallback_previous", run)
            merged["runs"] = old_runs
            out["audit"] = merged
    old_ts = str(out.get("generatedAt", ""))
    scan_ts = str(scanned.get("generatedAt", ""))
    if scan_ts > old_ts:
        out["generatedAt"] = scan_ts
    return out

def self_test():
    latest = {
      "generatedAt": "2026-11-14T14:30:00Z",
      "jobs": [{"id": "a", "url": "https://example.org/a"}, {"id": "b", "url": "https://example.org/b"}],
      "audit": {"date": "2026-11-14", "runs": {
          "15:30": {"status": "complete", "requiredSourcesChecked": 100, "newJobs": 1}}}}
    scan = {
      "generatedAt": "2026-11-14T14:29:00Z",
      "jobs": [{"id": "a", "url": "https://example.org/a"}, {"id": "c", "url": "https://example.org/c"}],
      "audit": {"date": "2026-11-14", "runs": {
          "15:30": {"status": "partial", "requiredSourcesChecked": 4, "newJobs": 1},
          "automated_fallback": {"status": "partial", "requiredSourcesChecked": 4, "newJobs": 1}}}}
    merged = combine(latest, scan)
    assert len(merged["jobs"]) == 3
    assert merged["jobs"][0]["id"] == "c"
    assert merged["audit"]["runs"]["15:30"]["status"] == "complete"
    assert merged["audit"]["runs"]["automated_fallback"]["status"] == "partial"
    assert merged["generatedAt"] == latest["generatedAt"]
    print("Concurrent update merge self-test: OK")

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        self_test()
    elif len(sys.argv) == 3:
        scan_file, latest_file = map(Path, sys.argv[1:])
        merged = combine(json.loads(latest_file.read_text(encoding="utf-8")),
                         json.loads(scan_file.read_text(encoding="utf-8")))
        latest_file.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        print(f"Merged concurrent scan: {len(merged['jobs'])} jobs")
    else:
        raise SystemExit("Usage: merge_scan_result.py --self-test | SCAN_JSON LATEST_JSON")
