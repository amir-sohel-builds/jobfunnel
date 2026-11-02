import json, os, random, time, datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from . import db, sources, tailor as tailor_mod
from urllib.parse import urlparse, parse_qs
from .score import score_job

STATIC = os.path.join(os.path.dirname(__file__), "static", "index.html")
DAY = 86400

def state(con, days=None):
    jobs = [dict(r) for r in con.execute(
        "SELECT id,company,title,location,url,score,reasons,status,updated,"
        "substr(description,1,420) AS snippet FROM jobs WHERE status!='skipped' "
        "ORDER BY score DESC LIMIT 500")]
    reached = [set() for _ in db.STAGES]
    applied_ts = []
    inw = None
    if days:
        cut = time.time() - days * DAY
        inw = {r["job_id"] for r in con.execute("SELECT job_id FROM events WHERE status='applied' AND ts>=?", (cut,))}
    for e in con.execute("SELECT job_id,status,ts FROM events"):
        if inw is not None and e["job_id"] not in inw:
            continue
        if e["status"] in db.STAGES:
            for j in range(db.STAGES.index(e["status"]) + 1):
                reached[j].add(e["job_id"])
        if e["status"] == "applied":
            applied_ts.append(e["ts"])
    cur = {}
    for j in jobs:
        if inw is None or j["id"] in inw:
            cur[j["status"]] = cur.get(j["status"], 0) + 1
    r = [len(s) for s in reached]
    waiting = [cur.get(s, 0) for s in db.STAGES]
    closed = [max(0, r[i] - (r[i + 1] if i < 3 else 0) - waiting[i]) for i in range(4)]
    mon = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())
    weeks = []
    for k in range(7, -1, -1):
        a = mon - datetime.timedelta(weeks=k)
        lo = time.mktime(a.timetuple())
        n = sum(1 for t in applied_ts if lo <= t < lo + 7 * DAY)
        weeks.append({"label": a.strftime("%b %d").replace(" 0", " "), "n": n})
    mail = [dict(r) for r in con.execute(
        "SELECT m.ts,m.sender,m.subject,m.kind,m.outcome,j.company,j.title FROM mail m "
        "LEFT JOIN jobs j ON j.id=m.job_id WHERE m.outcome IN ('updated','review') ORDER BY m.ts DESC LIMIT 30")]
    return {"mail": mail, "jobs": jobs, "funnel": {"reached": r, "waiting": waiting, "closed": closed}, "weeks": weeks}

def do_fetch(cfg, con):
    new = kept = 0
    for job in sources.fetch_all(cfg["companies"]):
        sc, why = score_job(job, cfg)
        if db.upsert(con, job, sc, why, cfg["score"]["min_score"]):
            new += 1; kept += sc >= cfg["score"]["min_score"]
    con.commit()
    return {"new": new, "kept": kept}

def seed_demo(con):
    if con.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"]:
        return
    rnd = random.Random(7)
    cos = ["Stripe", "Datadog", "Cloudflare", "Ramp", "Notion", "Airbnb", "Shopify", "Figma", "Twilio", "GitLab",
           "Vimeo", "Okta", "Canva", "Wealthsimple", "Hootsuite", "Asana", "Elastic", "Confluent", "Samsara", "Brex"]
    roles = ["Staff TPM, Platform", "Senior TPM, Infrastructure", "Technical Program Manager", "Principal TPM, Data",
             "Staff TPM, Core Systems", "Senior TPM, AI Platform", "TPM, Developer Experience", "Staff TPM, Streaming"]
    locs = ["Toronto, Canada", "Remote, Canada", "Remote, United States", "Vancouver, Canada", "New York, United States"]
    paths = [["applied"], ["applied"], ["applied", "screen"], ["applied", "screen"], ["applied", "screen", "interview"],
             ["applied", "screen", "interview"], ["applied", "screen", "interview", "offer"], ["applied", "rejected"],
             ["applied", "rejected"], ["applied", "screen", "rejected"], ["applied", "screen", "interview", "rejected"],
             ["applied", "screen", "interview", "rejected"], ["applied"], ["applied", "screen"], ["shortlisted"], ["shortlisted"]]
    now = time.time()
    for i, c in enumerate(cos * 2):
        title, loc = rnd.choice(roles), rnd.choice(locs)
        sc = rnd.randint(52, 96)
        jid = f"demo:{c.lower()}:{1000 + i}"
        path = paths[i] if i < len(paths) else ["new"]
        t = now - rnd.randint(20, 52) * DAY
        con.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (jid, "demo", c, title, loc, "https://example.com/jobs/" + str(1000 + i),
                     "Lead cross-functional programs across platform and cloud infrastructure teams.", sc,
                     "staff +25; remote +10; kw(6) +30", path[-1], t, t))
        if path[0] != "new":
            for st in path:
                t += rnd.randint(1, 8) * DAY * (0.6 if st == "applied" else 1)
                t = min(t, now - DAY)
                con.execute("INSERT INTO events VALUES(?,?,?,?)", (jid, st, t, ""))
    for k, (c, sub, kind) in enumerate([("Stripe", "Interview invitation: Staff TPM", "interview"),
                                        ("Airbnb", "Update on your application", "rejected"),
                                        ("Datadog", "Quick intro call?", "screen"),
                                        ("Figma", "Thank you for applying to Figma", "received")]):
        r = con.execute("SELECT id FROM jobs WHERE company=? LIMIT 1", (c,)).fetchone()
        con.execute("INSERT INTO mail VALUES(?,?,?,?,?,?,?)", (f"demo-mail-{k}", now - (k + 1) * DAY, c + " Recruiting", sub,
                    r["id"] if r else None, kind, "updated"))
    con.commit()

class H(BaseHTTPRequestHandler):
    cfg = None; dbpath = None
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/state":
            d = int(parse_qs(u.query).get("days", ["0"])[0] or 0)
            return self._send(200, state(db.connect(self.dbpath), d or None))
        with open(STATIC, "rb") as f:
            self._send(200, f.read(), "text/html; charset=utf-8")
    def do_POST(self):
        con = db.connect(self.dbpath)
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            if self.path == "/api/mark":
                return self._send(200, {"id": db.set_status(con, data["id"], data["status"], data.get("note", ""))})
            if self.path == "/api/tailor":
                try:
                    return self._send(200, {"text": tailor_mod.tailor(con, data["id"], force=bool(data.get("force")))})
                except Exception as e:
                    return self._send(400, {"error": str(e)})
            if self.path == "/api/fetch":
                return self._send(200, do_fetch(self.cfg, con))
        except SystemExit as e:
            return self._send(400, {"error": str(e)})
        self._send(404, {"error": "not found"})

def run(cfg, dbpath, port=8765, demo=False):
    H.cfg, H.dbpath = cfg, dbpath
    if demo:
        seed_demo(db.connect(dbpath))
    print(f"jobfunnel running at http://localhost:{port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
