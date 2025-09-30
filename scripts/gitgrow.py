#!/usr/bin/env python3
import os
import sys
import random
from pathlib import Path
from github import Github, GithubException, Auth
from datetime import datetime, timedelta, timezone

def die(msg: str):
    print(msg, file=sys.stderr)
    sys.exit(1)

def main():
    # — Auth & client setup —
    raw = os.getenv("PAT_TOKEN")
    if not raw:
        die("PAT_TOKEN environment variable is required")
    token = raw.strip()  # <-- removes trailing \n / spaces
    if not token:
        die("PAT_TOKEN is empty after stripping")

    # Use modern auth; avoids the deprecation warning
    gh = Github(auth=Auth.Token(token))
    try:
        me = gh.get_user()
    except GithubException as e:
        die(f"[ERROR] auth/user lookup failed: {e}")

    # — Determine repo root & config paths —
    base_dir   = Path(__file__).parent.parent.resolve()
    user_path  = base_dir / "config" / "usernames.txt"
    white_path = base_dir / "config" / "whitelist.txt"
    per_run    = int(os.getenv("FOLLOWERS_PER_RUN", "100"))

    # — Load whitelist —
    if white_path.exists():
        with white_path.open() as f:
            whitelist = {ln.strip().lower() for ln in f if ln.strip()}
    else:
        print("[WARN] config/whitelist.txt not found, proceeding with empty whitelist")
        whitelist = set()

    # — Load candidate usernames —
    if not user_path.exists():
        die(f"Username file not found: {user_path}")
    with user_path.open() as f:
        candidates = [ln.strip() for ln in f if ln.strip()]

    # — Fetch current following list once —
    try:
        following = {u.login.lower(): u for u in me.get_following()}
    except GithubException as e:
        die(f"[ERROR] fetching following list: {e}")

    # --- STEP 2: Follow up to per_run new users ---
    random.shuffle(candidates)
    new_followed = 0
    notfound_new = []
    private_new  = []

    for login in candidates:
        if new_followed >= per_run:
            break

        ll = login.lower()
        if ll == me.login.lower() or ll in whitelist or ll in following:
            continue

        # — existence check —
        try:
            user = gh.get_user(login)
        except GithubException as e:
            if getattr(e, "status", None) == 404:
                notfound_new.append(login)
                print(f"[SKIP] {login} not found")
            else:
                private_new.append(login)
                print(f"[PRIVATE] {login} inaccessible: {e}")
            continue

        # — activity filter (last 30 days) —
        try:
            events = user.get_events()  # public events only
            last_event = next(iter(events), None)  # may trigger API call
            too_old = (datetime.now(timezone.utc) - timedelta(days=30))
            if not last_event or (getattr(last_event, "created_at", None) and last_event.created_at < too_old):
                stamp = getattr(last_event, "created_at", None)
                print(f"[SKIP] {login} inactive (last event: {stamp if stamp else 'none'})")
                continue
        except GithubException as e:
            print(f"[WARN] could not fetch events for {login}, skipping: {e}")
            continue

        # attempt follow
        try:
            me.add_to_following(user)
            new_followed += 1
            print(f"[FOLLOWED] {login} ({new_followed}/{per_run})")
        except GithubException as e:
            if getattr(e, "status", None) == 403:
                private_new.append(login)
                print(f"[PRIVATE] cannot follow {login}: {e}")
            else:
                print(f"[ERROR] follow {login}: {e}")

    print(f"Done follow phase: {new_followed}/{per_run} followed.")
    if notfound_new:
        print("Not found (skipped) during follow phase:", notfound_new)
    if private_new:
        print("Private/inaccessible (skipped) during follow phase:", private_new)

    # --- STEP 3: Follow-back your followers ---
    try:
        followers_map = {u.login.lower(): u for u in me.get_followers()}
    except GithubException as e:
        die(f"[ERROR] fetching followers list: {e}")

    back_count   = 0
    private_back = []

    for login, user in followers_map.items():
        ll = login.lower()
        if ll == me.login.lower() or ll in whitelist or ll in following:
            continue
        try:
            me.add_to_following(user)
            back_count += 1
            print(f"[FOLLOW-BACKED] {login}")
        except GithubException as e:
            if getattr(e, "status", None) == 403:
                private_back.append(login)
                print(f"[PRIVATE] cannot follow-back {login}: {e}")
            else:
                print(f"[ERROR] follow-back {login}: {e}")

    print(f"Done follow-back phase: {back_count} followed-back.")
    if private_back:
        print("Private/inaccessible skipped during follow-back:", private_back)

if __name__ == "__main__":
    main()
