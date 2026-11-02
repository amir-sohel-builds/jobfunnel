"""Read-only Gmail access. Fetches only headers and the snippet, never full message bodies."""
import os

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
QUERY = 'newer_than:{d}d (application OR applying OR interview OR candidacy OR recruiter) -category:promotions -category:social'

def _service(creds_path="credentials.json", token_path="token.json"):
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise SystemExit("Install Gmail deps first: pip install -r requirements-gmail.txt")
    creds = Credentials.from_authorized_user_file(token_path, SCOPES) if os.path.exists(token_path) else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                raise SystemExit("credentials.json not found. See the Gmail setup steps in README.md")
            creds = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES).run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

def fetch(days=30, max_n=150):
    svc = _service()
    ids, token = [], None
    while len(ids) < max_n:
        r = svc.users().messages().list(userId="me", q=QUERY.format(d=days), maxResults=100, pageToken=token).execute()
        ids += [m["id"] for m in r.get("messages", [])]
        token = r.get("nextPageToken")
        if not token:
            break
    for i in ids[:max_n]:
        m = svc.users().messages().get(userId="me", id=i, format="metadata",
                                       metadataHeaders=["From", "Subject"]).execute()
        h = {x["name"]: x["value"] for x in m["payload"]["headers"]}
        yield dict(id=i, ts=int(m["internalDate"]) / 1000, sender=h.get("From", ""),
                   subject=h.get("Subject", ""), snippet=m.get("snippet", ""))
