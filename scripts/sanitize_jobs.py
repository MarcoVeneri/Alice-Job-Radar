from __future__ import annotations

import json
import math
from pathlib import Path

PATH = Path("data/jobs.json")


def s(value, default=""):
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def score(value):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return 0.0
    return n if math.isfinite(n) else 0.0


def checks(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [s(x) for x in value if s(x)]
    if isinstance(value, str):
        return [value] if value else []
    return [s(value)]


def main():
    data = json.loads(PATH.read_text(encoding="utf-8"))
    raw_jobs = data.get("jobs") if isinstance(data, dict) else []
    if not isinstance(raw_jobs, list):
        raw_jobs = []

    out = []
    seen = set()
    for i, raw in enumerate(raw_jobs):
        if not isinstance(raw, dict):
            continue
        job = dict(raw)
        job_id = s(job.get("id")) or f"sanitized-{i}"
        if job_id in seen:
            continue
        seen.add(job_id)

        job["id"] = job_id
        job["company"] = s(job.get("company"), "Azienda") or "Azienda"
        job["title"] = s(job.get("title"), "Offerta") or "Offerta"
        job["location"] = s(job.get("location"))
        job["workMode"] = s(job.get("workMode"))
        job["contract"] = s(job.get("contract"))
        job["salary"] = s(job.get("salary"))
        job["category"] = s(job.get("category"), "Operations") or "Operations"
        job["summary"] = s(job.get("summary"))
        job["url"] = s(job.get("url"), "#") or "#"
        job["date"] = s(job.get("date"))
        job["firstSeenAt"] = s(job.get("firstSeenAt"))
        job["firstSeenRun"] = s(job.get("firstSeenRun"))
        job["score"] = score(job.get("score"))
        job["checks"] = checks(job.get("checks"))
        job["remote"] = bool(job.get("remote", False))
        job["active"] = job.get("active", True) is not False
        out.append(job)

    data["jobs"] = out
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Sanitized {len(out)} jobs; removed {len(raw_jobs) - len(out)} invalid/duplicate records")


if __name__ == "__main__":
    main()
