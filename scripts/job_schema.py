"""Normalize legacy and imported job metadata without changing vacancy identity or audit."""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path


def normalized_score(value):
    if isinstance(value, bool):
        return 0.0
    try:
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0


def normalized_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1")
    return isinstance(value, (int, float)) and value == 1


def normalized_checks(value):
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def normalize_catalog(data):
    """Repair optional metadata only; never fabricate IDs, links or audit evidence."""
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise ValueError("Invalid catalogue: jobs must be a list")
    jobs = data["jobs"]
    ids = set()
    for job in jobs:
        if not isinstance(job, dict):
            raise ValueError("Invalid catalogue: non-object job")
        ident = str(job.get("id") or "").strip()
        if not ident or ident in ids:
            raise ValueError("Invalid catalogue: empty or duplicate job ID")
        ids.add(ident)

    counts = Counter()
    for job in jobs:
        old = job.get("score")
        # Preserve existing finite numeric scores, including their original type.
        try:
            valid = type(old) in (int, float) and math.isfinite(old)
        except OverflowError:
            valid = False
        if not valid:
            job["score"] = normalized_score(old)
            counts["score"] += 1
        old = job.get("checks")
        if not isinstance(old, list) or not all(isinstance(x, str) for x in old):
            job["checks"] = normalized_checks(old)
            counts["checks"] += 1
        for key in ("active", "remote"):
            old = job.get(key)
            if not isinstance(old, bool):
                # Missing/unknown eligibility must not become a positive claim.
                job[key] = normalized_bool(old)
                counts[key] += 1
    if counts:
        print("Job metadata normalized:", dict(counts))
    return counts


def write_catalog(path, data):
    normalize_catalog(data)
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def self_test():
    cases = [None, "", "7.25", "NaN", float("inf"), {}, [], True, 10**400, "bad", 8]
    jobs = [{"id": str(i), "score": x, "checks": ["verified", None, 12],
             "active": "false", "remote": "true", "url": "https://example.org/" + str(i),
             "candidate": True} for i, x in enumerate(cases)]
    jobs.append({"id": "missing"})
    data = {"jobs": jobs, "audit": {"runs": {"15:30": {"status": "partial"}}}}
    counts = normalize_catalog(data)
    assert counts["score"] == 11
    assert jobs[2]["score"] == 7.25 and jobs[10]["score"] == 8
    assert all(type(j["score"]) in (int, float) and math.isfinite(j["score"]) for j in jobs)
    assert all(type(j["active"]) is bool and type(j["remote"]) is bool for j in jobs)
    assert jobs[0]["active"] is False and jobs[0]["remote"] is True
    assert jobs[0]["checks"] == ["verified"] and jobs[0]["candidate"] is True
    assert jobs[-1]["remote"] is False and jobs[-1]["active"] is False
    assert jobs[0]["url"] == "https://example.org/0"
    assert data["audit"]["runs"]["15:30"]["status"] == "partial"
    assert not normalize_catalog(data)
    for bad in ({"jobs": None}, {"jobs": [{"id": "x"}, {"id": "x"}]}, {"jobs": [{}]}):
        try:
            normalize_catalog(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid catalogue accepted")
    print("Job schema normalization regression tests: OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/jobs.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        if normalize_catalog(data):
            write_catalog(path, data)
