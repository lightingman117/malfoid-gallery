"""Local receiver for YouTube's PubSubHubbub push notifications.

GET  /callback  -> answers the hub's subscription check with hub.challenge
POST /callback  -> verifies the HMAC signature, then appends each new or
                   deleted video to data/queue.jsonl. Nothing is processed here.

Run it on 127.0.0.1; a public HTTPS tunnel must forward to it (see README.md).
Requires the YT_PUSH_SECRET environment variable.
"""
import hashlib
import hmac
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from common import DATA, QUEUE, load_channels, topic_for

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "at": "http://purl.org/atompub/tombstones/1.0",
}
MAX_BODY = 1024 * 1024
ALLOWED_TOPICS = {topic_for(c["channel_id"]) for c in load_channels()}


def parse_entries(body: bytes) -> list[dict]:
    root = ET.fromstring(body)
    out = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for entry in root.findall("atom:entry", NS):
        vid = entry.findtext("yt:videoId", namespaces=NS)
        if not vid:
            continue
        out.append({
            "received_at": now,
            "kind": "new",
            "video_id": vid,
            "channel_id": entry.findtext("yt:channelId", namespaces=NS),
            "title": entry.findtext("atom:title", namespaces=NS),
            "published": entry.findtext("atom:published", namespaces=NS),
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    for dead in root.findall("at:deleted-entry", NS):
        ref = dead.get("ref", "")
        vid = ref.rsplit(":", 1)[-1]
        out.append({
            "received_at": now,
            "kind": "deleted",
            "video_id": vid,
            "channel_id": None,
            "title": None,
            "published": dead.get("when"),
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "yt-push-receiver"

    def log_message(self, fmt, *args):  # keep stdout quiet; the queue is the record
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _path_ok(self) -> bool:
        return urlsplit(self.path).path == "/callback"

    def do_GET(self):
        if not self._path_ok():
            return self.send_error(404)
        q = parse_qs(urlsplit(self.path).query)
        mode = q.get("hub.mode", [""])[0]
        topic = q.get("hub.topic", [""])[0]
        challenge = q.get("hub.challenge", [""])[0]
        if mode in ("subscribe", "unsubscribe") and topic in ALLOWED_TOPICS and challenge:
            body = challenge.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self):
        if not self._path_ok():
            return self.send_error(404)
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0 or length > MAX_BODY:
            return self.send_error(413 if length > MAX_BODY else 411)
        body = self.rfile.read(length)

        secret = os.environ["YT_PUSH_SECRET"].encode()
        sig = self.headers.get("X-Hub-Signature", "")
        expected = "sha1=" + hmac.new(secret, body, hashlib.sha1).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return self.send_error(403, "bad signature")

        try:
            events = parse_entries(body)
        except ET.ParseError:
            return self.send_error(400, "bad xml")

        if events:
            DATA.mkdir(parents=True, exist_ok=True)
            with QUEUE.open("a", encoding="utf-8") as f:
                for ev in events:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        self.send_response(204)
        self.end_headers()


def main() -> None:
    if not os.environ.get("YT_PUSH_SECRET"):
        sys.exit("Set YT_PUSH_SECRET before starting the receiver.")
    port = int(os.environ.get("YT_PUSH_PORT", "8787"))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"listening on http://127.0.0.1:{port}/callback for {len(ALLOWED_TOPICS)} topics", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
