import re

def score_job(job, cfg):
    """Pure function. Returns (score, reasons). No network, no LLM."""
    s = cfg["score"]
    title, loc = job["title"].lower(), job["location"].lower()
    desc = job["description"].lower()
    if not re.search(cfg["title_include"], title):
        return 0, ["title no match"]
    if re.search(cfg["title_exclude"], title):
        return 0, ["title excluded"]
    if loc and not re.search(cfg["location_include"], loc):
        return 0, ["location no match"]
    if loc and re.search(cfg["location_exclude"], loc) and not re.search(r"canada|united states|usa", loc):
        return 0, ["location excluded"]

    pts, why = s["base"], []
    for word, p in s["seniority"].items():
        if re.search(rf"\b{word}\b", title):
            pts += p; why.append(f"{word} +{p}"); break
    if "remote" in loc or "remote" in title:
        pts += s["remote_bonus"]; why.append(f"remote +{s['remote_bonus']}")
    if re.search(r"canada|toronto|ontario|vancouver|montreal", loc):
        pts += s["canada_bonus"]; why.append(f"canada +{s['canada_bonus']}")
    hits = [k for k in s["keywords"] if re.search(rf"\b{re.escape(k)}\b", desc)]
    kw = min(len(hits) * 5, s["keyword_cap"])
    if kw:
        pts += kw; why.append(f"kw({len(hits)}) +{kw}")
    return min(pts, 100), why
