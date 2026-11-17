import argparse, sys, yaml
from . import db, sources
from .score import score_job

def load_cfg(path):
    with open(path) as f:
        return yaml.safe_load(f)

def cmd_fetch(a, cfg, con):
    new = kept = 0
    for job in sources.fetch_all(cfg["companies"]):
        sc, why = score_job(job, cfg)
        if db.upsert(con, job, sc, why, cfg["score"]["min_score"]):
            new += 1; kept += sc >= cfg["score"]["min_score"]
    con.commit()
    print(f"{new} new jobs, {kept} above threshold")

def cmd_list(a, cfg, con):
    rows = con.execute(
        "SELECT id,score,company,title,location,url FROM jobs WHERE status=? "
        "ORDER BY score DESC LIMIT ?", (a.status, a.n)).fetchall()
    for r in rows:
        print(f"{r['score']:>3}  {r['id'][-12:]:<12} {r['company']:<12} {r['title'][:50]:<50} {r['location'][:25]}\n     {r['url']}")

def cmd_mark(a, cfg, con):
    print("ok:", db.set_status(con, a.id, a.status, a.note))

def cmd_report(a, cfg, con):
    total = con.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"]
    above = con.execute("SELECT COUNT(*) c FROM jobs WHERE status!='skipped'").fetchone()["c"]
    print(f"found {total} | shortlist-worthy {above}")
    prev = None
    for i, st in enumerate(db.STAGES):
        later = db.STAGES[i:]
        q = ",".join("?" * len(later))
        n = con.execute(f"SELECT COUNT(DISTINCT job_id) c FROM events WHERE status IN ({q})", later).fetchone()["c"]
        pct = f"  ({n/prev:.0%} of prev)" if prev else ""
        print(f"{st:<10}{n:>4}{pct}")
        prev = n or None
    rej = con.execute("SELECT COUNT(*) c FROM jobs WHERE status='rejected'").fetchone()["c"]
    print(f"rejected  {rej:>4}")
    print("\nby company (applied+):")
    for r in con.execute("SELECT company, COUNT(DISTINCT job_id) n FROM events e JOIN jobs j ON j.id=e.job_id "
                         "WHERE e.status='applied' GROUP BY company ORDER BY n DESC"):
        print(f"  {r['company']:<14}{r['n']}")

def cmd_gmail(a, cfg, con):
    from . import gmail, mailrules
    r = mailrules.process(con, gmail.fetch(a.days))
    print(f"{r['updated']} statuses updated, {r['review']} need review, {r['ignored']} ignored")

def cmd_tailor(a, cfg, con):
    from . import tailor
    rows = con.execute("SELECT id FROM jobs WHERE id LIKE ?", ("%" + a.id,)).fetchall()
    if len(rows) != 1:
        raise SystemExit(f"{len(rows)} jobs match '{a.id}'")
    print(tailor.tailor(con, rows[0]["id"], force=a.force))

def cmd_serve(a, cfg, con):
    from . import server
    server.run(cfg, a.db, a.port, a.demo)

def resolve_db(a):
    """Demo mode always uses a separate database file, so sample data
    can never mix with real applications."""
    if a.cmd == "serve" and getattr(a, "demo", False) and a.db == "jobfunnel.db":
        return "jobfunnel-demo.db"
    return a.db

def main(argv=None):
    p = argparse.ArgumentParser(prog="jobfunnel")
    p.add_argument("--config", default="config.yaml"); p.add_argument("--db", default="jobfunnel.db")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch").set_defaults(f=cmd_fetch)
    l = sub.add_parser("list"); l.add_argument("--status", default="new"); l.add_argument("-n", type=int, default=20); l.set_defaults(f=cmd_list)
    m = sub.add_parser("mark"); m.add_argument("id"); m.add_argument("status"); m.add_argument("--note", default=""); m.set_defaults(f=cmd_mark)
    sub.add_parser("report").set_defaults(f=cmd_report)
    g = sub.add_parser("sync-gmail"); g.add_argument("--days", type=int, default=30); g.set_defaults(f=cmd_gmail)
    t = sub.add_parser("tailor"); t.add_argument("id"); t.add_argument("--force", action="store_true"); t.set_defaults(f=cmd_tailor)
    v = sub.add_parser("serve"); v.add_argument("--port", type=int, default=8765); v.add_argument("--demo", action="store_true"); v.set_defaults(f=cmd_serve)
    a = p.parse_args(argv)
    a.db = resolve_db(a)
    a.f(a, load_cfg(a.config), db.connect(a.db))

if __name__ == "__main__":
    main()
