"""Join the pages of one entry into continuous text and translate it as a whole.

  uv run entry.py pistacia                 # build data/entries/pistacia/ (German + English)
  uv run entry.py pistacia --no-translate  # only the joined German text

Per page the source is the gold text if it exists, else the OCR (translate.py's default).
Running heads and page numbers are dropped. A paragraph that runs over a page break is joined,
and "[p. N]" marks where page N begins. Footnotes stay grouped by page and are listed after the
text. The text is translated in chunks of whole paragraphs with translate.translate().
"""

import argparse
import json
import re
import sys
from pathlib import Path

import translate as T

sys.stdout.reconfigure(encoding="utf-8")

DATA = Path(__file__).parent / "data"
SOURCE = "or-claude-opus-5.5@low+ital"
CHUNK_CHARS = 6000

# start / end: regexes for the first block of the entry and the first block after it
ENTRIES = {
    "pistacia": {"vol": "I", "pages": list(range(191, 201)), "title": "Pistacia (Bd. I pp. 191–200)",
                 "start": r"^b\)\s*Pistacia", "end": r"^4\.\s*Rhus",
                 # checked by eye: p. 196 ends "(3.—4. Jh.)" mid-sentence
                 "continue": [197]},
}
# A paragraph continues on the next page if the page ends without sentence-final punctuation;
# "continue" / "break" in an entry override this for the pages listed (the first page of the pair).
SENTENCE_END = re.compile(r"[.!?:;)\]]\s*$")


def page_blocks(vol: str, page: int) -> list[dict]:
    ocr = json.loads((DATA / "ocr" / SOURCE / vol / f"{page}.json").read_text(encoding="utf-8"))
    gold = DATA / "gold" / vol / f"{page}.txt"
    return (T.gold_page(gold, ocr) if gold.exists() else ocr)["blocks"]


def build(cfg: dict) -> tuple[list[dict], list[dict]]:
    """-> (main blocks, footnote blocks); each block has a "page"."""
    main, notes, started, ended = [], [], False, False
    for page in cfg["pages"]:
        first_on_page = True
        for b in page_blocks(cfg["vol"], page):
            text = b["text"].strip()
            if b["type"] == "furniture":
                continue
            if b["type"] == "footnote":
                if started and not ended:
                    notes.append({"type": "footnote", "marker": b.get("marker", ""), "text": text, "page": page})
                continue
            if not started:
                if not re.search(cfg["start"], text):
                    continue
                started = True
            elif re.search(cfg["end"], text):
                ended = True
            if ended:
                continue
            prev = main[-1] if main else None
            continues = (page in cfg.get("continue", []) or not SENTENCE_END.search(prev["text"] if prev else "")) \
                and page not in cfg.get("break", [])
            if first_on_page and prev and prev["type"] == "body" and b["type"] == "body" and continues:
                if prev["text"].endswith("-"):  # word broken over the page: marker after the word
                    word, _, rest = text.partition(" ")
                    prev["text"] = f"{prev['text'][:-1]}{word} [p. {page}] {rest}"
                else:
                    prev["text"] += f" [p. {page}] {text}"
            else:
                marker = f"[p. {page}] " if first_on_page and main else ""
                main.append({"type": b["type"], "marker": "", "text": marker + text, "page": page})
            first_on_page = False
        if ended:
            break
    if not started:
        sys.exit(f"start pattern {cfg['start']!r} not found")
    return main, notes


def chunks(blocks: list[dict]) -> list[list[dict]]:
    out, cur = [], []
    for b in blocks:
        if cur and sum(len(x["text"]) for x in cur) + len(b["text"]) > CHUNK_CHARS:
            out.append(cur)
            cur = []
        cur.append(b)
    return out + [cur] if cur else out


def render(title: str, main: list[dict], notes: list[dict]) -> str:
    out = [f"# {title}", ""]
    for b in main:
        text = T.LRM + T.md_inline(b["text"])  # LRM: see translate.LRM
        out += [f"### {text}" if b["type"] == "heading" else text, ""]
    if notes:
        out += ["---", "", "**Notes**", ""]
        for page in sorted({n["page"] for n in notes}):
            out += [f"*p. {page}*", ""]
            out += [T.LRM + f"{n['marker']} {T.md_inline(n['text'])}".strip() + "  "
                    for n in notes if n["page"] == page]
            out.append("")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("entry", choices=ENTRIES)
    p.add_argument("--model", default="anthropic/claude-opus-5.5")
    p.add_argument("--effort", default="medium")
    p.add_argument("--no-translate", action="store_true")
    a = p.parse_args()
    cfg = ENTRIES[a.entry]
    out = DATA / "entries" / a.entry
    out.mkdir(parents=True, exist_ok=True)

    main_blocks, notes = build(cfg)
    (out / "de.json").write_text(json.dumps({"main": main_blocks, "notes": notes}, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
    (out / "de.md").write_text(render(cfg["title"], main_blocks, notes), encoding="utf-8")
    print(f"{len(main_blocks)} paragraphs, {len(notes)} footnotes, "
          f"{sum(len(b['text']) for b in main_blocks)} characters of main text")
    if a.no_translate:
        return

    keys = [f"{cfg['vol']}/{pg}" for pg in cfg["pages"]]
    en_main, en_notes, cost = [], [], 0.0
    for kind, blocks, target in (("text", main_blocks, en_main), ("notes", notes, en_notes)):
        for i, ch in enumerate(chunks(blocks), 1):
            res = T.translate({"blocks": ch, "meta": {"entry": a.entry, "part": kind}}, a.model, a.effort, keys)
            for src, b in zip(ch, res["blocks"]):
                target.append({**b, "page": src["page"]})
            cost += res["meta"]["cost_usd"]
            print(f"{kind} chunk {i}: {len(ch)} blocks, {res['meta']['seconds']} s, "
                  f"${res['meta']['cost_usd']:.4f}", flush=True)
    meta = {"model": a.model, "effort": a.effort, "rules": T.RULES_VERSION, "cost_usd": round(cost, 4)}
    (out / "en.json").write_text(json.dumps({"main": en_main, "notes": en_notes, "meta": meta},
                                            ensure_ascii=False, indent=1), encoding="utf-8")
    title = cfg["title"].replace("Bd.", "vol.")
    (out / "en.md").write_text(render(title, en_main, en_notes), encoding="utf-8")
    print(f"translation cost ${cost:.4f}; wrote {out / 'en.md'}")


if __name__ == "__main__":
    main()
