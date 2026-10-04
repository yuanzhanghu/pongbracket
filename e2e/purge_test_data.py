#!/usr/bin/env python3
"""Delete leftover E2E test clubs/tournaments on the local dev instance so the
suite never hits the 32-club subscription cap. Local-only; safe to run anytime.

Deletes tournaments first (they hold dependent stages/matches), then the clubs.
Only touches names starting with E2E- / DEBUG / TEST.
"""
import os
import sys

import requests

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:8401")
EMAIL = os.environ.get("E2E_EMAIL", "e2e@local.test")
PW = os.environ.get("E2E_PASSWORD", "e2e-Passw0rd!")
PREFIXES = ("E2E-", "DEBUG", "TEST")

if "ai1to1.com" in BASE or ":8400" in BASE:
    sys.exit(f"refusing production-like target {BASE!r}")


def main() -> None:
    r = requests.post(
        f"{BASE}/api/token",
        data={"grant_type": "password", "username": EMAIL, "password": PW},
        timeout=15,
    )
    if r.status_code != 200:
        print(f"purge: cannot auth ({r.status_code}); skipping")
        return
    auth = {"Authorization": f"bearer {r.json()['access_token']}", "Accept": "application/json"}

    tourns = requests.get(
        f"{BASE}/api/tournaments?filter_=ALL", headers=auth, timeout=15
    ).json().get("data", [])
    t_del = 0
    for t in tourns:
        if t["name"].startswith(PREFIXES):
            if requests.delete(
                f"{BASE}/api/tournaments/{t['id']}", headers=auth, timeout=15
            ).status_code < 300:
                t_del += 1

    clubs = requests.get(f"{BASE}/api/clubs", headers=auth, timeout=15).json().get("data", [])
    c_del = 0
    for c in clubs:
        if c["name"].startswith(PREFIXES):
            if requests.delete(
                f"{BASE}/api/clubs/{c['id']}", headers=auth, timeout=15
            ).status_code < 300:
                c_del += 1

    remaining = len(requests.get(f"{BASE}/api/clubs", headers=auth, timeout=15).json().get("data", []))
    print(f"purge: deleted {t_del} tournaments, {c_del} clubs; {remaining} clubs remain")


if __name__ == "__main__":
    main()
