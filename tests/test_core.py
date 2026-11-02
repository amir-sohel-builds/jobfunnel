import time, unittest, yaml
from jobfunnel import db, mailrules as mr, server
from jobfunnel.score import score_job

CFG = yaml.safe_load(open("config.yaml"))

def job(i, company, title, status="new"):
    return dict(id=i, company=company, title=title, status=status)

def add(con, i, company, title, status):
    con.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (i, "t", company, title, "Toronto", "u", "d", 80, "", status, time.time(), time.time()))

def M(i, sender, subject, snippet=""):
    return dict(id=i, ts=time.time(), sender=sender, subject=subject, snippet=snippet)

class Scoring(unittest.TestCase):
    def j(self, title, loc, desc=""):
        return dict(title=title, location=loc, description=desc)
    def test_good_match(self):
        s, _ = score_job(self.j("Staff Technical Program Manager", "Toronto, Canada (Remote)", "cloud platform aws"), CFG)
        self.assertGreaterEqual(s, 70)
    def test_excluded(self):
        self.assertEqual(score_job(self.j("TPM Intern", "Remote"), CFG)[0], 0)
        self.assertEqual(score_job(self.j("Senior TPM", "Berlin, Germany"), CFG)[0], 0)
        self.assertEqual(score_job(self.j("Software Engineer", "Toronto"), CFG)[0], 0)

class Mail(unittest.TestCase):
    def test_classify_order(self):
        self.assertEqual(mr.classify("we are unable to extend an offer"), "rejected")
        self.assertEqual(mr.classify("pleased to offer you the role"), "offer")
        self.assertEqual(mr.classify("we enjoyed the interview with the team. unfortunately"), "rejected")
    def test_process_and_idempotent(self):
        con = db.connect(":memory:")
        add(con, "a:1", "stripe", "Staff TPM", "applied")
        add(con, "a:2", "ramp", "TPM, Core", "new")
        add(con, "a:3", "ramp", "TPM, Data Platform", "new")
        msgs = [M("1", "Stripe", "Interview invitation", "schedule an interview with you"),
                M("2", "Ramp", "Thank you for applying", "received your application for TPM, Data Platform"),
                M("3", "Ramp", "Thank you for applying", "application received"),
                M("4", "Nobody", "Weekly digest", "hello")]
        r = mr.process(con, msgs)
        st = {x["id"]: x["status"] for x in con.execute("SELECT id,status FROM jobs")}
        self.assertEqual(st, {"a:1": "interview", "a:2": "new", "a:3": "applied"})
        self.assertEqual((r["updated"], r["review"]), (2, 1))
        self.assertEqual(mr.process(con, msgs), {"updated": 0, "review": 0, "ignored": 0})
    def test_no_regress(self):
        self.assertFalse(mr.advance_ok("interview", "screen"))
        self.assertTrue(mr.advance_ok("interview", "rejected"))
        self.assertFalse(mr.advance_ok("rejected", "rejected"))

class Funnel(unittest.TestCase):
    def test_counts_add_up(self):
        con = db.connect(":memory:"); server.seed_demo(con)
        f = server.state(con)["funnel"]
        r, w, c = f["reached"], f["waiting"], f["closed"]
        for i in range(3):
            self.assertEqual(r[i], r[i + 1] + w[i] + c[i])
        self.assertEqual(r[3], w[3] + c[3])
    def test_range_is_subset(self):
        con = db.connect(":memory:"); server.seed_demo(con)
        self.assertLessEqual(server.state(con, 30)["funnel"]["reached"][0], server.state(con)["funnel"]["reached"][0])
    def test_status_changes_logged(self):
        con = db.connect(":memory:"); add(con, "x:1", "acme", "TPM", "new")
        db.set_status(con, "x:1", "applied")
        self.assertEqual(server.state(con)["funnel"]["reached"][0], 1)

if __name__ == "__main__":
    unittest.main()
