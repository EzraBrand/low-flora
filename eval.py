"""Character error rate (CER) of each OCR engine against hand-corrected gold pages.

  uv run eval.py                                   # table for all gold pages, all engines
  uv run eval.py draft I/193 --from "or-claude-opus-5.5@low"   # start a gold page from one engine's output

Gold format: data/gold/{vol}/{page}.txt, UTF-8 plain text, one block per paragraph, blocks
separated by a blank line, printed line breaks kept, a footnote starts with its mark ("*) ...").
Same conventions as the OCR prompt in ocr.py: subscripts _{14}, superscripts ^{a}, [?] unreadable,
italics as <i>...</i>.

CER = edit distance / gold length, after normalizing: Unicode NFC, bidi control marks and <i> tags removed,
all whitespace runs (spaces and line breaks) collapsed to one space. Per script, each gold
character's errors count for that character's script; an inserted character counts for the
script of the gold character next to it.
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

from rapidfuzz.distance import Levenshtein

sys.stdout.reconfigure(encoding="utf-8")

DATA = Path(__file__).parent / "data"
SCRIPTS = [  # (name, ranges); first match wins; anything else is "common"
    ("Latin", [(0x41, 0x5A), (0x61, 0x7A), (0xC0, 0x24F), (0x1E00, 0x1EFF), (0x2C0, 0x36F)]),
    ("Hebrew", [(0x590, 0x5FF), (0xFB1D, 0xFB4F)]),
    ("Arabic", [(0x600, 0x6FF), (0x750, 0x77F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)]),
    ("Syriac", [(0x700, 0x74F), (0x860, 0x86F)]),
    ("Greek", [(0x370, 0x3FF), (0x1F00, 0x1FFF)]),
]
BIDI = re.compile("[‎‏‪-‮⁦-⁩﻿]")
ITALIC = re.compile(r"</?i>")


def script(ch: str) -> str:
    o = ord(ch)
    for name, ranges in SCRIPTS:
        if any(a <= o <= b for a, b in ranges):
            return name
    return "common"


def norm(text: str) -> str:
    text = ITALIC.sub("", BIDI.sub("", unicodedata.normalize("NFC", text)))
    return re.sub(r"\s+", " ", text).strip()


def page_text(result: dict) -> str:
    """OCR json -> the same plain-text layout as a gold file."""
    out = []
    for b in result["blocks"]:
        marker = b.get("marker") or ""
        out.append(f"{marker} {b['text']}".strip() if marker else b["text"])
    return "\n\n".join(out)


def cer(gold: str, hyp: str) -> dict[str, list[int]]:
    """{script: [errors, gold chars]} plus 'all'."""
    gold, hyp = norm(gold), norm(hyp)
    stats = {}
    for ch in gold:
        stats.setdefault(script(ch), [0, 0])[1] += 1
    for op in Levenshtein.editops(gold, hyp):
        pos = min(op.src_pos, len(gold) - 1)  # insertions: the gold char at that position
        stats.setdefault(script(gold[pos]), [0, 0])[0] += 1
    stats["all"] = [sum(v[0] for v in stats.values()), len(gold)]
    return stats


def cmd_table(_):
    golds = sorted(g for g in (DATA / "gold").glob("*/*.txt") if not g.name.endswith(".draft.txt"))
    if not golds:
        sys.exit("no gold pages in data/gold/ yet (see: uv run eval.py draft --help)")
    engines = sorted(p.name for p in (DATA / "ocr").iterdir() if not p.name.startswith("_"))
    cols = ["all", "Latin", "Hebrew", "Arabic", "Syriac", "Greek", "common"]
    print(f"{len(golds)} gold page(s): " + ", ".join(f"{g.parent.name}/{g.stem}" for g in golds))
    print(f"{'engine':32s}" + "".join(f"{c:>9s}" for c in cols) + "   pages")
    for eng in engines:
        tot, n = {}, 0
        for g in golds:
            f = DATA / "ocr" / eng / g.parent.name / f"{g.stem}.json"
            if not f.exists():
                continue
            n += 1
            res = json.loads(f.read_text(encoding="utf-8"))
            for k, (e, c) in cer(g.read_text(encoding="utf-8"), page_text(res)).items():
                t = tot.setdefault(k, [0, 0])
                t[0] += e
                t[1] += c
        if n:
            cells = [f"{tot[c][0] / tot[c][1]:9.1%}" if tot.get(c, [0, 0])[1] else f"{'-':>9s}" for c in cols]
            print(f"{eng:32s}" + "".join(cells) + f"   {n}/{len(golds)}")
    chars = {}
    for g in golds:
        for k, (_, c) in cer(g.read_text(encoding="utf-8"), "").items():
            chars[k] = chars.get(k, 0) + c
    print(f"{'(gold chars)':32s}" + "".join(f"{chars.get(c, 0):9d}" for c in cols))


def cmd_draft(a):
    vol, page = a.page.split("/")
    src = DATA / "ocr" / a.source / vol / f"{page}.json"
    out = DATA / "gold" / vol / f"{page}.draft.txt"
    if out.exists() or out.with_name(f"{page}.txt").exists():
        sys.exit(f"a draft or gold file for {a.page} exists; not overwriting it")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page_text(json.loads(src.read_text(encoding="utf-8"))) + "\n", encoding="utf-8")
    print(f"wrote {out} from {a.source}; correct it against data/raw/{vol}/{page}.jpg, "
          f"then rename it to {page}.txt (only *.txt without .draft counts as gold)")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers()
    s = sub.add_parser("draft", help="copy one engine's output to data/gold/ for hand correction")
    s.add_argument("page", help="vol/page, e.g. I/193")
    s.add_argument("--from", dest="source", required=True, help="engine folder in data/ocr/")
    s.set_defaults(func=cmd_draft)
    p.set_defaults(func=cmd_table)
    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
