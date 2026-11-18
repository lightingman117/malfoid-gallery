---
name: malfoid-x-daily-scrape
description: Use when asked to run the daily X scrape for Malfoid videos, or to search X for Malfoid video posts over a date range. Opens an X media search for the last two days (yesterday and today) in the user's Chrome, lists the video posts not already in the Malfoid Index, and writes a candidate report. Never edits works.yaml and never posts, likes, follows or logs in.
---

# Daily X scrape for Malfoid videos

The scrape finds X posts with video (`f=media`) that mention Malfoid, posted in a
two-day window. It only reports candidates. Adding an entry is a separate step, done
with `malfoid-index-add-entry`, after the user has reviewed the report.

## Search URL

Build it from these parts. Every run covers **two days**: yesterday and today.

```
https://x.com/search?q=<QUERY>%20until%3A<UNTIL>%20since%3A<SINCE>%20-filter%3Alinks%20-filter%3Areplies&src=typed_query&f=media
```

- `QUERY`: `malfoid` by default. The user can override it, for example `draconia` or `malfoid%20harry`.
- `SINCE`: yesterday, `YYYY-MM-DD`. X includes this day.
- `UNTIL`: **tomorrow**, `YYYY-MM-DD`. X excludes this day, so tomorrow makes today included.
- `-filter:links -filter:replies` drops posts with links and replies. Keep them unless the user says otherwise.
- `f=media` limits results to posts with media. Videos are checked below.

Compute the dates with `date` in the shell (`date -v-1d +%F` for yesterday, `date -v+1d +%F` for tomorrow on macOS), not from memory.

Example for 2026-11-18 (covers 2026-11-17 and 2026-11-18):

```
https://x.com/search?q=malfoid%20until%3A2026-11-19%20since%3A2026-11-17%20-filter%3Alinks%20-filter%3Areplies&src=typed_query&f=media
```

Note: the link the user gave for 2026-11-18 used `until:2026-11-18`, which would
cover only 2026-11-17. Use the tomorrow-based `UNTIL` so both days are included.

## Steps

1. **Open the search in Chrome** with the Claude in Chrome tools (`mcp__claude-in-chrome__*`). Use the user's Chrome, which is signed in to X. Load the tools with ToolSearch first if they are deferred.
2. **Check the page.** If it shows a login wall, a "Something went wrong" error, or a CAPTCHA, stop and tell the user. Do not log in, and do not try to get past a check.
3. **Read the results.** Scroll until no new posts load, or about 15 scrolls, whichever is first. For each post collect: the status URL (`x.com/<user>/status/<id>`), the author handle, the post text, and the post date. Use `get_page_text` or `read_page`, or run JavaScript that reads the `article` elements.
4. **Keep only video posts.** A post counts if it has a video player or a video badge. Image-only posts are dropped. If you cannot tell, keep the post and mark it "video unverified".
5. **Remove known posts.** Skip any post whose status ID is in `malfoid-index/works.yaml` (search the file for the ID), or already in `scripts/x_daily/data/x_seen.json`.
6. **Write the report** to `scripts/x_daily/data/x-candidates-YYYY-MM-DD.md` (today's date). For each candidate: a link, the author, the date, the first line of the text, a note if the video is unverified, and whether the author already appears in the index. Write the file atomically, through a temp file and rename.
7. **Update `x_seen.json`** with every status ID shown in the report, so tomorrow's run does not list it again.
8. **Report back** to the user: how many posts were read, how many videos, how many new candidates, and the report path.

## Limits

- Read only. Never like, repost, reply, follow or post.
- Run it at most once a day. Stop after one full pass.
- X's terms restrict automated access. Keep runs manual or occasional, and do not run it in a loop or with a fast scroll.
- The browser view depends on the search page. If X changes the layout, say so and stop; do not guess post IDs.

## Setup notes

- The data folder `scripts/x_daily/data/` is git-ignored.
- To run it every day, schedule this skill with `/loop` or the `schedule` skill, not with launchd. launchd can't drive the signed-in Chrome.
