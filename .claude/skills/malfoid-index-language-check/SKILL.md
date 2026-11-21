---
name: malfoid-index-language-check
description: Use when setting or checking the language field of a Malfoid Index entry (malfoid-index/works.yaml or greylist.yaml) for a YouTube video or creator, especially to tell whether the audio is English and whether the subtitles are real or hard-coded. Covers reading the caption and audio tracks from the page, when to sample frames, and what to write.
---

# Checking the language of a video

The `language` field says what the work is in. For videos, it means the **audio** language plus any subtitles the viewer can use. Entries say things like `English`, `English, Korean subtitles` or `Spanish`.

## Signals, in order of reliability

1. **Auto-generated English captions** (`English (auto-generated)`, `kind: asr`). YouTube only makes these from speech it can hear, so an `asr` track in language X means the spoken audio is language X. This is the main signal for the audio language. Accept it as the audio language.
2. **Other caption tracks.** A real (uploaded) track in language Y means subtitles in Y are available. A caption track in the page list means the viewer can turn it on. Subtitles in another language are not a sign that the audio is in that language.
3. **Audio tracks.** YouTube lists alternate audio only for videos with dubs or several audio tracks. Empty means one track, so the audio is the one in (1).
4. **Burned-in (hard-coded) subtitles.** These are in the picture and do not appear in the caption list. Check them by sampling frames (below), because a caption list cannot show them.
5. **Auto-translate** is a machine option in the subtitle menu. It is not a subtitle track of the video. Do not count it.

If there is no `asr` track and no caption track, the audio language is unknown: sample frames, and say so in the entry notes rather than guessing.

## Reading the caption and audio tracks (no playback needed)

Open the watch page in the browser, wait about 3 seconds, then read the page's player data. Use a synchronous expression, because a Promise comes back as `{}`:

```js
JSON.stringify((() => { const pr = window.ytInitialPlayerResponse; if (!pr) return {err:'no var'}; const caps = (pr.captions?.playerCaptionsTracklistRenderer?.captionTracks||[]).map(t=>({lang:t.languageCode, name:t.name?.simpleText, asr:t.kind==='asr'})); const fmts = [...(pr.streamingData?.adaptiveFormats||[]), ...(pr.streamingData?.formats||[])]; const audio = [...new Set(fmts.filter(f=>f.audioTrack).map(f=>JSON.stringify({id:f.audioTrack.id, name:f.audioTrack.displayName})))]; return { id: pr.videoDetails?.videoId, title: pr.videoDetails?.title, captions: caps, audioTracks: audio }; })())
```

The subtitle menu (the gear icon, then Subtitles/CC) shows the same tracks, plus Off and Auto-translate. Ads can cover the menu; the page data above avoids that.

## Sampling frames for burned-in subtitles

1. If an ad is playing (`document.querySelector('.ad-showing')`), wait for it to end or skip. Do not sample an ad frame.
2. Pause and seek, then take a screenshot:
   ```js
   (async () => { const v = document.querySelector('video'); v.pause(); v.currentTime = 60; await new Promise(r=>setTimeout(r,1500)); return v.currentTime; })()
   ```
3. Sample three points, for example about 20 seconds, about 1 minute and about 2 minutes, or spread across the length. Subtitles are not on every frame, so one blank frame proves nothing. Stop as soon as the answer is clear.
4. Read the text on the frame. A `>>` line in English means English speech or English subtitles are burned in.

## Deciding the field

- Audio is English (asr `en`) and no other subtitle text is seen: `English`.
- Audio is English and there are real or burned-in subtitles in another language: `English, <Language> subtitles`. Only use this when that subtitle language is actually seen in the caption list or in a frame.
- Audio is in another language: that language, for example `Spanish`. Put the entry in `greylist.yaml` if it is not English, as the greylist rules say.
- Unknown: leave `language` as it is and note the gap in the PR.

For a creator entry with several videos, check at least one long video and one short, and say which ones were checked. Shorts can differ from the long videos, so do not generalise from one kind to the other without saying so.

## Recording the decision

Write the language in the entry's `language` field and, if it changed, the summary too. In the PR description, list each video checked, its caption tracks, whether subtitles were seen in frames, and the timestamps sampled. Then run the build check from the `malfoid-index-add-entry` skill.
