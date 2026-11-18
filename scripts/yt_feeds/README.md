# YouTube feed poll

Once a day, checks every YouTube channel linked from `malfoid-index/works.yaml`
through its public RSS feed, and writes a digest of new uploads. It never edits
the index.

## Files

- `build_channels.py`: reads the channel links from `works.yaml`, resolves each to its channel ID, and writes `channels.json`. A channel that can't be resolved keeps its previous entry, with a warning.
- `poll_feeds.py`: reads each channel's feed and records which videos it has seen in `data/seen.json`. New videos go into `data/digest-YYYY-MM-DD.md`, marked "in index" or "not in index".
- `channels.json`: the generated channel list. Don't edit it by hand; run `build_channels.py`.
- `launchd/`: the template for the daily job. The installed copy lives in `~/Library/LaunchAgents/`.
- `tests/`: offline tests. Run `python3 -m unittest discover -s tests` from this folder.

## Daily job

Every day at 09:00, launchd runs `build_channels.py` and then `poll_feeds.py`. Output goes to `data/daily.log`.

- **First run:** every video currently in the feeds is recorded as seen and no digest is written. Use `python3 poll_feeds.py --backfill` on the first run to report them instead.
- **Failed feeds:** a channel whose feed fails is listed in the digest and retried the next day. Its videos aren't marked as seen, so nothing is lost.
- **Limit:** each feed holds the latest 15 uploads, so a channel posting more than 15 videos between runs would lose some.

## Manage the job

Stop it: `launchctl bootout gui/$(id -u)/com.malfoid.yt-feeds-daily`

Start it again: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.malfoid.yt-feeds-daily.plist`

Run it now: `cd scripts/yt_feeds && python3 build_channels.py && python3 poll_feeds.py`

## Deleted-video check

`check_deleted.py` runs after the feed poll. It checks every YouTube video linked from `works.yaml` (about 820) and writes `data/deleted-report-YYYY-MM-DD.md` when something is unavailable, back online, or could not be checked. It also keeps the last known state in `data/video_status.json`.

- A video is only reported as unavailable when the watch page itself says so. A failed oEmbed lookup on its own does not count, because oEmbed has returned false "not found" results for working Shorts.
- A network error is reported as "could not check", never as unavailable.
- It changes nothing in the index. Verify each report entry by hand, then edit the index.
- Playlists and channels are not checked.

Run it now: `python3 check_deleted.py`
