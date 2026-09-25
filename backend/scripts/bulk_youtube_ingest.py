"""Bulk-add songs through the same API the Upload page uses.

For each "Artist - Title" line: YouTube search -> hits not yet in the
library -> /api/youtube/download (download, trim, analyse, save), trying the
next hit when AcoustID does not recognise one.

    docker exec -i musicrec-backend-1 python scripts/bulk_youtube_ingest.py [max_saved] < songs.txt

Stops once ``max_saved`` songs were saved (default: no limit).
"""
import json
import sys
import time
import urllib.parse
import urllib.request

API = "http://localhost:8000/api"
# Hits tried per song when AcoustID does not recognise the audio.
_ATTEMPTS = 3


def search(query: str) -> list[dict]:
    url = f"{API}/youtube/search?" + urllib.parse.urlencode({"q": query, "limit": 5})
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.load(r)


def download(item: dict) -> dict:
    body = json.dumps({"video_id": item["video_id"], "title": item["title"]}).encode()
    req = urllib.request.Request(f"{API}/youtube/download", data=body,
                                 headers={"Content-Type": "application/json"})
    result: dict = {}
    with urllib.request.urlopen(req, timeout=1800) as r:
        for line in r:
            line = line.strip()
            if line:
                event = json.loads(line)
                if event["stage"] == "done":
                    result = event["result"]
    return result


def main() -> None:
    max_saved = int(sys.argv[1]) if len(sys.argv) > 1 else None
    queries = [l.strip() for l in sys.stdin if l.strip() and not l.startswith("#")]
    counts: dict[str, int] = {}
    for i, q in enumerate(queries, 1):
        t0 = time.time()
        try:
            # Audio-only uploads match AcoustID far more often than music
            # videos with intros, so they are searched first.
            hits = [h for h in search(f"{q} official audio") if not h.get("in_library")]
            status = "skipped (in library / no hit)"
            for hit in hits[:_ATTEMPTS]:
                res = download(hit)
                status = res.get("status", "?")
                if status != "saved":
                    status += f" ({res.get('reason')})"
                if status == "saved" or "duplicate" in status:
                    break
        except Exception as exc:  # keep going on single failures
            status = f"error ({exc})"
        key = status.split(" ")[0]
        counts[key] = counts.get(key, 0) + 1
        print(f"[{i}/{len(queries)}] {q} -> {status} [{time.time() - t0:.0f}s] {counts}", flush=True)
        if max_saved is not None and counts.get("saved", 0) >= max_saved:
            print(f"Reached {max_saved} saved songs, stopping.", flush=True)
            break
        if "bot_check" in status.lower() or "rate" in status.lower():
            time.sleep(300)  # back off if YouTube starts complaining


if __name__ == "__main__":
    main()
