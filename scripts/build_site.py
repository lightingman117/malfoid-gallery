#!/usr/bin/env python3
"""Build the static gallery website (GitHub Pages) from the repo data.

Requires PyYAML for the full gallery data (the built-in fallback in miniyaml.py cannot parse flow
mappings or wrapped scalars); Pillow is only needed for thumbnails.

Reads gallery.yaml, input/*.yaml, plan/daily-malfoid-*.yaml, videos/videos.yaml and the ideas/ lists,
and writes a ready-to-serve folder (default `_site/`, not committed):

  _site/index.html, app.js, style.css, vendor/   copied from site/ (the static source)
  _site/index.json                               one merged record per gallery entry
  _site/thumbs/<id>.webp                         ~480 px wide thumbnails (needs Pillow)
  _site/images/, videos/, references/            the media the pages link to (copied unchanged)
  guest/entries/*.yaml + guest/images/           guest works (see guest/CONTRIBUTING.md), shown with a guest frame

QA notes, seeds, idea prompts and rejected/ are left out on purpose.

    python3 scripts/build_site.py            # build into _site/
    python3 scripts/build_site.py --out /tmp/site --no-thumbs
    cd _site && python3 -m http.server 8000  # preview at http://localhost:8000/
"""
import argparse
import datetime
import glob
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import miniyaml  # noqa: E402

# Accounts that must not be added to the Malfoid Index: they sell subscriptions to AI-made fan content
# of Malfoid, which raises rights-holder concerns. Lower-case handles without the @. The build fails if
# any work's creator, url or `also` link points at one of them. Kept in code only, not published.
BLOCKED_ACCOUNTS = {
    "katechon_studio",  # X: promotes a malfoid.tv subscription charging a monthly fee for AI fan content
    "jack_demonkey",  # X: reposts other people's videos without credit
    "nostalgiawizar",  # X: reuploads other creators' videos without credit
    "3danimationfamily",  # YouTube: reuploads other people's work
    "maelle_gold",  # YouTube: reuploads other creators' videos (J.A. Vázquez's Harry Potter AU and Galakushi's series)
}
# Sites that sell paid access to fan content. A work whose url or `also` link is on one of these
# domains (or a subdomain of it) fails the build too.
BLOCKED_DOMAINS = {
    "malfoid.tv",  # paid subscription service for AI-made fan content of Malfoid and Potter
}

THUMB_WIDTH = 480
THUMB_QUALITY = 80

THEME_NAMES = {
    "autumn": "Autumn", "winter": "Winter", "christmas": "Christmas", "thanksgiving": "Thanksgiving",
    "black-friday": "Black Friday", "everyday": "Everyday", "doodle": "Doodle tests",
    "halloween": "Halloween", "new-year": "New Year", "valentines": "Valentine's", "spring": "Spring",
    "summer": "Summer", "pack-keyframes": "Companion pack: key frames", "pack-activities": "Companion pack: activities",
}
LOCATION_NAMES = {
    "castle": "Castle school", "town": "Town & shops", "home": "Home & cozy", "outdoors": "Outdoors",
    "plain": "Plain background", "": "Unknown",
}
STYLE_NAMES = {"anime": "Anime", "rough-doodle": "Rough doodle", "cel-90s": "90s cel"}
STATUS_NAMES = {"posted": "Posted", "upcoming": "Upcoming", "gallery-only": "Gallery only"}
# Older entries (made before ideas.py) have no `idea:` block; infer their outfit from the prompt.
OUTFIT_HINTS = [
    ("camel coat", "camel-coat"), ("christmas sweater", "christmas-sweater"),
    ("cream knit sweater", "cream-sweater-plaid"), ("gown", "gown"), ("black robe", "uniform-robe"),
    ("hooded robe", "uniform-robe"), ("grey vest", "uniform-vest"),
]


def load(path):
    return miniyaml.load(os.path.join(ROOT, path))


def humanize(s):
    return (s or "").replace("-", " ").strip().capitalize()


def by_id(items):
    return {x["id"]: x for x in items or []}


def is_animated(rel):
    """True for an animated WebP/GIF (companion pack activities); needs Pillow, else False."""
    if not rel.lower().endswith((".webp", ".gif")):
        return False
    try:
        from PIL import Image
        with Image.open(os.path.join(ROOT, rel)) as im:
            return getattr(im, "n_frames", 1) > 1
    except Exception:
        return False


def location_group(setting, tags, style):
    stags = set((setting or {}).get("tags") or [])
    if setting:
        if "castle" in stags:
            return "castle"
        if "city" in stags:
            return "town"
        if "indoor" in stags:
            return "home"
        return "outdoors"
    if style and style != "anime":
        return "plain"
    tags = set(tags)
    if "companion-pack" in tags:
        return "plain"
    if "castle" in tags:
        return "castle"
    if tags & {"park", "leaves"}:
        return "outdoors"
    if tags & {"food", "cozy", "christmas", "thanksgiving"}:
        return "home"
    return ""


def infer_outfit(prompt):
    p = (prompt or "").lower()
    for hint, oid in OUTFIT_HINTS:
        if hint in p:
            return oid
    return None


def size_of(s):
    try:
        w, h = (int(x) for x in str(s).lower().split("x"))
        return w, h
    except Exception:
        return None, None


def captions_of(day):
    out = {}
    for platform in ("x", "instagram", "tiktok", "rednote"):
        block = day.get(platform)
        if isinstance(block, dict):
            out[platform] = {k: v for k, v in block.items() if v not in (None, "")}
    return out


def posted_of(value):
    """`posted:` is empty, a date, or {date, x, instagram, ...}."""
    if not value:
        return None
    if isinstance(value, dict):
        links = {k: v for k, v in value.items() if k != "date" and isinstance(v, str) and v.startswith("http")}
        return {"date": str(value.get("date") or ""), "links": links}
    return {"date": str(value), "links": {}}


GUEST_DIR = "guest/entries"


def _http(value):
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def guest_problems(g, stem):
    """Checks a guest entry (guest/entries/<id>.yaml) and returns a list of problems; empty when it is fine."""
    problems = []
    if not isinstance(g, dict):
        return ["not a YAML mapping"]
    if str(g.get("id") or "") != stem:
        problems.append("id must match the file name (%s)" % stem)
    for key in ("title", "artist", "license"):
        if not str(g.get(key) or "").strip():
            problems.append("missing %s" % key)
    if g.get("rights_confirmed") is not True:
        problems.append("rights_confirmed must be true (the submitter confirms the rights and credit)")
    if not isinstance(g.get("ai_generated"), bool):
        problems.append("ai_generated must be true or false")
    elif g["ai_generated"] and not str(g.get("model") or "").strip():
        problems.append("model is required when ai_generated is true")
    if not str(g.get("created") or "").strip():
        problems.append("missing created (date submitted, YYYY-MM-DD)")
    image = str(g.get("image") or "")
    image_url = str(g.get("image_url") or "")
    if bool(image) == bool(image_url):
        problems.append("set exactly one of image (a file in guest/images/) or image_url (an https link)")
    elif image:
        if not image.startswith("guest/images/"):
            problems.append("image must be under guest/images/")
        elif not os.path.isfile(os.path.join(ROOT, image)):
            problems.append("image file not found: %s" % image)
    elif not _http(image_url):
        problems.append("image_url must be an http or https link")
    for key in ("artist_url", "source"):
        if g.get(key) and not _http(g.get(key)):
            problems.append("%s must be an http or https link" % key)
    return problems


def guest_records(start_order):
    """Guest works as gallery records: shown in the gallery, never posted (no plan, no planned date)."""
    records = []
    for path in sorted(glob.glob(os.path.join(ROOT, GUEST_DIR, "*.yaml"))):
        rel = os.path.relpath(path, ROOT)
        stem = os.path.splitext(os.path.basename(path))[0]
        g = miniyaml.load(path)
        problems = guest_problems(g, stem)
        if problems:
            raise SystemExit("%s:\n  - %s" % (rel, "\n  - ".join(problems)))
        ai = g["ai_generated"]
        model = str(g.get("model") or "").strip() if ai else ""
        external = "image_url" in g and bool(str(g.get("image_url") or "").strip())
        image = str(g["image_url"]).strip() if external else str(g["image"])
        records.append({
            "id": stem,
            "order": start_order + len(records),
            "title": str(g["title"]).strip(),
            "created": str(g["created"]),
            "theme": "",
            "themeName": "",
            "tags": list(g.get("tags") or []),
            "style": "anime",
            "styleName": STYLE_NAMES["anime"],
            "styleDesc": None,
            "variant": None,
            "status": "gallery-only",
            "planned": None,
            "posted": None,
            "image": image,
            # External images are shown from the artist's host: no local copy or thumbnail is made.
            "thumb": image if external else "thumbs/%s.webp" % stem,
            "width": None,
            "height": None,
            "prompt": "",
            "tool": ("AI-generated: " + model) if ai else "Not AI-generated",
            "basePost": None,
            "resultPost": None,
            "reference": None,
            "poseRef": None,
            "poseName": None,
            "poseView": None,
            "outfit": None,
            "outfitName": None,
            "emotion": None,
            "emotionName": None,
            "setting": None,
            "settingName": None,
            "location": "",
            "locationName": LOCATION_NAMES[""],
            "season": None,
            "media": "animation" if not external and is_animated(image) else "image",
            "source": None,
            "guest": {
                "external": external,
                "artist": str(g["artist"]).strip(),
                "artistUrl": g.get("artist_url") or None,
                "source": g.get("source") or None,
                "license": str(g["license"]).strip(),
                "aiGenerated": ai,
                "model": model or None,
                "note": str(g.get("note") or "").strip() or None,
            },
        })
    return records


def build_index():
    gallery = load("gallery.yaml")["entries"]
    outfits = by_id(load("ideas/outfits.yaml").get("outfits"))
    settings = by_id(load("ideas/settings.yaml").get("settings"))
    emotions = by_id(load("ideas/emotions.yaml").get("emotions"))
    styles = by_id(load("ideas/styles.yaml").get("styles"))
    videos = by_id(load("videos/videos.yaml"))
    days = {}
    for plan_path in sorted(glob.glob(os.path.join(ROOT, "plan", "daily-malfoid-*.yaml"))):
        plan = load(os.path.relpath(plan_path, ROOT))
        for day in plan.get("days") or []:
            days[day["id"]] = dict(day, series=plan.get("series", "Daily Malfoid"))

    entries = []
    for order, g in enumerate(gallery):
        inp = load(g["input"])
        idea = inp.get("idea") if isinstance(inp.get("idea"), dict) else {}
        tags = list(inp.get("tags") or [])
        style = idea.get("style") or next((t[6:] for t in tags if t.startswith("style-")), None) or "anime"
        outfit = idea.get("outfit") or infer_outfit(inp.get("prompt"))
        setting = settings.get(idea.get("setting")) if idea.get("setting") else None
        emotion = idea.get("emotion")
        day = days.get(g["id"])
        video = videos.get(g["id"])
        gallery_only = bool(g.get("gallery_only") or inp.get("gallery_only"))
        posted = posted_of(g.get("posted"))
        status = "gallery-only" if gallery_only else ("posted" if posted else "upcoming")
        w, h = size_of(inp.get("size"))
        pose_name = idea.get("pose_name")
        rec = {
            "id": g["id"],
            "order": order,
            "title": inp.get("title") or g.get("title"),
            "created": str(g.get("created") or inp.get("created") or ""),
            "theme": inp.get("theme") or "",
            "themeName": THEME_NAMES.get(inp.get("theme"), humanize(inp.get("theme"))),
            "tags": tags,
            "style": style,
            "styleName": STYLE_NAMES.get(style, humanize(style)),
            "styleDesc": (styles.get(style) or {}).get("name"),
            "variant": idea.get("variant"),
            "status": status,
            "planned": str(g["planned"]) if g.get("planned") else None,
            "posted": posted,
            "image": g["image"],
            "thumb": "thumbs/%s.webp" % g["id"],
            "width": w,
            "height": h,
            "prompt": inp.get("prompt") or "",
            "tool": inp.get("tool"),
            "basePost": inp.get("base_post"),
            "resultPost": inp.get("result_post"),
            "reference": inp.get("reference"),
            "poseRef": inp.get("pose_ref"),
            "poseName": pose_name,
            "poseView": idea.get("pose_view"),
            "outfit": outfit,
            "outfitName": (outfits.get(outfit) or {}).get("name", humanize(outfit)) if outfit else None,
            "emotion": emotion,
            "emotionName": (emotions.get(emotion) or {}).get("name", humanize(emotion)) if emotion else None,
            "setting": idea.get("setting"),
            "settingName": (setting or {}).get("name"),
            "location": location_group(setting, tags, style),
            "season": idea.get("season"),
            "media": "video" if video else ("animation" if is_animated(g["image"]) else "image"),
            "source": inp.get("source"),
        }
        rec["locationName"] = LOCATION_NAMES[rec["location"]]
        if day:
            rec["daily"] = {
                "series": day.get("series"), "n": day.get("n"), "label": day.get("label"),
                "date": str(day.get("date")), "type": day.get("type"), "theme": day.get("theme"),
                "captions": captions_of(day),
            }
        if video:
            rec["video"] = {
                "src": video.get("video"), "post": video.get("video_post"),
                "sourcePost": video.get("source_post"), "motion": video.get("motion"),
            }
        entries.append(rec)

    entries += guest_records(len(entries))

    return {
        "title": "Malfoid Gallery",
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "repo": "https://github.com/rhedak/malfoid-gallery",
        "labels": {"status": STATUS_NAMES, "location": LOCATION_NAMES, "theme": THEME_NAMES},
        "entries": entries,
    }


def _as_list(value):
    """A YAML list, or one value as a one-item list (never the characters of a string)."""
    if not value:
        return []
    return value if isinstance(value, list) else [value]


def work_urls(w):
    """Every http(s) link stored on a work, including embed, video and item links."""
    urls = [w.get("url"), w.get("embed")]
    urls += _as_list(w.get("also")) + _as_list(w.get("embed_also"))
    for v in _as_list(w.get("videos")):
        if isinstance(v, dict):
            urls += [v.get("url"), v.get("embed")] + _as_list(v.get("also"))
        else:
            urls.append(v)
    for it in _as_list(w.get("items")):
        if isinstance(it, dict):
            urls += [it.get("url")] + _as_list(it.get("also"))
    return [u for u in (str(x or "").strip() for x in urls) if u.startswith(("http://", "https://"))]


def social_handles(w):
    """Handles read from the work's own links (YouTube @handles and X profile handles), for search only."""
    import re
    from urllib.parse import urlparse, unquote
    X_SKIP = {"i", "home", "search", "explore", "intent", "share", "hashtag", "notifications", "messages"}
    out = []
    for u in work_urls(w):
        host = (urlparse(u).hostname or "").lower()
        path = unquote(urlparse(u).path)
        if host.endswith("youtube.com"):
            m = re.match(r"/@([^/?#]+)", path)
            if m:
                out.append(m.group(1))
        elif host in ("x.com", "twitter.com", "www.x.com", "www.twitter.com"):
            seg = path.strip("/").split("/")[0]
            if seg and seg.lower() not in X_SKIP and re.fullmatch(r"[A-Za-z0-9_]{1,30}", seg):
                out.append(seg)
    seen, res = set(), []
    for h in out:
        if h.lower() not in seen:
            seen.add(h.lower())
            res.append(h)
    return res


def blocked_handle(w):
    """The blocked account or domain a work links to (creator, handles or any URL), or None."""
    from urllib.parse import urlparse
    urls = work_urls(w)
    creator = str(w.get("creator") or "").strip()
    if creator.startswith(("http://", "https://")):
        urls.append(creator)
    for u in urls:
        host = (urlparse(u).hostname or "").lower()
        for d in BLOCKED_DOMAINS:
            if host == d or host.endswith("." + d):
                return d
    names = [creator.lstrip("@")]
    names += [str(h or "").strip().lstrip("@") for h in _as_list(w.get("handles"))]
    if creator.startswith(("http://", "https://")):
        names += social_handles({"url": creator})
    names += social_handles(w)
    for h in names:
        if h and h.lower() in BLOCKED_ACCOUNTS:
            return h
    return None


def kinds_of(value):
    """`kind:` is one value or a list (e.g. [other, fanfic]); the first is the primary kind."""
    items = value if isinstance(value, list) else [value]
    out = []
    for k in items:
        k = "" if k is None else str(k).strip().lower()
        if k and k not in out:
            out.append(k)
    return out or ["other"]


LENGTHS = ("one-shot", "short", "novel", "unknown")
FORMATS = ("anime", "cinematic", "audiobook", "other")


def length_of(value):
    """The optional `length` field for fanfic: one-shot, short, novel or unknown (the default)."""
    v = "" if value is None else str(value).strip().lower()
    return v if v in LENGTHS else "unknown"


def format_of(value):
    """The optional `format` field for videos: anime, cinematic, audiobook or other (the default)."""
    v = "" if value is None else str(value).strip().lower()
    return v if v in FORMATS else "other"


def order_of(value):
    """The optional `order` field: a number, or None when the work has none."""
    try:
        return int(value) if value is not None and str(value).strip() != "" else None
    except (TypeError, ValueError):
        return None


def build_works():
    """The Malfoid Index sub page: malfoid-index/works.yaml -> works.json (ordered works first, then A-Z by title)."""
    data = load("malfoid-index/works.yaml")

    def text(v):
        return "" if v is None else str(v).strip()

    def thumb_of(w):
        """An https image, or a banner file in site/malfoid-index/banners/ (copied with the site)."""
        t = text(w.get("thumb"))
        if t.startswith("https://"):
            return t
        if t.startswith("banners/") and ".." not in t and os.path.isfile(os.path.join(ROOT, "site", "malfoid-index", t)):
            return t
        return ""

    def embed_of(w):
        """An embeddable player for a YouTube video or playlist, a Rumble embed page or a public X post. Anything else is left out."""
        from urllib.parse import urlparse, parse_qs
        import re
        u = text(w.get("embed"))
        # A video kept in this repo (videos/*.mp4, the gallery's own clips): played from the site, one folder up.
        if re.match(r"^videos/[A-Za-z0-9._-]+\.mp4$", u):
            return "../" + u
        if not u.startswith("https://"):
            return ""
        p = urlparse(u)
        host = (p.hostname or "").lower()
        q = parse_qs(p.query)
        ok_id = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
        if host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
            if p.path == "/watch" and ok_id.match(q.get("v", [""])[0]):
                src = "https://www.youtube-nocookie.com/embed/" + q["v"][0]
                if ok_id.match(q.get("list", [""])[0]):
                    src += "?list=" + q["list"][0]
                return src
            if p.path.startswith("/shorts/") and ok_id.match(p.path.split("/")[2] if p.path.count("/")>=2 else ""):
                return "https://www.youtube-nocookie.com/embed/" + p.path.split("/")[2]
            if p.path == "/playlist" and ok_id.match(q.get("list", [""])[0]):
                return "https://www.youtube-nocookie.com/embed/videoseries?list=" + q["list"][0]
            return ""
        if host == "youtu.be" and ok_id.match(p.path.strip("/")):
            return "https://www.youtube-nocookie.com/embed/" + p.path.strip("/")
        # A Google Drive video file (shared by link): its preview player. Folders cannot be embedded.
        if host == "drive.google.com":
            m = re.match(r"^/file/d/([A-Za-z0-9_-]{10,})(?:/[a-z]*)?$", p.path)
            if m:
                return "https://drive.google.com/file/d/" + m.group(1) + "/preview"
            return ""
        if host == "rumble.com" and p.path.startswith("/embed/"):
            return "https://rumble.com" + p.path + ("?" + p.query if p.query else "")
        m = re.match(r"^/(v[a-z0-9]+)-[^/]*\.html$", p.path)
        if host == "rumble.com" and m:
            return "https://rumble.com/embed/" + m.group(1) + "/"
        # A public X post: its video plays in X's own tweet embed (only the post id is used).
        m = re.match(r"^/[A-Za-z0-9_]{1,30}/status/(\d{5,25})$", p.path)
        if host in ("x.com", "www.x.com", "twitter.com", "www.twitter.com") and m:
            return "https://platform.twitter.com/embed/Tweet.html?id=" + m.group(1)
        # A public Instagram post or reel: its embed page (only the shortcode is used).
        m = re.match(r"^/(p|reel)/([A-Za-z0-9_-]{5,20})/?$", p.path)
        if host in ("instagram.com", "www.instagram.com") and m:
            return "https://www.instagram.com/" + m.group(1) + "/" + m.group(2) + "/embed/"
        # A Bilibili video page (English or Chinese path): its BV id plays in Bilibili's external player.
        m = re.match(r"^/(?:[a-z]{2}/)?video/(BV[A-Za-z0-9]{10})/?$", p.path)
        if host in ("bilibili.com", "www.bilibili.com") and m:
            return "https://player.bilibili.com/player.html?bvid=" + m.group(1) + "&page=1"
        return ""

    def videos_of(w):
        """The videos listed under `videos:` (Rumble or YouTube links), each with its player address and an episode label."""
        import re
        out = []
        for i, v in enumerate(w.get("videos") or []):
            # A video is either a link, or {url, label} to name it (e.g. its YouTube title).
            given = text(v.get("label")) if isinstance(v, dict) else ""
            u = text(v.get("url") if isinstance(v, dict) else v)
            src = embed_of({"embed": u})
            if not src:
                continue
            m = re.search(r"s(\d{2})e(\d{2})", u, re.I)
            label = given or ("Season %d, episode %d" % (int(m.group(1)), int(m.group(2))) if m else "Episode %d" % (i + 1))
            # Optional `also`: other places this video is posted (X, YouTube), shown under its player.
            also = [text(a) for a in (v.get("also") or []) if text(a).startswith(("http://", "https://"))] if isinstance(v, dict) else []
            out.append({"url": u, "embed": src, "label": label, "also": also})
        return out

    def watch_of(w):
        """A link at the top of a card to another entry's sub page: {"label", "id"}, or None."""
        watch = w.get("watch")
        if not isinstance(watch, dict) or not text(watch.get("id")):
            return None
        return {"label": text(watch.get("label")) or "Watch now", "id": text(watch.get("id"))}

    def more_of(w):
        """A link under the summary to more videos elsewhere: {"label", "url"} (https only), or None."""
        more = w.get("more")
        if not isinstance(more, dict) or not text(more.get("url")).startswith(("http://", "https://")):
            return None
        return {"label": text(more.get("label")) or "More related videos on YouTube", "url": text(more.get("url"))}

    # The greylist (archive creators not confirmed as English) is built too, flagged, and hidden unless the page asks for it.
    grey = load("malfoid-index/greylist.yaml") if os.path.exists(os.path.join(ROOT, "malfoid-index", "greylist.yaml")) else {}
    works = []
    for w, is_grey in [(w, False) for w in data.get("works") or []] + [(w, True) for w in (grey or {}).get("works") or []]:
        if not isinstance(w, dict) or not text(w.get("title")):
            continue
        bad = blocked_handle(w)
        if bad:
            # Fail the build rather than hide the work: a listed account must not be added or kept.
            sys.exit("error: %r links to a blocked account or site %r (see BLOCKED_ACCOUNTS and BLOCKED_DOMAINS in scripts/build_site.py)"
                     % (text(w.get("title")), bad))
        tags = w.get("tags") or []
        # a creator with many works lists them under `items`; the sub page shows these
        items = []
        for it in (w.get("items") or []):
            if isinstance(it, dict) and text(it.get("title")):
                items.append({
                    "title": text(it.get("title")),
                    "url": text(it.get("url")),
                    "added": text(it.get("added")),
                    "summary": text(it.get("summary")),
                    "also": [text(u) for u in (it.get("also") or []) if text(u).startswith(("http://", "https://"))],
                })
        works.append({
            "items": items,
            "id": text(w.get("id")),
            "title": text(w.get("title")),
            "kinds": kinds_of(w.get("kind")),
            "creator": text(w.get("creator")),
            "url": text(w.get("url")),
            "language": text(w.get("language")),
            "added": text(w.get("added")),
            "summary": text(w.get("summary")),
            "tags": [text(t) for t in (tags if isinstance(tags, list) else [tags]) if text(t)],
            "thumb": thumb_of(w),
            "embed": embed_of(w),
            "embed_label": text(w.get("embed_label")),
            "embed_also": [text(u) for u in (w.get("embed_also") or []) if text(u).startswith(("http://", "https://"))],
            "videos": videos_of(w),
            "also": [text(u) for u in (w.get("also") or []) if text(u).startswith(("http://", "https://"))],
            "watch": watch_of(w),
            "more": more_of(w),
            "order": order_of(w.get("order")),
            "length": length_of(w.get("length")),
            "format": format_of(w.get("format")),
            "first_name": text(w.get("first_name")),
            "greylisted": is_grey,
            "handles": list(dict.fromkeys([text(h) for h in (w.get("handles") or []) if text(h)] + social_handles(w))),
        })
    works.sort(key=lambda w: (w["order"] is None, w["order"] or 0, w["title"].lower()))
    return {"title": text(data.get("title")) or "Malfoid Index", "contact": text(data.get("contact")), "works": works}


def copy(rel, out):
    src, dst = os.path.join(ROOT, rel), os.path.join(out, rel)
    if not os.path.isfile(src):
        raise SystemExit("error: the gallery references a missing file: %s" % rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
        shutil.copy2(src, dst)


def make_thumb(src, dst):
    from PIL import Image  # imported lazily so --no-thumbs works without Pillow
    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with Image.open(src) as im:
        if im.mode in ("RGBA", "LA", "P"):  # pack frames are transparent: put them on the site's dark panel colour
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (16, 26, 22, 255))
            bg.alpha_composite(im)
            im = bg
        im = im.convert("RGB")
        if im.width > THUMB_WIDTH:
            im = im.resize((THUMB_WIDTH, round(im.height * THUMB_WIDTH / im.width)), Image.LANCZOS)
        im.save(dst, "WEBP", quality=THUMB_QUALITY, method=6)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"), help="output folder (default: _site/)")
    ap.add_argument("--no-thumbs", action="store_true", help="skip thumbnails (no Pillow needed; PyYAML still required)")
    args = ap.parse_args()
    if miniyaml._pyyaml is None:
        raise SystemExit("error: PyYAML is required to build the site (pip install pyyaml); "
                         "the built-in fallback cannot parse all gallery data")
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    src_dir = os.path.join(ROOT, "site")
    for base, _dirs, files in os.walk(src_dir):
        for name in files:
            rel = os.path.relpath(os.path.join(base, name), src_dir)
            os.makedirs(os.path.join(out, os.path.dirname(rel)), exist_ok=True)
            shutil.copy2(os.path.join(base, name), os.path.join(out, rel))
    open(os.path.join(out, ".nojekyll"), "w").close()

    index = build_index()
    made = 0
    for e in index["entries"]:
        if not _http(e["image"]):
            copy(e["image"], out)
        for rel in (e.get("reference"), e.get("poseRef"), (e.get("video") or {}).get("src")):
            if rel:
                copy(rel, out)
        if not args.no_thumbs and not _http(e["image"]):
            made += make_thumb(os.path.join(ROOT, e["image"]), os.path.join(out, e["thumb"]))
    with open(os.path.join(out, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))
    works = build_works()
    for w in works["works"]:
        for v in w.get("videos") or []:
            e = v.get("embed") or ""
            if e.startswith("../videos/"):
                copy(e[3:], out)
    os.makedirs(os.path.join(out, "malfoid-index"), exist_ok=True)
    with open(os.path.join(out, "malfoid-index", "works.json"), "w", encoding="utf-8") as f:
        json.dump(works, f, ensure_ascii=False, separators=(",", ":"))
    print("built %s: %d entries, %d new thumbnails, %d index works" % (
        os.path.relpath(out, os.getcwd()), len(index["entries"]), made, len(works["works"])))


if __name__ == "__main__":
    main()
