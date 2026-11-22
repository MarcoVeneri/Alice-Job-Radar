"""Stable vacancy key, retaining identifiers carried in the query string."""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def job_url(value):
    if not value:
        return ""
    url = urlsplit(str(value))
    args = [(k, v) for k, v in parse_qsl(url.query)
            if not k.lower().startswith("utm_") and k.lower() not in
            {"source", "from", "trackingid", "refid", "trk"}]
    if (url.hostname or "").endswith(".indeed.com") or url.hostname == "indeed.com":
        jk = dict(args).get("jk") or dict(args).get("vjk")
        if jk:
            return "https://indeed.com/viewjob?" + urlencode({"jk": jk})
    return urlunsplit((url.scheme.lower(), url.netloc.lower(), url.path.rstrip("/"),
                       urlencode(sorted(args)), ""))
