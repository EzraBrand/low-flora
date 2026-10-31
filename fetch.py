"""Fetch page images of Löw, Die Flora der Juden, from the Frankfurt UB IIIF server.

  uv run fetch.py list IV --from 600 --to 620   # scan index, label, image id
  uv run fetch.py preview I 200 201 202         # 1000px previews for picking pages
  uv run fetch.py sample                        # full-res sample set + data/raw/manifest.json

Scan index = 1-based position in the IIIF manifest (same as the viewer's page counter).
All responses are cached; requests are sequential with a delay.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://sammlungen.ub.uni-frankfurt.de"
RECORD = "http://nbn-resolving.de/urn:nbn:de:hebis:30-180014581006"
# Bd. I is bound as one scan record holding both halves (Bd. 1,1 and 1,2).
VOLUMES = {"I": 104263, "II": 103171, "III": 103724, "IV": 105456}
DELAY = 2.0
DATA = Path(__file__).parent / "data"

# (vol, scan index, why). Picked from previews; see README.
SAMPLE = [
    ("IV", 611, "index"),          # p. 595: start of the Hebrew/Aramaic plant-name index
    ("IV", 650, "index"),          # p. 634: Latin/Greek names
    ("IV", 700, "index"),          # p. 684: dense Hebrew/Aramaic
    *[("IV", s, "abbreviations") for s in range(747, 757)],  # pp. 731-740: Löw's abbreviation list
    *[("I", s, "entry") for s in range(211, 221)],  # pp. 191-200: the whole Pistacia entry
    ("II", 307, "entry"),          # p. 289: Olea, Hebrew verbs, footnote
    ("III", 301, "entry"),         # p. 287: Citrus (etrog), rabbinic sources
    # tables of contents ("Inhalt"); Bd. I has one per half-volume; Bd. III scan 14 and Bd. IV scan 16 are blank
    *[("I", s, "toc") for s in range(17, 21)],
    *[("II", s, "toc") for s in (13, 14)],
    *[("III", s, "toc") for s in (11, 12, 13)],
    *[("IV", s, "toc") for s in range(11, 16)],  # scan 16 is blank
]

session = requests.Session()
session.headers["User-Agent"] = "low-flora OCR test (personal research; sequential, cached)"
_last = 0.0


def get(url: str) -> requests.Response:
    global _last
    wait = DELAY - (time.monotonic() - _last)
    if wait > 0:
        time.sleep(wait)
    r = session.get(url, timeout=120)
    _last = time.monotonic()
    r.raise_for_status()
    return r


def manifest(vol: str) -> dict:
    path = DATA / "cache" / "manifests" / f"{VOLUMES[vol]}.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(get(f"{BASE}/i3f/v20/{VOLUMES[vol]}/manifest").content)
    return json.loads(path.read_text(encoding="utf-8"))


def canvases(vol: str) -> list[dict]:
    out = []
    for i, c in enumerate(manifest(vol)["sequences"][0]["canvases"], start=1):
        res = c["images"][0]["resource"]
        out.append({
            "vol": vol,
            "scan_index": i,
            "label": c["label"],
            # "[608]" = unnumbered page; the viewer then shows the scan index, not a page number.
            "printed_page": None if c["label"].startswith("[") else c["label"],
            "image_id": res["service"]["@id"].rsplit("/", 1)[-1],
            "width": c["width"],
            "height": c["height"],
        })
    return out


def page_key(c: dict) -> str:
    return c["printed_page"] or f"scan{c['scan_index']:04d}"


def download(url: str, path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(get(url).content)
    tmp.replace(path)
    print(f"  saved {path.relative_to(DATA.parent)}", flush=True)


def cmd_list(a):
    for c in canvases(a.vol):
        if a.start <= c["scan_index"] <= a.to:
            print(f"{c['scan_index']:4d}  {c['label']:>8}  {c['image_id']}")


def cmd_preview(a):
    cs = canvases(a.vol)
    for i in a.scan:
        c = cs[i - 1]
        download(f"{BASE}/i3f/v20/{c['image_id']}/full/1000,/0/default.jpg",
                 DATA / "preview" / a.vol / f"{i:04d}_{page_key(c)}.jpg")


def cmd_sample(a):
    records = []
    for vol, scan, why in SAMPLE:
        c = canvases(vol)[scan - 1]
        url = f"{BASE}/i3f/v20/{c['image_id']}/full/full/0/default.jpg"
        path = DATA / "raw" / vol / f"{page_key(c)}.jpg"
        print(f"{vol} scan {scan} = p. {c['label']} ({why})", flush=True)
        download(url, path)
        records.append({**c, "kind": why, "source_url": url, "file": path.relative_to(DATA).as_posix()})
    out = {"work": "Löw, Die Flora der Juden (1924-34)", "record": RECORD,
           "licence": "Public Domain Mark 1.0", "volume_records": VOLUMES, "pages": records}
    (DATA / "raw" / "manifest.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(records)} pages; manifest at data/raw/manifest.json")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(required=True)
    s = sub.add_parser("list")
    s.add_argument("vol", choices=VOLUMES)
    s.add_argument("--from", dest="start", type=int, default=1)
    s.add_argument("--to", type=int, default=10**6)
    s.set_defaults(func=cmd_list)
    s = sub.add_parser("preview")
    s.add_argument("vol", choices=VOLUMES)
    s.add_argument("scan", type=int, nargs="+")
    s.set_defaults(func=cmd_preview)
    s = sub.add_parser("sample")
    s.set_defaults(func=cmd_sample)
    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
