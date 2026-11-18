# YouTube push notifications

Receives YouTube's PubSubHubbub push notifications for the channels in
`channels.json`, queues them, and writes a daily digest. It never edits
`works.yaml`; you decide what to add from the digest.

## Files

- `receiver.py`: HTTP server on 127.0.0.1:8787. Answers the hub's subscription check and appends each notification to `data/queue.jsonl`. Requests without a valid HMAC signature are refused.
- `subscribe.py`: subscribes or renews the channels with the hub. Dry run unless you pass `--apply`. Leases last 5 days.
- `process_daily.py`: reads the queue, skips videos it has already reported, and writes `data/digest-YYYY-MM-DD.md`. Each new video is marked "in index" or "not in index".
- `channels.json`: the channel IDs to subscribe to.
- `launchd/`: templates for running the receiver all the time and the daily job at 09:00 on macOS.

## Setup

1. Pick a secret and export it for every command: `export YT_PUSH_SECRET='choose-a-long-random-string'`
2. Start the receiver: `python3 receiver.py`
3. Make it public over HTTPS. The hub must reach your machine, so this needs a tunnel to 127.0.0.1:8787. A quick tunnel gives a new URL on each start, which breaks the subscriptions, so use a named tunnel with a fixed hostname for the daily job.
4. Check the dry run: `python3 subscribe.py --callback https://YOUR-HOST/callback`
5. Subscribe: `python3 subscribe.py --callback https://YOUR-HOST/callback --apply`. The hub then checks the callback with a GET request, which the receiver answers.
6. Process once: `python3 process_daily.py`, then read `data/digest-*.md`.

The launchd templates contain `REPO`, `SECRET` and `TUNNEL_URL` placeholders. Fill them in, copy them to `~/Library/LaunchAgents/`, and load them with `launchctl`.

## Notes

- A subscription lapses after 5 days. The daily job renews it by running `subscribe.py --apply` before the digest.
- The notification only says which video changed. Titles and channel names come from the notification itself, so the digest does not need a YouTube API key.
- `data/` is git-ignored because it holds the queue and the digests.
