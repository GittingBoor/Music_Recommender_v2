"""Queue songs for the backend's bulk YouTube import.

Reads "Artist - Title" lines and hands them to POST /api/admin/bulk. The
backend works through them one by one (search, download, trim, analyse);
progress shows at the bottom of the Upload page, and songs that did not make
it are listed at GET /api/ingest/failures.

    docker exec -i musicrec-backend-1 python scripts/bulk_youtube_ingest.py < scripts/bulk_songs.txt

/api/admin/ is blocked by nginx, so this runs inside the backend container.
"""
import json
import sys
import urllib.request

API = "http://localhost:8000/api"


def main() -> None:
    queries = [l.strip() for l in sys.stdin if l.strip() and not l.startswith("#")]
    body = json.dumps({"queries": queries}).encode()
    req = urllib.request.Request(f"{API}/admin/bulk", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        print(json.load(r))


if __name__ == "__main__":
    main()
