"""OCR the sample pages with two engines, for comparison.

  uv run ocr.py tesseract              # all pages in data/raw/manifest.json
  uv run ocr.py claude I/193 IV/595    # only these pages
  uv run ocr.py claude --force         # redo pages that already have output

Writes data/ocr/{engine}/{vol}/{page}.json and .md. Pages with output are skipped.
"""

import argparse
import base64
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

DATA = Path(__file__).parent / "data"
TESSERACT = os.environ.get(
    "TESSERACT", str(Path.home() / "AppData/Local/Programs/Tesseract-OCR/tesseract.exe"))
TESSDATA = Path(__file__).parent / "tessdata"
TESS_LANGS = "deu+heb+ara+syr"

MODEL = "claude-opus-5-5"
PRICE_IN, PRICE_OUT = 4.00, 20.00  # USD per MTok, claude-opus-5-5 (skill table, cached 06-Oct-2026)
MAX_EDGE, MAX_PIXELS = 2576, 3_750_000  # the API downscales images beyond either limit

BLOCK_TYPES = ["heading", "body", "footnote", "index_entry", "furniture"]
LANGS = ["deu", "lat", "fra", "eng", "ita", "grc", "heb", "arc", "syc", "ara", "fas", "translit", "other"]

PROMPT = """\
These images are one printed page of Immanuel Löw, "Die Flora der Juden" (1924-34): a German \
scholarly text with Hebrew, Aramaic, Syriac, Arabic and Greek words, and romanized \
transliterations. The page is split into {n} image(s), top to bottom, cut at blank space \
between lines. Transcribe the whole page as one page.

Transcription rules:
- Transcribe exactly what is printed. Never translate, normalize, modernize, correct or expand \
abbreviations. Keep the original spelling (ß, ä, old forms) and punctuation, including the \
dashes (—), tildes (~) and asterisks.
- Hebrew, Aramaic, Syriac, Arabic and Greek stay in their own script, in Unicode, in logical \
(reading) order. Keep vowel points and diacritics only where they are printed. Keep the \
diacritics of transliterations (ṭ, ḥ, ā, š, ʿ, ʾ ...).
- Keep each printed line as one line: separate lines with "\\n". Keep a hyphen at a line end \
as printed. Do not join lines.
- Subscripts: write "_{{14}}" for a subscript 14. Superscripts: write "^{{a}}". Write small \
capitals and letter-spaced words as plain text with normal capitalization \
(SACHAU in small caps -> "Sachau").
- Italics: wrap italic text in <i>...</i> (e.g. "<i>buṭm</i>, sont"). Open and close the tag \
inside one run; if an italic stretch continues into the next run, close it and open it again \
there. Punctuation after an italic word stays outside the tag unless it is clearly italic. \
Semitic scripts and Greek are never marked italic.
- Text you cannot read: write [?] for each unreadable stretch. Do not guess.

Blocks, in reading order:
- "furniture": running head, page number, printer's signature (e.g. "Löw, Flora. I.").
- "heading": a section or entry heading that stands on its own line(s).
- "body": a paragraph of main text. A new paragraph starts at an indented line.
- "index_entry": a paragraph on an index or abbreviation-list page (keep the whole printed \
paragraph in one block; do not split it into single entries).
- "footnote": one footnote. Put its printed mark ("*)", "**)", "†)", "1)") in "marker" and \
not in the runs. In the main text, keep the footnote reference marks where they are printed.
For other block types, "marker" is "".

Runs: split each block into runs of one language each, in reading order. Codes: deu German, \
lat Latin (incl. botanical names), fra French, eng English, ita Italian, grc Greek, heb Hebrew, \
arc Aramaic (incl. Jewish Babylonian/Palestinian, Targum, Samaritan), syc Syriac, ara Arabic, \
fas Persian, translit romanized Semitic words, other. Numbers, references and punctuation go \
with the run around them. Concatenating the runs of a block must give the block text exactly \
(spaces and "\\n" included). If Hebrew vs. Aramaic is unclear, use heb.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": BLOCK_TYPES},
                    "marker": {"type": "string"},
                    "runs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "lang": {"type": "string", "enum": LANGS},
                                "text": {"type": "string"},
                            },
                            "required": ["lang", "text"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["type", "marker", "runs"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["blocks"],
    "additionalProperties": False,
}


# ---------- image preparation (Claude) ----------

def _span(profile: np.ndarray, thr: float, gap: int) -> tuple[int, int]:
    """Largest run of indices where profile > thr, bridging gaps up to `gap`."""
    idx = np.flatnonzero(profile > thr)
    breaks = np.flatnonzero(np.diff(idx) > gap)
    starts = np.r_[idx[0], idx[breaks + 1]]
    ends = np.r_[idx[breaks], idx[-1]] + 1
    k = int(np.argmax(ends - starts))
    return int(starts[k]), int(ends[k])


def text_box(gray: Image.Image) -> tuple[int, int, int, int]:
    """Bounding box of the text block, without the scan borders around the page."""
    small = np.asarray(gray.reduce(4)) < 140
    h, w = small.shape
    # blank out border lines (rows/columns that are mostly ink), then find the text block
    small[small.mean(axis=1) > 0.25, :] = False
    small[:, small.mean(axis=0) > 0.25] = False
    x0, x1 = _span(small.mean(axis=0), 0.003, int(w * 0.015))
    rows = small[:, x0:x1].mean(axis=1)
    rows = np.where(rows > 0.4, 0, rows)
    ys = np.flatnonzero(rows > 0.002)
    pad = 6
    return (max(x0 - pad, 0) * 4, max(ys[0] - pad, 0) * 4,
            min(x1 + pad, w) * 4, min(ys[-1] + 1 + pad, h) * 4)


def page_images(path: Path) -> list[Image.Image]:
    """Crop to the text block; cut in two at a blank row if the page is tall."""
    gray = Image.open(path).convert("L")
    page = gray.crop(text_box(gray))
    w, h = page.size
    if h <= MAX_EDGE * 1.1 or h < 1.3 * w:
        return [page]
    ink = (np.asarray(page) < 140).mean(axis=1)
    lo, hi = int(h * 0.4), int(h * 0.6)
    cut = lo + int(np.argmin(np.convolve(ink[lo:hi], np.ones(15) / 15, "same")))
    return [page.crop((0, 0, w, cut)), page.crop((0, cut, w, h))]


def jpeg_b64(img: Image.Image) -> str:
    s = min(1, MAX_EDGE / max(img.size), (MAX_PIXELS / (img.width * img.height)) ** 0.5)
    if s < 1:  # resize here, so we control the filter
        img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return base64.standard_b64encode(buf.getvalue()).decode()


# ---------- engines ----------

def parse_blocks(text: str) -> list[dict]:
    """Model JSON -> blocks; block lang = the language with the most characters."""
    text = text.strip()
    if text.startswith("```"):  # models without schema enforcement may fence the JSON
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    blocks = []
    for b in json.loads(text)["blocks"]:
        chars = {}
        for r in b["runs"]:
            chars[r["lang"]] = chars.get(r["lang"], 0) + len(r["text"].strip())
        blocks.append({"type": b["type"], "lang": max(chars, key=chars.get) if chars else "other",
                       "text": "".join(r["text"] for r in b["runs"]),
                       "marker": b.get("marker", ""), "runs": b["runs"]})
    return blocks


def run_openrouter(path: Path) -> dict:
    import requests

    key = Path(os.environ.get("OPENROUTER_KEY_FILE", Path.home() / "Desktop/Misc/key.txt"))
    imgs = page_images(path)
    content = [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{jpeg_b64(im)}"}}
               for im in imgs]
    content.append({"type": "text", "text": PROMPT.format(n=len(imgs))
                    + "\nAnswer with the JSON object only."})
    t = time.monotonic()
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": "Bearer " + key.read_text(encoding="utf-8").strip()},
        json={"model": ARGS.model, "max_tokens": 32000,
              "messages": [{"role": "user", "content": content}],
              "response_format": {"type": "json_schema",
                                  "json_schema": {"name": "page", "strict": True, "schema": SCHEMA}},
              "reasoning": {"effort": ARGS.effort},
              "usage": {"include": True}},
        timeout=900)
    d = r.json()
    raw = DATA / "ocr" / "_raw" / f"{ARGS.model.split('/')[-1]}_{path.parent.name}_{path.stem}.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    if not r.ok or "error" in d:
        raise RuntimeError(f"HTTP {r.status_code}: {d.get('error', d)}")
    ch = d["choices"][0]
    u = d.get("usage", {})
    if ch.get("finish_reason") not in ("stop", "end_turn"):
        raise RuntimeError(f"finish_reason={ch.get('finish_reason')}, cost ${u.get('cost', 0):.4f}")
    return {"blocks": parse_blocks(ch["message"]["content"]), "meta": {
        "engine": "openrouter", "model": d.get("model", ARGS.model), "provider": d.get("provider"),
        "effort": ARGS.effort, "reasoning_tokens":
            (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        "images": [list(im.size) for im in imgs],
        "input_tokens": u.get("prompt_tokens"), "output_tokens": u.get("completion_tokens"),
        "cost_usd": round(u.get("cost", 0), 4), "seconds": round(time.monotonic() - t, 1)}}


def run_claude(path: Path) -> dict:
    import anthropic

    imgs = page_images(path)
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                            "data": jpeg_b64(im)}} for im in imgs]
    content.append({"type": "text", "text": PROMPT.format(n=len(imgs))})
    client = anthropic.Anthropic()
    t = time.monotonic()
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=64000,
        betas=["server-side-fallback-2026-07-01"],
        extra_body={"fallbacks": "default"},
        output_config={"effort": ARGS.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": content}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason != "end_turn":
        raise RuntimeError(f"stop_reason={msg.stop_reason} {getattr(msg, 'stop_details', '')}")
    text = next(b.text for b in msg.content if b.type == "text")
    u = msg.usage
    cost = (u.input_tokens * PRICE_IN + u.output_tokens * PRICE_OUT) / 1e6
    return {"blocks": parse_blocks(text), "meta": {
        "engine": "claude", "model": msg.model, "effort": ARGS.effort,
        "images": [list(im.size) for im in imgs],
        "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
        "cost_usd": round(cost, 4), "seconds": round(time.monotonic() - t, 1)}}


def run_tesseract(path: Path) -> dict:
    t = time.monotonic()
    tsv = subprocess.run(
        [TESSERACT, str(path), "stdout", "-l", TESS_LANGS, "--psm", "3",
         "--tessdata-dir", str(TESSDATA), "-c", "tessedit_create_tsv=1"],
        capture_output=True, check=True).stdout.decode("utf-8")
    # level 5 = word; group words into lines, lines into Tesseract paragraphs
    paras: dict[tuple, dict[tuple, list[str]]] = {}
    for row in tsv.splitlines()[1:]:
        f = row.split("\t")
        if len(f) < 12 or f[0] != "5" or not f[11].strip():
            continue
        par = (int(f[2]), int(f[3]))
        line = par + (int(f[4]),)
        paras.setdefault(par, {}).setdefault(line, []).append(f[11])
    blocks = [{"type": "body", "lang": TESS_LANGS,
               "text": "\n".join(" ".join(ws) for ws in lines.values())}
              for lines in paras.values()]
    return {"blocks": blocks, "meta": {
        "engine": "tesseract", "langs": TESS_LANGS, "psm": 3, "cost_usd": 0,
        "seconds": round(time.monotonic() - t, 1)}}


KRAKEN = Path(__file__).parent / ".venv-kraken" / "Scripts" / "kraken.exe"


def run_kraken(path: Path) -> dict:
    """Kraken (separate venv, see README): default baseline segmenter + the model in --model."""
    t = time.monotonic()
    out = DATA / "cache" / "kraken" / f"{Path(ARGS.model).stem}_{path.parent.name}_{path.stem}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(KRAKEN), "-i", str(path), str(out), "segment", "-bl", "ocr", "-m", ARGS.model],
                   capture_output=True, check=True, env={**os.environ, "PYTHONUTF8": "1"})
    text = out.read_text(encoding="utf-8").strip()
    return {"blocks": [{"type": "body", "lang": "other", "text": text}], "meta": {
        "engine": "kraken", "model": Path(ARGS.model).name, "cost_usd": 0,
        "seconds": round(time.monotonic() - t, 1)}}


ENGINES = {"claude": run_claude, "tesseract": run_tesseract, "openrouter": run_openrouter,
           "kraken": run_kraken}


def to_md(page: dict, result: dict) -> str:
    out = [f"<!-- {page['vol']} p. {page['label']}, scan {page['scan_index']}, "
           f"{result['meta'].get('model', result['meta']['engine'])} -->"]
    lrm = "‎"  # left-to-right mark: keeps a line that starts with Hebrew LTR on GitHub
    for b in result["blocks"]:
        text = lrm + b["text"].replace("\n", f"  \n{lrm}")  # keep printed line breaks
        if b["type"] == "heading":
            out.append(f"### {text}")
        elif b["type"] == "footnote":
            out.append(f"> {lrm}{b.get('marker', '')} {text}".replace("  \n", "  \n> "))
        elif b["type"] == "furniture":
            out.append(f"{lrm}*{text}*")
        else:
            out.append(text)
    return "\n\n".join(out) + "\n"


def main():
    global ARGS
    p = argparse.ArgumentParser()
    p.add_argument("engine", choices=ENGINES)
    p.add_argument("pages", nargs="*", help="vol/page, e.g. I/193 (default: all in manifest)")
    p.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--model", help="openrouter model id, e.g. google/gemini-3.1-pro-preview")
    p.add_argument("--tag", default="", help="suffix for the output folder, e.g. a prompt version")
    p.add_argument("--force", action="store_true")
    ARGS = p.parse_args()
    # output folder per engine; one folder per OpenRouter model
    name = {"openrouter": lambda: f"or-{ARGS.model.split('/')[-1]}@{ARGS.effort}",
            "kraken": lambda: f"kraken-{Path(ARGS.model).stem}"}.get(ARGS.engine, lambda: ARGS.engine)()
    name += f"+{ARGS.tag}" if ARGS.tag else ""

    pages = json.loads((DATA / "raw" / "manifest.json").read_text(encoding="utf-8"))["pages"]
    if ARGS.pages:
        pages = [pg for pg in pages if f"{pg['vol']}/{Path(pg['file']).stem}" in ARGS.pages]
    total, done = 0.0, 0
    for i, pg in enumerate(pages, 1):
        out = DATA / "ocr" / name / pg["vol"] / Path(pg["file"]).stem
        if out.with_suffix(".json").exists() and not ARGS.force:
            print(f"[{i}/{len(pages)}] {pg['file']}: done already", flush=True)
            continue
        try:
            res = ENGINES[ARGS.engine](DATA / pg["file"])
        except Exception as e:  # report and go on with the next page
            print(f"[{i}/{len(pages)}] {pg['file']}: FAILED {type(e).__name__}: {e}", flush=True)
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        out.with_suffix(".md").write_text(to_md(pg, res), encoding="utf-8")
        total += res["meta"]["cost_usd"]
        done += 1
        print(f"[{i}/{len(pages)}] {pg['file']}: {len(res['blocks'])} blocks, "
              f"{res['meta']['seconds']} s, ${res['meta']['cost_usd']:.4f}", flush=True)
    print(f"{done} pages OCR'd this run, cost ${total:.4f}")


if __name__ == "__main__":
    main()
