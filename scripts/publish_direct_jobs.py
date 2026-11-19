"""Include direct-board listings in the same catalogue consumed by every app version."""
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen


def merge(data, rows):
    jobs = data['jobs']
    by_id = {job['id']: job for job in jobs}
    urls = {job.get('url', '').split('?')[0].rstrip('/') for job in jobs}
    for row in rows:
        job = row['job']
        ident = job['id']
        url = job['url'].split('?')[0].rstrip('/')
        if ident in by_id:
            by_id[ident].update(job)
        elif url not in urls:
            jobs.append(dict(job))
            by_id[ident] = jobs[-1]
            urls.add(url)
    audit = data['audit']
    for slot, run in audit['runs'].items():
        if slot not in ('09:30', '15:30') or run.get('status') not in ('partial', 'complete'):
            continue
        count = sum(j['id'] in by_id and j.get('date') == audit['date'] and
                    j.get('firstSeenRun') == slot for j in (r['job'] for r in rows))
        run['newJobs'] = run.get('newJobs', 0) - run.get('directNewJobsIncluded', 0) + count
        run['directNewJobsIncluded'] = count


def main():
    cfg = Path('config.js').read_text()
    base = re.search(r'url:"([^"]+)"', cfg)[1]
    key = re.search(r'publishableKey:"([^"]+)"', cfg)[1]
    rows = []
    while True:
        url = f'{base}/rest/v1/alice_direct_jobs?select=job&order=job_id&limit=500&offset={len(rows)}'
        with urlopen(Request(url, headers={'apikey': key}), timeout=20) as response:
            page = json.load(response)
        rows.extend(page)
        if len(page) < 500:
            break
    path = Path('data/jobs.json')
    data = json.loads(path.read_text())
    merge(data, rows)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
