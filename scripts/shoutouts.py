#!/usr/bin/env python3
import os, json
from pathlib import Path
import requests
from github import Github

# ─── Config ───────────────────────────────────────────────────────────────────
DISCUSSION_ID = os.environ["WELCOME_DISCUSSION_ID"]
TOKEN         = os.environ["PAT_TOKEN"]
REPO          = os.environ["GITHUB_REPOSITORY"]
STATE_FILE    = Path(".github/state/stars.json")

# ─── GitHub setup & REST endpoint ─────────────────────────────────────────────
gh   = Github(TOKEN)
repo = gh.get_repo(REPO)
COMMENTS_URL = (
    f"https://api.github.com/repos/{REPO}"
    f"/discussions/{DISCUSSION_ID}/comments"
)

# ─── 1. Load previous state ────────────────────────────────────────────────────
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
if STATE_FILE.exists():
    seen = set(json.loads(STATE_FILE.read_text())["stars"])
else:
    seen = set()

# ─── 2. Get current stargazers & diff ─────────────────────────────────────────
current   = {u.login.lower() for u in repo.get_stargazers()}
new_stars = current - seen
un_stars  = seen    - current

# ─── 3. Post messages via REST ────────────────────────────────────────────────
def post(body: str):
    resp = requests.post(
        COMMENTS_URL,
        headers={
            "Authorization": f"token {TOKEN}",
            "Accept":        "application/vnd.github.v3+json"
        },
        json={"body": body},
    )
    resp.raise_for_status()

# Welcome new stargazers
if new_stars:
    msg = (
        "🎉 **A sky full of new stars!** 🌟 Welcome aboard: "
        + ", ".join(f"@{u}" for u in sorted(new_stars))
        + "\n\n"
        "> _'Cause you're a sky, you're a sky full of stars_\n"
        "> _I'm gonna give you my heart..._\n\n"
        "You've been added to `usernames.txt`. Glad to have you here!"
    )
    post(msg)

# Farewell unstargazers
if un_stars:
    msg = (
        "👋 **Oh no, stars fading away...** We'll miss you: "
        + ", ".join(f"@{u}" for u in sorted(un_stars))
        + "\n\n"
        "> _I don't care, go on and tear me apart_\n"
        "> _I don't care if you do_\n"
        "> _'Cause in a sky, 'cause in a sky full of stars_\n"
        "> _I think I saw you..._\n\n"
        "We've removed you from the list, but you're always welcome back!"
    )
    post(msg)

# ─── 4. Save updated state ────────────────────────────────────────────────────
STATE_FILE.write_text(json.dumps({"stars": sorted(current)}))
print("Shout-out run complete.")
