"""Build and maintain the table of abbreviations and short references used on the OCR'd pages.

  uv run abbrev.py              # scan main-text pages not yet scanned; update abbreviations.json + ABBREVIATIONS.md
  uv run abbrev.py --render     # only re-render ABBREVIATIONS.md from abbreviations.json

For each main-text page (gold text if it exists, else OCR), a model lists every abbreviation,
short title and author-name reference, and expands it from Löw's own list (Bd. IV pp. 731-740,
OCR'd in data/ocr/{SOURCE}/IV/), or from general knowledge (marked), or marks it unknown.
abbreviations.json is the maintained file: new rows are added, existing rows only get new page
numbers. A row with "checked": true is never changed by the script; edit those by hand.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent
DATA = ROOT / "data"
TABLE = ROOT / "abbreviations.json"
OUT_MD = ROOT / "ABBREVIATIONS.md"
SOURCE = "or-claude-opus-5.5@low+ital"
MODEL = "anthropic/claude-opus-5.5"
KEY_FILE = Path.home() / "Desktop/Misc/key.txt"
KINDS = {"general": "General abbreviations",
         "source": "Primary sources (Bible, rabbinic, Syriac, Arabic texts)",
         "bibliography": "Bibliography (authors, journals, reference works)"}

PROMPT = """\
Below are (1) the author's list of abbreviations from Immanuel Löw, "Die Flora der Juden" \
vol. 4 pp. 731-740 (OCR text), and (2) one page of the work.

List every abbreviation, shortened word, short title and author-name reference that occurs on \
the page (2), each once: e.g. "Hg.", "assyr.", "palmyr.", "n. pr.", "BB.", "Gal.-Üb.", "ZDPV.", \
"Rh.", "jKil.", "Targ.", "Guigues", "Fraenkel", "Sachau Inedita". Include general German \
abbreviations (d. h., vgl., u. a., f., ff., LW.), language names (arab., syr.), sources \
(Bible books, Mishnah/Talmud tractates, midrashim) and bibliography (authors and works cited by \
name only). Do not list plant names, full words or numbers.

For each item give:
- "abbr": as printed on the page (without italics tags).
- "kind": "general", "source" or "bibliography".
- "expansion": the full form in English (for bibliography: author, title, place and year as \
far as known). Translate German expansions into English but keep titles in their language.
- "basis": "Löw list" if the expansion comes from list (1); "general knowledge" if you know it \
from elsewhere; "unknown" if you do not know (then "expansion" is your best guess or "").
- "list_entry": for "Löw list", the entry text copied from (1), else "".

Return JSON: {{"items": [...]}}.

(1) Löw's list of abbreviations:
{abbrev_list}

(2) The page (vol. {vol}, p. {page}):
{page_text}
"""

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "abbr": {"type": "string"},
            "kind": {"type": "string", "enum": list(KINDS)},
            "expansion": {"type": "string"},
            "basis": {"type": "string", "enum": ["Löw list", "general knowledge", "unknown"]},
            "list_entry": {"type": "string"}},
        "required": ["abbr", "kind", "expansion", "basis", "list_entry"],
        "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False,
}


def plain(text: str) -> str:
    return re.sub(r"</?i>", "", text)


def page_text(vol: str, page: str) -> str:
    gold = DATA / "gold" / vol / f"{page}.txt"
    if gold.exists():
        return plain(gold.read_text(encoding="utf-8"))
    res = json.loads((DATA / "ocr" / SOURCE / vol / f"{page}.json").read_text(encoding="utf-8"))
    return plain("\n\n".join(f"{b.get('marker', '')} {b['text']}".strip() for b in res["blocks"]))


def abbrev_list() -> str:
    out = []
    for p in range(731, 741):
        f = DATA / "ocr" / SOURCE / "IV" / f"{p}.json"
        res = json.loads(f.read_text(encoding="utf-8"))
        out.append("\n".join(b["text"] for b in res["blocks"] if b["type"] != "furniture"))
    return plain("\n".join(out))


def ask(prompt: str) -> tuple[list[dict], float]:
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": "Bearer " + KEY_FILE.read_text(encoding="utf-8").strip()},
        json={"model": MODEL, "max_tokens": 32000,
              "messages": [{"role": "user", "content": prompt}],
              "response_format": {"type": "json_schema",
                                  "json_schema": {"name": "abbr", "strict": True, "schema": SCHEMA}},
              "reasoning": {"effort": "medium"}, "usage": {"include": True}},
        timeout=900)
    d = r.json()
    if not r.ok or "error" in d:
        raise RuntimeError(f"HTTP {r.status_code}: {d.get('error', d)}")
    ch = d["choices"][0]
    if ch.get("finish_reason") not in ("stop", "end_turn"):
        raise RuntimeError(f"finish_reason={ch.get('finish_reason')}")
    return json.loads(ch["message"]["content"])["items"], d.get("usage", {}).get("cost", 0)


def key(abbr: str) -> str:
    return re.sub(r"\s+", " ", abbr.strip())  # case matters: BB. (Bar Bahlul) != Bb. (Bava Batra)


def render(table: dict) -> str:
    lines = ["# Abbreviations and bibliography", "",
             "Generated file: do not edit; edit `abbreviations.json` and run `uv run abbrev.py --render`. "
             "Maintained by `abbrev.py` in `abbreviations.json` (rows with `\"checked\": true` are "
             "hand-edited and never overwritten). Basis: **Löw** = his list in Bd. IV pp. 731–740; "
             "**gk** = general knowledge, not in his list; **?** = not known, the expansion is a guess "
             "or empty. Pages: vol/page where the item occurs.", ""]
    for kind, title in KINDS.items():
        rows = sorted((r for r in table["items"].values() if r["kind"] == kind),
                      key=lambda r: key(r["abbr"]))
        if not rows:
            continue
        lines += [f"## {title}", "", "| Abbreviation | Expansion | Basis | Pages |", "|---|---|---|---|"]
        for r in rows:
            basis = {"Löw list": "Löw", "general knowledge": "gk", "unknown": "?"}[r["basis"]]
            basis += " ✓" if r.get("checked") else ""
            cells = [r["abbr"], r["expansion"] or "—", basis, ", ".join(r["pages"])]
            lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
        lines.append("")
    return "\n".join(lines)


def write_md(table: dict) -> None:
    OUT_MD.write_text(render(table), encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", help="only re-render ABBREVIATIONS.md")
    a = p.parse_args()
    table = json.loads(TABLE.read_text(encoding="utf-8")) if TABLE.exists() else {"pages_done": [], "items": {}}
    if not a.render:
        man = json.loads((DATA / "raw" / "manifest.json").read_text(encoding="utf-8"))["pages"]
        todo = [f"{pg['vol']}/{Path(pg['file']).stem}" for pg in man if pg["kind"] == "entry"]
        todo = [t for t in todo if t not in table["pages_done"]]
        lst, total = abbrev_list(), 0.0
        for i, pg in enumerate(todo, 1):
            vol, page = pg.split("/")
            items, cost = ask(PROMPT.format(abbrev_list=lst, vol=vol, page=page, page_text=page_text(vol, page)))
            total += cost
            new = 0
            for it in items:
                row = table["items"].get(key(it["abbr"]))
                if row is None:
                    row = table["items"][key(it["abbr"])] = {**it, "pages": [], "checked": False}
                    new += 1
                if pg not in row["pages"]:
                    row["pages"].append(pg)
            table["pages_done"].append(pg)
            TABLE.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[{i}/{len(todo)}] {pg}: {len(items)} items, {new} new, ${cost:.4f}", flush=True)
        print(f"{len(table['items'])} items in table; cost this run ${total:.4f}")
    write_md(table)
    print(f"wrote {OUT_MD.name}")


if __name__ == "__main__":
    main()
