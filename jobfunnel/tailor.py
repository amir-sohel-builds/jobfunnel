"""On-demand tailoring for ONE job you chose. The only LLM call in the project. Cached per job."""
import json, os, time, urllib.request

MODEL = os.environ.get("JOBFUNNEL_MODEL", "claude-sonnet-5-5")
SYSTEM = """You tailor one candidate's application materials to one job posting.
Rules:
- Use ONLY facts that appear in PROFILE. Never invent employers, titles, dates, metrics, tools or outcomes.
- If the posting asks for something PROFILE does not show, list it under Gaps. Do not paper over it.
- Plain, direct, specific. No filler. Avoid: thrilled, passionate, leverage, dynamic, synergy, excited to.
Output markdown with exactly these sections:
## Match
3 bullets: where PROFILE lines up with the posting.
## Summary
3 sentences for the top of the resume.
## Lead with
5 bullets taken or adapted from PROFILE experience, most relevant first.
## Cover note
Under 150 words.
## Gaps
Bullets, or "None"."""

def build_user(profile, job):
    return (f"PROFILE:\n{profile}\n\nPOSTING: {job['company']} | {job['title']} | {job['location']}\n"
            f"{job['description'][:6000]}")

def call_model(system, user, key, model=MODEL):
    body = json.dumps({"model": model, "max_tokens": 1400, "system": system,
                       "messages": [{"role": "user", "content": user}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", body, {
        "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.load(r)
    return "".join(b.get("text", "") for b in d["content"] if b.get("type") == "text")

def tailor(con, job_id, profile_path="profile.md", force=False):
    row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise ValueError("job not found")
    if not force:
        c = con.execute("SELECT text FROM docs WHERE job_id=?", (job_id,)).fetchone()
        if c:
            return c["text"]
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("Set ANTHROPIC_API_KEY in your environment first.")
    if not os.path.exists(profile_path):
        raise ValueError("Create profile.md (copy profile.example.md) with your resume text first.")
    text = call_model(SYSTEM, build_user(open(profile_path).read(), dict(row)), key)
    con.execute("INSERT OR REPLACE INTO docs VALUES(?,?,?)", (job_id, text, time.time()))
    con.commit()
    return text
