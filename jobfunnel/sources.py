import json, re, sys, urllib.request, html

UA = {"User-Agent": "jobfunnel/0.1 (personal job search)"}

def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

def _text(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()

def greenhouse(slug):
    d = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    for j in d.get("jobs", []):
        yield dict(id=f"gh:{slug}:{j['id']}", source="greenhouse", company=slug,
                   title=j["title"], location=(j.get("location") or {}).get("name", ""),
                   url=j["absolute_url"], description=_text(j.get("content")))

def lever(slug):
    for j in _get(f"https://api.lever.co/v0/postings/{slug}?mode=json"):
        cat = j.get("categories") or {}
        loc = " ".join(filter(None, [cat.get("location"), j.get("workplaceType")]))
        yield dict(id=f"lv:{slug}:{j['id']}", source="lever", company=slug,
                   title=j["text"], location=loc, url=j["hostedUrl"],
                   description=j.get("descriptionPlain", ""))

def ashby(slug):
    d = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    for j in d.get("jobs", []):
        loc = j.get("location", "") + (" Remote" if j.get("isRemote") else "")
        yield dict(id=f"ab:{slug}:{j['id']}", source="ashby", company=slug,
                   title=j["title"], location=loc, url=j["jobUrl"],
                   description=j.get("descriptionPlain", ""))

FETCHERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}

def fetch_all(companies):
    for src, slugs in companies.items():
        for slug in slugs or []:
            try:
                yield from FETCHERS[src](slug)
            except Exception as e:
                print(f"warn: {src}/{slug}: {e}", file=sys.stderr)
