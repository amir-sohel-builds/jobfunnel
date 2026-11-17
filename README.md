# jobfunnel

Deterministic job-search pipeline for TPM roles. Pulls from public Greenhouse/Lever/Ashby
board APIs, scores with transparent rules, tracks your application funnel in SQLite.
No LinkedIn scraping, no LLM calls in the core loop.

    pip install -r requirements.txt
    python -m jobfunnel.cli fetch
    python -m jobfunnel.cli list
    python -m jobfunnel.cli mark <id-suffix> applied --note "referral"
    python -m jobfunnel.cli report

Tune `config.yaml` (regexes, weights, companies). Statuses: new, shortlisted, skipped,
applied, screen, interview, offer, rejected, withdrawn.

## Web app

    python -m jobfunnel.cli serve --demo     # sample data
    python -m jobfunnel.cli serve            # your data, http://localhost:8765

Overview (funnel, 30/90 days/all time), Matches, Board (drag cards), Inbox.

## Gmail status sync (no LLM)

Read-only; only headers and the message snippet are fetched. Rules in `mailrules.py` map emails
to statuses (received, screen, interview, offer, rejected). Statuses only move forward, except rejections.
Ambiguous emails go to the Inbox as "Needs a look" instead of guessing.

1. console.cloud.google.com: create a project, enable the Gmail API.
2. OAuth consent screen: External, add your own email as a test user.
3. Credentials: create an OAuth client ID of type Desktop app, download it as `credentials.json` into this folder.
4. `pip install -r requirements-gmail.txt`
5. `python -m jobfunnel.cli sync-gmail --days 30` (a browser window asks you to approve once)

`credentials.json` and `token.json` are gitignored. Never commit them.

## Tailoring (the only LLM call)

Copy `profile.example.md` to `profile.md` and fill in your real resume text. Then:

    export ANTHROPIC_API_KEY=...        # optional: JOBFUNNEL_MODEL to pick a model
    python -m jobfunnel.cli tailor <id>

or press Tailor on a job in the web app. One call per job you choose, cached, uses only facts from your profile and lists gaps instead of inventing experience.

## License

MIT. See LICENSE.
