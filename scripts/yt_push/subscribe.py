"""Subscribe (or renew) the channels in channels.json with YouTube's hub.

Dry run by default: it prints what it would send. Add --apply to send.
Needs a public HTTPS callback URL (--callback) that forwards to receiver.py,
and the YT_PUSH_SECRET environment variable. Leases last 5 days, so run this
again before they lapse (the launchd job does this daily).
"""
import argparse
import os
import sys
import urllib.parse
import urllib.request

from common import HUB, LEASE_SECONDS, load_channels, topic_for


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--callback", required=True, help="public https URL ending in /callback")
    ap.add_argument("--apply", action="store_true", help="actually send the subscribe requests")
    args = ap.parse_args()

    if not args.callback.startswith("https://") or not args.callback.endswith("/callback"):
        sys.exit("--callback must be a public https URL ending in /callback")
    secret = os.environ.get("YT_PUSH_SECRET")
    if not secret:
        sys.exit("Set YT_PUSH_SECRET first (the same value the receiver uses).")

    for c in load_channels():
        form = {
            "hub.mode": "subscribe",
            "hub.topic": topic_for(c["channel_id"]),
            "hub.callback": args.callback,
            "hub.verify": "async",
            "hub.lease_seconds": str(LEASE_SECONDS),
            "hub.secret": secret,
        }
        label = f"{c['name']} ({c['channel_id']})"
        if not args.apply:
            print(f"would subscribe: {label}")
            continue
        data = urllib.parse.urlencode(form).encode()
        req = urllib.request.Request(HUB, data=data, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                print(f"{resp.status} subscribe requested: {label}")
        except Exception as exc:  # report and keep going for the other channels
            print(f"failed: {label}: {exc}")


if __name__ == "__main__":
    main()
