import sqlite3, time

STAGES = ["applied", "screen", "interview", "offer"]  # funnel order
STATUSES = ["new", "shortlisted", "skipped"] + STAGES + ["rejected", "withdrawn"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
  id TEXT PRIMARY KEY, source TEXT, company TEXT, title TEXT, location TEXT,
  url TEXT, description TEXT, score INTEGER, reasons TEXT,
  status TEXT DEFAULT 'new', first_seen REAL, updated REAL);
CREATE TABLE IF NOT EXISTS events(
  job_id TEXT, status TEXT, ts REAL, note TEXT);
CREATE TABLE IF NOT EXISTS mail(
  msg_id TEXT PRIMARY KEY, ts REAL, sender TEXT, subject TEXT, job_id TEXT, kind TEXT, outcome TEXT);
CREATE TABLE IF NOT EXISTS docs(job_id TEXT PRIMARY KEY, text TEXT, ts REAL);
"""

def connect(path="jobfunnel.db"):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con

def upsert(con, job, score, reasons, min_score):
    """Insert new jobs; never overwrite status of an existing job."""
    if con.execute("SELECT 1 FROM jobs WHERE id=?", (job["id"],)).fetchone():
        return False
    now = time.time()
    status = "new" if score >= min_score else "skipped"
    con.execute(
        "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (job["id"], job["source"], job["company"], job["title"], job["location"],
         job["url"], job["description"], score, "; ".join(reasons), status, now, now))
    return True

def set_status(con, job_id, status, note=""):
    if status not in STATUSES:
        raise SystemExit(f"status must be one of {STATUSES}")
    row = con.execute("SELECT id FROM jobs WHERE id LIKE ?", ("%" + job_id,)).fetchall()
    if len(row) != 1:
        raise SystemExit(f"{len(row)} jobs match '{job_id}'; use more of the id")
    jid = row[0]["id"]
    now = time.time()
    con.execute("UPDATE jobs SET status=?, updated=? WHERE id=?", (status, now, jid))
    con.execute("INSERT INTO events VALUES(?,?,?,?)", (jid, status, now, note))
    con.commit()
    return jid
