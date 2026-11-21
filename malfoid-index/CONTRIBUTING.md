# Adding a work to the Malfoid Index

The Malfoid Index lists fanfics, fan art, comics, videos and other fan works about Malfoid (genderbent Draco Malfoy). You can submit a work in two ways. The rules are the same for both.

1. **By email** to rhedak@proton.me, with a title, your name or handle, a first name for Malfoid if the work uses one (optional), a link, the language and two or three sentences about the work.
2. **By pull request** on GitHub, described below.

## Using Claude to contribute

Point your Claude at `malfoid-index/contributor-skill/SKILL.md`. It helps you find new works on YouTube, X or the Malfoid Archive, and fill in unverified or unset fields, with the same rules as below. Claude opens a pull request from a branch; it never commits directly to `main` and never opens an issue.

## The rules

- The work is about Malfoid (genderbent Draco Malfoy).
- The work is in English, or has English subtitles.
- The work is wholesome (SFW).
- The link works and stays online.
- The work is not already listed.
- The work's creator and links are not on the blocklist. Before you contribute, check `BLOCKED_ACCOUNTS` and `BLOCKED_DOMAINS` in `scripts/build_site.py`. The build fails if an entry links a blocked account or domain.
- The `creator` field names who made the work. If you made it, use your own name or handle. If you are adding someone else's work, name the creator and say in the pull request that you are not the creator. Reuploads of someone else's work are not added.

Anything that does not follow these rules will not be added.

## Non-English works (the greylist)

The main list shows only works in English or with English subtitles. A work in another language is
still welcome, but it goes on the **greylist** (`malfoid-index/greylist.yaml`) instead:

- The greylist is not shown by default. The index has a checkbox, "Show non-English / unverified", that
  shows it. Greylisted works carry the label "not English / unverified" and are not checked for SFW.
- With the checkbox on, a language row appears, so visitors can pick one language (for example Spanish).
- Add the entry the same way as a main entry, but under `works:` in `greylist.yaml`, and set `language`
  to the language the work is in (for example `"Spanish"` or `"Japanese, English subtitles"`).
- The build does not read `greylist.yaml` into the main list, so a greylisted entry never appears
  without the checkbox.
- A greylisted work can move to the main list once it is confirmed in English or with English subtitles.
  Move its entry from `greylist.yaml` to the end of `works.yaml`, and set `language` to English.

The same rules otherwise apply: the work is about Malfoid, it is SFW, the link works, it is not already
listed, and the work is not a reupload of someone else's work.

## Adding an entry by pull request

1. Fork the repository, or create a branch if you have write access.
2. Open `malfoid-index/works.yaml` and add your entry at the end of the `works:` list. Keep the indentation the same as the other entries.
3. Open a pull request. The pull request template asks you to confirm the rules.

A new entry looks like this:

```yaml
  - id: "fanfic-ao3-123456"
    title: "My Fanfic Title"
    kind: fanfic
    creator: "Your name or handle"
    first_name: ""
    url: "https://archiveofourown.org/works/123456"
    language: "English"
    added: 2026-11-09
    summary: "One or two sentences about the work."
    tags: [romance, slice-of-life]
```

Fields:

- `id`: a short unique slug using the platform and its ID where you can, for example `fanfic-ao3-123456`.
- `title`, `kind`, `url`: required. `kind` is one of `creator`, `comic`, `game`, `fanfic`, `art`, `gallery`, `video`, `music` or `other`, or a list such as `[comic, fanfic]`.
- `creator`, `language`, `added` (the date you submit, `YYYY-MM-DD`), `summary`, `tags`: recommended.
- `first_name`: the first name the work uses for Malfoid, such as Draconia, Dracaena or Draco. Leave it out or blank if the work does not name her. Feeds the name chart on the index.
- `length`: for fanfic only: `one-shot`, `short`, `novel` or `unknown`.
- `thumb`, `also`, `items`, `order`: optional. See the comments at the top of `works.yaml`.

A pull request can also change an entry you already have, for example to fix a link or summary. Edit the same entry and say what changed in the pull request. To remove your work from the index, ask in the pull request or by email.

## What happens next

- A check runs on every pull request and confirms that the index still builds.
- The maintainer reviews the entry and may ask for changes, or decline it.
- When a pull request is merged into `main`, the site is rebuilt and published automatically. This usually takes a few minutes.
