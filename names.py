"""Common English names for the Latin plant names in the translated contents lists.

  uv run names.py                 # all contents lists not yet in plant_names.json
  uv run names.py toc-II --force  # redo one list

Writes plant_names.json: {entry: [{"line", "latin", "english", "modern", "sure"}]}, where "line"
is the 0-based line number in the English contents list (data/entries/{entry}/en.json, lines of
all main blocks in order) and "latin" is the exact text in that line to annotate. The reading
edition (build_site.py) shows it as "Latin [=english]". Edit the file by hand to correct a name;
a row with "checked": true is never overwritten.
"""

import argparse
import json
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent
DATA = ROOT / "data"
TABLE = ROOT / "plant_names.json"
KEY_FILE = Path.home() / "Desktop/Misc/key.txt"
MODEL = "anthropic/claude-opus-5.5"
ENTRIES = ["toc-I-1", "toc-I-2", "toc-II", "toc-III", "toc-IV"]

PROMPT = """\
Below are the numbered lines of a table of contents from Immanuel Löw, "Die Flora der Juden" \
(1924-34), already translated into English. Most lines begin with a Latin plant name: a family \
(e.g. Anacardiaceae), a genus (Pistacia), or a species (Pistacia Terebinthus L.; "P. Lentiscus" \
abbreviates the genus of the nearest genus line above). Some lines have a prefix ("Appendix:", \
"Arab." = Arabic) or are not plant names at all ("Arabic names", "Preface", chapter titles).

For every line that contains a Latin plant name, give:
- "line": the line number.
- "latin": the Latin name exactly as it appears in the line (without the prefix, the author \
abbreviation such as "L." only if it is part of what you copy, and without the page number).
- "english": the common English name as used today, short (e.g. "cashew family", "pistachio", \
"terebinth", "mastic tree"). For a family, use "... family". If there is no common English name, \
give a short plain description (e.g. "a horsetail genus") rather than inventing a name.
- "modern": the current accepted scientific name if Löw's name is outdated or a synonym \
(e.g. Ampelidaceae -> "Vitaceae"), else "".
- "sure": false if the identification of Löw's name is uncertain, else true.
Lines without a Latin plant name: leave them out.

Return JSON: {{"names": [...]}}.

Lines:
{lines}
"""

SCHEMA = {"type": "object", "properties": {"names": {"type": "array", "items": {
    "type": "object",
    "properties": {"line": {"type": "integer"}, "latin": {"type": "string"}, "english": {"type": "string"},
                   "modern": {"type": "string"}, "sure": {"type": "boolean"}},
    "required": ["line", "latin", "english", "modern", "sure"], "additionalProperties": False}}},
    "required": ["names"], "additionalProperties": False}


def lines_of(entry: str) -> list[str]:
    d = json.loads((DATA / "entries" / entry / "en.json").read_text(encoding="utf-8"))
    return [line for b in d["main"] for line in b["text"].split("\n")]


def ask(lines: list[str]) -> tuple[list[dict], float]:
    numbered = "\n".join(f"{i}: {line}" for i, line in enumerate(lines))
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": "Bearer " + KEY_FILE.read_text(encoding="utf-8").strip()},
        json={"model": MODEL, "max_tokens": 32000,
              "messages": [{"role": "user", "content": PROMPT.format(lines=numbered)}],
              "response_format": {"type": "json_schema",
                                  "json_schema": {"name": "names", "strict": True, "schema": SCHEMA}},
              "reasoning": {"effort": "medium"}, "usage": {"include": True}},
        timeout=900)
    d = r.json()
    if not r.ok or "error" in d:
        raise RuntimeError(f"HTTP {r.status_code}: {d.get('error', d)}")
    ch = d["choices"][0]
    if ch.get("finish_reason") not in ("stop", "end_turn"):
        raise RuntimeError(f"finish_reason={ch.get('finish_reason')}")
    return json.loads(ch["message"]["content"])["names"], d.get("usage", {}).get("cost", 0)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("entries", nargs="*", default=ENTRIES)
    p.add_argument("--force", action="store_true")
    a = p.parse_args()
    table = json.loads(TABLE.read_text(encoding="utf-8")) if TABLE.exists() else {}
    total = 0.0
    for e in a.entries:
        if e in table and not a.force:
            print(f"{e}: done already")
            continue
        lines = lines_of(e)
        names, cost = ask(lines)
        checked = {(r["line"], r["latin"]): r for r in table.get(e, []) if r.get("checked")}
        rows, bad = [], 0
        for n in names:
            if not (0 <= n["line"] < len(lines)) or n["latin"] not in lines[n["line"]]:
                bad += 1  # the name must be found in its line, or the site cannot place it
                continue
            rows.append(checked.get((n["line"], n["latin"]), n))
        table[e] = sorted(rows, key=lambda r: r["line"])
        TABLE.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
        total += cost
        print(f"{e}: {len(rows)} names, {bad} rejected (not found in their line), "
              f"{sum(not r['sure'] for r in rows)} uncertain, ${cost:.4f}", flush=True)
    print(f"cost ${total:.4f}")


if __name__ == "__main__":
    main()
