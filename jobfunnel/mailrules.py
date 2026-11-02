"""Deterministic email -> status rules. No LLM. Order matters: rejections are checked
first because they often contain words like 'offer' or 'interview'."""
import re
from . import db

RULES = [
    ("rejected", r"unfortunately|not (be )?moving forward|will not be moving|decided to (move forward|proceed) with (other|another)|regret to inform|not (been )?selected|position has been filled|unable to (offer|extend)"),
    ("offer", r"pleased to (offer|extend)|extend (you )?an offer|offer letter|excited to offer"),
    ("interview", r"schedule (an|your|a) .{0,20}interview|interview (with|invitation|availability)|invite you to (an )?interview|(technical|onsite|panel|final) (round|interview)|calendly\.com"),
    ("screen", r"(recruiter|phone|initial|intro\w*) (screen|call|chat)|quick (call|chat)|\b(15|20|30)[- ]minute (call|chat|conversation)|learn more about your background"),
    ("received", r"thank you for (applying|your application|your interest)|application (has been )?received|received your application|we(\u2019|')ve received"),
]
RANK = {"new": 0, "shortlisted": 0, "applied": 1, "screen": 2, "interview": 3, "offer": 4}

def classify(text):
    t = text.lower()
    for kind, rx in RULES:
        if re.search(rx, t):
            return kind
    return None

def _words(s):
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 3}

def match_job(text, jobs):
    """Returns (job, ambiguous). Company name must appear as a whole word; ties broken by title overlap."""
    t = text.lower()
    cands = []
    for j in jobs:
        rx = r"\b" + re.escape(j["company"].lower()).replace(r"\-", r"[\s-]?") + r"\b"
        if re.search(rx, t):
            cands.append(j)
    if not cands:
        return None, False
    if len({j["company"] for j in cands}) > 1:
        return None, True
    if len(cands) == 1:
        return cands[0], False
    tw = _words(t)
    scored = sorted(((len(_words(j["title"]) & tw), j) for j in cands), key=lambda x: -x[0])
    if scored[0][0] > scored[1][0]:
        return scored[0][1], False
    return None, True

def advance_ok(cur, new):
    if new == "rejected":
        return cur not in ("rejected", "withdrawn")
    return RANK[new] > RANK.get(cur, 0)

def process(con, msgs):
    """msgs: dicts with id, ts, sender, subject, snippet. Safe to re-run (dedupes by message id)."""
    out = {"updated": 0, "review": 0, "ignored": 0}
    for m in msgs:
        if con.execute("SELECT 1 FROM mail WHERE msg_id=?", (m["id"],)).fetchone():
            continue
        kind = classify(m["subject"] + " " + m["snippet"])
        job_id, outcome = None, "ignored"
        if kind:
            pool = ("new", "shortlisted") if kind == "received" else ("applied", "screen", "interview", "offer")
            jobs = [dict(r) for r in con.execute(
                "SELECT id,company,title,status FROM jobs WHERE status IN (%s)" % ",".join("?" * len(pool)), pool)]
            job, amb = match_job(f'{m["sender"]} {m["subject"]} {m["snippet"]}', jobs)
            if kind == "received" and job:
                n = con.execute("SELECT COUNT(*) c FROM jobs WHERE company=? AND status!='skipped'", (job["company"],)).fetchone()["c"]
                if n > 1 and not (_words(job["title"]) & _words(f'{m["subject"]} {m["snippet"]}')):
                    job, amb = None, True
            new = "applied" if kind == "received" else kind
            if job and advance_ok(job["status"], new):
                db.set_status(con, job["id"], new, "email: " + m["subject"][:80])
                job_id, outcome = job["id"], "updated"
            elif amb or (job is None and kind != "received"):
                outcome = "review"
        con.execute("INSERT INTO mail VALUES(?,?,?,?,?,?,?)",
                    (m["id"], m["ts"], m["sender"], m["subject"], job_id, kind or "", outcome))
        out[outcome] += 1
    con.commit()
    return out
