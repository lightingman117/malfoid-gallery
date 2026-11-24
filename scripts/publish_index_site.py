#!/usr/bin/env python3
"""Split the built gallery site into the two published sites.

Input: the output folder of scripts/build_site.py (the gallery, served at malfoid.jp).
Writes:
  <index_out>   the Malfoid Index at the root, for malfoid-index.com (its own Pages repo)
  <gallery_out> the same folder with malfoid-index/ replaced by a redirect to malfoid-index.com

The index pages reference the gallery's shared files with "../" (favicons, style.css). On the
index site they are copied to the root and the paths are rewritten to match.

Usage:
    python3 scripts/publish_index_site.py <gallery_out> <index_out>
"""
import os
import shutil
import sys

INDEX_HOST = "https://malfoid-index.com/"
GALLERY_HOST = "https://malfoid.jp/"
SHARED = ["favicon.ico", "favicon-32.png", "apple-touch-icon.png", "style.css", "site.webmanifest"]


def main(gallery, index):
    src = os.path.join(gallery, "malfoid-index")
    if not os.path.isfile(os.path.join(src, "index.html")):
        sys.exit("no malfoid-index/index.html in " + gallery)

    # 1. The index site: its own pages at the root.
    if os.path.exists(index):
        shutil.rmtree(index)
    shutil.copytree(src, index)
    for name in SHARED:
        if os.path.isfile(os.path.join(gallery, name)):
            shutil.copy2(os.path.join(gallery, name), os.path.join(index, name))
    html_path = os.path.join(index, "index.html")
    html = open(html_path, encoding="utf-8").read()
    html = html.replace('href="../"', 'href="%s"' % GALLERY_HOST)  # the "← Malfoid Gallery" link
    html = html.replace('href="../', 'href="./').replace('href="../', 'href="./')
    html = html.replace('"../', '"./')
    html = html.replace("https://rhedak.github.io/malfoid-gallery/malfoid-index/", INDEX_HOST)
    open(html_path, "w", encoding="utf-8").write(html)
    with open(os.path.join(index, "CNAME"), "w", encoding="utf-8") as f:
        f.write("malfoid-index.com\n")
    open(os.path.join(index, ".nojekyll"), "w").close()

    # 2. The gallery site: malfoid.jp/malfoid-index/ forwards to the index's own domain.
    shutil.rmtree(src)
    os.makedirs(src)
    with open(os.path.join(src, "index.html"), "w", encoding="utf-8") as f:
        f.write(
            '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<title>Malfoid Index</title>\n'
            '<meta http-equiv="refresh" content="0; url=%(h)s">\n'
            '<link rel="canonical" href="%(h)s">\n</head>\n<body>\n'
            '<p>The Malfoid Index has moved to <a href="%(h)s">malfoid-index.com</a>.</p>\n'
            '<script>location.replace("%(h)s");</script>\n</body>\n</html>\n' % {"h": INDEX_HOST}
        )
    print("published index site: %s, gallery redirect: %s" % (index, src))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
