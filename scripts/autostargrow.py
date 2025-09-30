#!/usr/bin/env python3
# scripts/autostargrow.py

import os
import sys
import json
import random
from pathlib import Path
from datetime import datetime, timezone

from github import Github, Auth, GithubException

# --- Config ---
GROWTH_SAMPLE = 10  # how many new users to process per run

# Resolve repo root regardless of where the script is invoked from
REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = REPO_ROOT / ".github" / "state" / "stargazer_state.json"
USERNAMES_PATH = REPO_ROOT / "config" / "usernames.txt"


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def load_or_init_state(path: Path) -> dict:
    """Load JSON state; if missing, initialize it to an empty dict."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        print(f"[INIT] {path} not found. Creating empty state {{}}")
        path.write_text("{}\n", encoding="utf-8")
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"[WARN] {path} is corrupt JSON. Re-initializing to {{}}")
        path.write_text("{}\n", encoding="utf-8")
        return {}


def pick_public_nonfork_repos(user, max_repos: int = 3):
    """Return up to max_repos public, non-fork, non-private repos for a user."""
    repos = []
    try:
        for repo in user.get_repos():
            if repo.private or repo.fork:
                continue
            repos.append(repo)
            if len(repos) >= max_repos:
                break
    except GithubException as e:
        print(f"    [WARN] Unable to list repos for {user.login}: {e}")
    return repos


def main():
    print("=== GitGrowBot autostargrow.py started ===")

    # --- Env & Auth ---
    bot_user = os.getenv("BOT_USER")
    raw_token = os.getenv("PAT_TOKEN")

    if not bot_user or not raw_token:
        die("PAT_TOKEN and BOT_USER required")

    token = raw_token.strip()
    if not token:
        die("PAT_TOKEN is empty after stripping")

    print("PAT_TOKEN and BOT_USER env vars present.")
    print(f"BOT_USER: {bot_user}")

    if not USERNAMES_PATH.exists():
        die(f"{USERNAMES_PATH} not found; cannot perform growth starring.")

    print("Authenticating with GitHub...")
    try:
        gh = Github(auth=Auth.Token(token))  # modern (no deprecation warning)
        me = gh.get_user()
        print(f"Authenticated as: {me.login}")
    except Exception as e:
        die(f"Could not authenticate with GitHub: {e}")

    # --- State ---
    print(f"Loading state from {STATE_PATH} ...")
    state = load_or_init_state(STATE_PATH)
    growth_starred = state.get("growth_starred", {})

    # Upgrade legacy entries (string -> dict form)
    changed = False
    for user, entries in list(growth_starred.items()):
        upgraded = []
        for e in entries:
            if isinstance(e, dict) and "repo" in e and "starred_at" in e:
                upgraded.append(e)
            elif isinstance(e, str):
                upgraded.append({"repo": e, "starred_at": None})
                changed = True
            # else: skip corrupt entries silently
        if upgraded != entries:
            growth_starred[user] = upgraded
            changed = True

    # --- Load candidate usernames ---
    with USERNAMES_PATH.open("r", encoding="utf-8") as f:
        all_usernames = [line.strip() for line in f if line.strip()]
    print(f"  Loaded {len(all_usernames)} usernames from {USERNAMES_PATH}")

    # Exclude already processed users
    available = list(set(all_usernames) - set(growth_starred))
    print(f"  {len(available)} candidates for growth starring.")
    if not available:
        print("  No new candidates; nothing to do.")
    sample = random.sample(available, min(GROWTH_SAMPLE, len(available))) if available else []

    now_iso = datetime.now(timezone.utc).isoformat()

    # --- Star a repo for each sampled user ---
    for i, login in enumerate(sample, start=1):
        print(f"  [{i}/{len(sample)}] Growth star for user: {login}")
        try:
            u = gh.get_user(login)
        except GithubException as e:
            print(f"    [SKIP] Cannot fetch user {login}: {e}")
            continue

        repos = pick_public_nonfork_repos(u, max_repos=3)
        if not repos:
            print(f"    No public repos to star for {login}, skipping.")
            continue

        repo = random.choice(repos)
        try:
            print(f"    Starring repo: {repo.full_name}")
            me.add_to_starred(repo)
            growth_starred.setdefault(login, [])
            growth_starred[login].append({"repo": repo.full_name, "starred_at": now_iso})
            changed = True
            print(f"    Growth: Starred {repo.full_name} for {login} at {now_iso}")
        except GithubException as e:
            # 304 (not modified) may mean already starred; 403 may be perms
            print(f"    Failed to star {repo.full_name} for {login}: {e}")

    # --- Persist state if changed (or always write to keep deterministic) ---
    print(f"Saving updated growth_starred to {STATE_PATH} ...")
    state["growth_starred"] = growth_starred
    with STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    print(f"Updated growth_starred written to {STATE_PATH}")

    print("=== GitGrowBot autostargrow.py finished ===")


if __name__ == "__main__":
    main()
