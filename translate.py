"""Translate OCR'd pages into English, block by block.

  uv run translate.py I/193 I/194                       # these pages
  uv run translate.py --main                            # all main-text pages in the sample
  uv run translate.py --main --model google/gemini-3.1-pro-preview --effort low

Input: data/ocr/{--source}/{vol}/{page}.json. Output: data/translation/{name}/{vol}/{page}.json
and .md, one English block for each source block. Words in Hebrew, Aramaic, Syriac, Arabic,
Greek stay in their script; Syriac, Arabic, Persian and Greek get a transliteration in square
brackets, Hebrew script does not. Roman numerals become Arabic numerals.
When data/gold/{vol}/{page}.txt exists, the gold text is translated instead of the OCR output.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

DATA = Path(__file__).parent / "data"
KEY_FILE = Path.home() / "Desktop/Misc/key.txt"

PROMPT = """\
Below is one OCR'd page of Immanuel Löw, "Die Flora der Juden" (1924-34), a German scholarly \
work on the plants of Jewish literature, as JSON blocks in reading order. Translate it into \
English for scholars of rabbinics.

Rules:
- Return exactly one output block for each input block, in the same order, with the same \
"type" and "marker". Translate only the "text".
- Translate German and French into clear, accurate English. Keep the author's meaning and \
hedging (e.g. "wohl", "vielleicht", "?"). Do not add explanations.
- Keep unchanged: Latin plant names and Latin phrases, English text, bibliographic \
abbreviations and references (BB., Gal.-Üb., ZDPV. 27, 25, j Dem. II 22^{{b}}), numbers, \
footnote reference marks (*), **), †), ^{{1}}) and the author's own romanized forms \
(e.g. <i>buṭmā</i>, <i>ʿilk el-buṭm</i>) with their <i> tags.
- Words in Hebrew script (Hebrew, Aramaic, Samaritan, Yiddish, Judeo-Arabic in Hebrew letters): keep them exactly as given and do NOT transliterate them.
- Words in Syriac script: keep them exactly as given and do NOT transliterate them (a program \
adds Hebrew letters later).
- Words in Arabic, Persian and Greek script: keep them exactly as given, in their script, and \
add a transliteration in square brackets right after each word or phrase, e.g. "بطم [buṭm]", \
"τερέβινθος [terebinthos]". Use standard current academic transliteration: IJMES for Arabic \
and Persian; SBL Handbook of Style (2nd ed.) for Greek. If the OCR text has [?], keep [?] and do \
not transliterate it. If a reading looks wrong, still transliterate what is written.
- Abbreviations: at the FIRST occurrence on the page of each abbreviation in the list below, \
add " [=expansion]" right after it, e.g. "assyr. [=Assyrian]", "BB. [=Bar Bahlul, Lexicon]". \
Use the expansion from the list; for bibliography shorten it to author and short title. If the \
list says the expansion is unknown, write "[=?]". Later occurrences on the same page stay as \
they are. Abbreviations that are not in the list: leave them as they are.
Abbreviation list for this page:
{abbrevs}
- Roman numerals used as numbers become Arabic numerals: "p. XXXIX" -> "p. 39". A Roman volume, book or chapter number before a page or folio number becomes "number, page" as the author writes elsewhere: "Robinson I 346. III 221" -> "Robinson 1, 346. 3, 221", "Gal. VI 644" -> "Gal. 6, 644", "jKil. I 27^{{a}}" -> "jKil. 1, 27^{{a}}", "E. Wiedem. XLIX 19" -> "E. Wiedem. 49, 19". Keep Roman numerals that are part of a name or title (e.g. Pius XII).
- Keep <i> tags around italic words; you may move them to fit the English word order.
- Join the printed lines of a block into running text: remove line breaks and re-join words \
hyphenated at a line end. Keep _{{..}} and ^{{..}} markup.
- A block may start or end in the middle of a sentence (the text continues from the previous \
page or on the next); translate the fragment as a fragment.

Return JSON: {{"blocks": [{{"type": ..., "marker": ..., "text": ...}}]}}.

Input blocks:
{blocks}
"""

SCHEMA = {
    "type": "object",
    "properties": {"blocks": {"type": "array", "items": {
        "type": "object",
        "properties": {"type": {"type": "string"}, "marker": {"type": "string"},
                       "text": {"type": "string"}},
        "required": ["type", "marker", "text"], "additionalProperties": False}}},
    "required": ["blocks"], "additionalProperties": False,
}


SYRIAC_TO_HEBREW = dict(zip("ܐܒܓܕܗܘܙܚܛܝܟܠܡܢܣܥܦܨܩܪܫܬ", "אבגדהוזחטיכלמנסעפצקרשת"))
FINALS = dict(zip("כמנפצ", "ךםןףץ"))
SYRIAC_RUN = re.compile(  # Syriac letters plus combining marks (seyame is U+0308)
    r"[ܐ-ݏ][܀-ݏ̀-ͯ]*(?:[  ]+[ܐ-ݏ][܀-ݏ̀-ͯ]*)*")


def syriac_to_hebrew(run: str) -> str:
    """Letter-for-letter Syriac -> Hebrew square script; vowels and diacritics dropped."""
    words = []
    for w in run.split():
        h = "".join(SYRIAC_TO_HEBREW.get(c, "") for c in w)
        if len(h) > 1 and h[-1] in FINALS:
            h = h[:-1] + FINALS[h[-1]]
        words.append(h)
    return " ".join(words)


def add_hebrew_letters(text: str) -> str:
    return SYRIAC_RUN.sub(lambda m: f"{m.group(0)} [{syriac_to_hebrew(m.group(0))}]", text)


def abbrev_rows(page_key: str) -> str:
    table = DATA.parent / "abbreviations.json"
    if not table.exists():
        return "(none)"
    rows = [r for r in json.loads(table.read_text(encoding="utf-8"))["items"].values()
            if page_key in r["pages"]]
    return "\n".join(f"- {r['abbr']} = {r['expansion'] if r['basis'] != 'unknown' else '?'}"
                     for r in rows) or "(none)"


def translate(page: dict, model: str, effort: str, page_key: str) -> dict:
    src = [{"type": b["type"], "marker": b.get("marker", ""), "text": b["text"]} for b in page["blocks"]]
    prompt = PROMPT.format(blocks=json.dumps({"blocks": src}, ensure_ascii=False, indent=1),
                           abbrevs=abbrev_rows(page_key))
    t = time.monotonic()
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": "Bearer " + KEY_FILE.read_text(encoding="utf-8").strip()},
        json={"model": model, "max_tokens": 32000,
              "messages": [{"role": "user", "content": prompt}],
              "response_format": {"type": "json_schema",
                                  "json_schema": {"name": "page", "strict": True, "schema": SCHEMA}},
              "reasoning": {"effort": effort}, "usage": {"include": True}},
        timeout=900)
    d = r.json()
    if not r.ok or "error" in d:
        raise RuntimeError(f"HTTP {r.status_code}: {d.get('error', d)}")
    ch, u = d["choices"][0], d.get("usage", {})
    if ch.get("finish_reason") not in ("stop", "end_turn"):
        raise RuntimeError(f"finish_reason={ch.get('finish_reason')}, cost ${u.get('cost', 0):.4f}")
    text = ch["message"]["content"].strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    blocks = json.loads(text)["blocks"]
    if len(blocks) != len(src):
        raise RuntimeError(f"{len(blocks)} blocks back for {len(src)} sent")
    for b in blocks:
        b["text"] = add_hebrew_letters(b["text"])
    return {"blocks": blocks, "meta": {
        "model": d.get("model", model), "effort": effort, "source_meta": page["meta"],
        "input_tokens": u.get("prompt_tokens"), "output_tokens": u.get("completion_tokens"),
        "cost_usd": round(u.get("cost", 0), 4), "seconds": round(time.monotonic() - t, 1)}}


FOOTNOTE = re.compile(r"^((?:\*+|†+|\^\{\d+\})\))\s*")


def gold_page(path: Path, ocr: dict) -> dict:
    """Gold text -> blocks; block types come from the OCR page if the block count matches."""
    texts = [t.strip("\n") for t in path.read_text(encoding="utf-8").split("\n\n") if t.strip()]
    types = [b["type"] for b in ocr["blocks"]] if len(ocr["blocks"]) == len(texts) else None
    blocks = []
    for i, t in enumerate(texts):
        m = FOOTNOTE.match(t)
        typ = types[i] if types else ("footnote" if m else "body")
        marker = m.group(1) if m and typ == "footnote" else ""
        blocks.append({"type": typ, "marker": marker, "text": t[m.end():] if marker else t})
    return {"blocks": blocks, "meta": {"engine": "gold", "file": path.name}}


def md_inline(text: str) -> str:
    text = re.sub(r"\^\{(.+?)\}", r"<sup>\1</sup>", text)
    return re.sub(r"_\{(.+?)\}", r"<sub>\1</sub>", text)


def to_md(label: str, result: dict) -> str:
    out, notes = [f"<!-- {label}, {result['meta']['model']} -->"], []
    for b in result["blocks"]:
        text = md_inline(b["text"])
        if b["type"] == "footnote":
            notes.append(f"{b['marker']} {text}")
        elif b["type"] == "furniture":
            out.append(f"*[{text}]*")
        elif b["type"] == "heading":
            out.append(f"### {text}")
        else:
            out.append(text)
    if notes:
        out.append("---")
        out += notes
    return "\n\n".join(out) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("pages", nargs="*", help="vol/page, e.g. I/193")
    p.add_argument("--main", action="store_true", help="all main-text (entry) pages in the sample")
    p.add_argument("--source", default="or-claude-opus-5.5@low+ital", help="OCR folder in data/ocr/")
    p.add_argument("--model", default="anthropic/claude-opus-5.5")
    p.add_argument("--effort", default="medium")
    p.add_argument("--force", action="store_true")
    a = p.parse_args()

    pages = list(a.pages)
    if a.main:
        man = json.loads((DATA / "raw" / "manifest.json").read_text(encoding="utf-8"))["pages"]
        pages += [f"{pg['vol']}/{Path(pg['file']).stem}" for pg in man if pg["kind"] == "entry"]
    name = f"{a.model.split('/')[-1]}@{a.effort}"
    total = 0.0
    for i, pg in enumerate(pages, 1):
        vol, page = pg.split("/")
        out = DATA / "translation" / name / vol / page
        if out.with_suffix(".json").exists() and not a.force:
            print(f"[{i}/{len(pages)}] {pg}: done already", flush=True)
            continue
        src = json.loads((DATA / "ocr" / a.source / vol / f"{page}.json").read_text(encoding="utf-8"))
        gold = DATA / "gold" / vol / f"{page}.txt"
        if gold.exists():
            src = gold_page(gold, src)
        try:
            res = translate(src, a.model, a.effort, pg)
        except Exception as e:
            print(f"[{i}/{len(pages)}] {pg}: FAILED {type(e).__name__}: {e}", flush=True)
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        out.with_suffix(".md").write_text(to_md(f"{vol} p. {page}", res), encoding="utf-8")
        total += res["meta"]["cost_usd"]
        print(f"[{i}/{len(pages)}] {pg}: {res['meta']['seconds']} s, ${res['meta']['cost_usd']:.4f}", flush=True)
    print(f"cost this run ${total:.4f}")


if __name__ == "__main__":
    main()
