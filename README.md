# low-flora

Test pipeline for OCR of Immanuel Löw, *Die Flora der Juden* (Vienna/Leipzig 1924–34).
Proof of concept on 9 pages: fetch page images, OCR them with several engines, score them
against hand-corrected pages, and translate them into English.

## Read the results

**Reading edition (web):** https://ezrabrand.github.io/low-flora/ — German and English side by
side, scans linked from each page mark, abbreviations and transliterations as tooltips (with
switches to show them inline), numbered footnotes, and a searchable abbreviation table. Built by
`build_site.py` into `docs/` (GitHub Pages serves `main:/docs`); run `uv run build_site.py` after new
translations.

**A whole entry:** [Pistacia, Bd. I pp. 191–200, in English](data/entries/pistacia/en.md)
(and the [joined German text](data/entries/pistacia/de.md)): ten pages joined into continuous
text, with page markers, footnotes by page, and abbreviations opened.

The current outputs for the main-text pages: the scan (Frankfurt viewer), the transcription
(Claude Opus 5.5, with italics), and the English translation (rules v3, see
[Translation](#translation)). **Start with Bd. I p. 194**: its transcription was checked by hand
(the gold page), and the translation was made from that checked text.

| Page | Contents | Scan | Transcription | English |
|---|---|---|---|---|
| **I 194** | Pistacia: Syriac, Arabic, Greek, footnotes | [scan](https://sammlungen.ub.uni-frankfurt.de/freimann/content/pageview/104480) | [checked (gold)](data/gold/I/194.txt), [notes](data/gold/I/194.notes.md) | [English](data/translation/claude-opus-5.5%40medium-v3/I/194.md) |
| I 193 | Pistacia Terebinthus | [scan](https://sammlungen.ub.uni-frankfurt.de/freimann/content/pageview/104479) | [OCR](data/ocr/or-claude-opus-5.5%40low%2Bital/I/193.md) | [English](data/translation/claude-opus-5.5%40medium-v3/I/193.md) |
| I 195 | Pistacia Lentiscus (mastic) | [scan](https://sammlungen.ub.uni-frankfurt.de/freimann/content/pageview/104481) | [OCR](data/ocr/or-claude-opus-5.5%40low%2Bital/I/195.md) | [English](data/translation/claude-opus-5.5%40medium-v3/I/195.md) |
| I 196 | Pistacia Lentiscus | [scan](https://sammlungen.ub.uni-frankfurt.de/freimann/content/pageview/104482) | [OCR](data/ocr/or-claude-opus-5.5%40low%2Bital/I/196.md) | [English](data/translation/claude-opus-5.5%40medium-v3/I/196.md) |
| I 197 | Pistacia Lentiscus | [scan](https://sammlungen.ub.uni-frankfurt.de/freimann/content/pageview/104483) | [OCR](data/ocr/or-claude-opus-5.5%40low%2Bital/I/197.md) | [English](data/translation/claude-opus-5.5%40medium-v3/I/197.md) |
| II 289 | Olea: Hebrew verbs | [scan](https://sammlungen.ub.uni-frankfurt.de/freimann/content/pageview/103479) | [OCR](data/ocr/or-claude-opus-5.5%40low%2Bital/II/289.md) | [English](data/translation/claude-opus-5.5%40medium-v3/II/289.md) |
| III 287 | Citrus: the *etrog* in rabbinic sources | [scan](https://sammlungen.ub.uni-frankfurt.de/freimann/content/pageview/104026) | [OCR](data/ocr/or-claude-opus-5.5%40low%2Bital/III/287.md) | [English](data/translation/claude-opus-5.5%40medium-v3/III/287.md) |

Also: [abbreviations and bibliography](ABBREVIATIONS.md) (from Löw's own list),
[other possible targets](TARGETS.md), and the outputs of all engines in [data/ocr](data/ocr).
The folder `claude-opus-5.5@medium-v1` holds the first translation (older rules: every non-Latin
word transliterated, no abbreviation expansion); it is kept only for comparison.

## Source

Frankfurt UB, Freimann-Sammlung, Public Domain Mark 1.0.
Record: http://nbn-resolving.de/urn:nbn:de:hebis:30-180014581006

| Vol. | Record id | Scans | Contents |
|---|---|---|---|
| I (1,1 + 1,2, one scan) | 104263 | 828 | Kryptogamae, Acanthaceae – Composaceae |
| II | 103171 | 550 | Iridaceae – Papilionaceae |
| III | 103724 | 536 | Pedaliaceae – Zygophyllaceae |
| IV | 105456 | 756 | Zusammenfassung, Nachträge, Indizes, Abkürzungen |

- IIIF Presentation 2.0 manifest: `https://sammlungen.ub.uni-frankfurt.de/i3f/v20/{record id}/manifest`
- IIIF Image API 2 (level 2): `.../i3f/v20/{image id}/full/full/0/default.jpg` gives the native scan,
  grayscale JPG, about 3850×5750 (Bd. I) or 4190×5560 (Bd. IV), about 2 MB per page.
- The resolver and HTML pages are behind Anubis bot protection. The IIIF endpoints are not.
- Canvas labels are printed page numbers. A label in brackets (`[608]`) is an unnumbered page,
  and the number is the scan index, not a page number.

## Setup

- Python 3.13 with uv: `uv sync`
- Tesseract 5.4 (`winget install --id UB-Mannheim.TesseractOCR -e`; it installs per user in
  `%LOCALAPPDATA%\Programs\Tesseract-OCR`, set `TESSERACT` if it is elsewhere).
  Language data (tessdata_best `deu heb ara syr osd`) goes in `tessdata\` in this repo.
- OpenRouter key: a text file, default `%USERPROFILE%\Desktop\Misc\key.txt` (set `OPENROUTER_KEY_FILE`).
- Direct Anthropic API (engine `claude`): `ANTHROPIC_API_KEY`. Not tested.
- Kraken (optional baseline), in its own venv:
  `uv venv .venv-kraken --python 3.12`, `uv pip install --python .venv-kraken\Scripts\python.exe kraken`,
  then `set PYTHONUTF8=1` and `.venv-kraken\Scripts\kraken.exe get 10.5281/zenodo.21788410`.

## Run

```
uv run fetch.py list IV --from 600 --to 620            # scan index, label, image id
uv run fetch.py preview I 213 214                      # 1000 px previews to pick pages
uv run fetch.py sample                                 # full-res sample + data/raw/manifest.json

uv run ocr.py tesseract                                # all sample pages
uv run ocr.py openrouter --model anthropic/claude-opus-5.5 --effort low
uv run ocr.py openrouter I/194 --model google/gemini-3.1-pro-preview --effort low
uv run ocr.py claude --effort medium                   # Anthropic API directly
uv run ocr.py kraken I/194 --model "%LOCALAPPDATA%\htrmopo\htrmopo\<id>\medium.safetensors"

uv run ocr.py openrouter I/193 --model anthropic/claude-opus-5.5 --effort low --tag ital

uv run eval.py draft I/194 --from "or-claude-opus-5.5@low"   # start a gold page
uv run eval.py                                         # CER table

uv run translate.py --main                             # English, all main-text pages
uv run entry.py pistacia                               # one whole entry, pages joined, in English
uv run translate.py I/194 --model google/gemini-3.1-pro-preview --effort low
```

`ocr.py` skips pages that have output (`--force` redoes them). Output:
`data/ocr/{engine}/{vol}/{page}.json` and `.md`; OpenRouter engines are named
`or-{model}@{effort}`, plus `+{tag}` when `--tag` is given (`+ital` = prompt with italics).
Raw OpenRouter responses are kept in `data/ocr/_raw/`.

### Output format

`{"blocks": [{"type", "lang", "text", "marker", "runs": [{"lang", "text"}]}], "meta": {...}}`

- `type`: `heading`, `body`, `footnote`, `index_entry`, `furniture` (running head, page number,
  printer's signature; added so that they do not count as body text).
- `runs`: one language per run (`deu lat fra eng ita grc heb arc syc ara fas translit other`);
  the block `lang` is the language with the most characters.
- `marker`: the footnote mark (`*)`, `**)`, `†)`), only on footnotes.
- Transcription rules (same for gold pages): printed line breaks kept, end-of-line hyphens kept,
  subscripts `_{14}`, superscripts `^{a}`, italics as `<i>…</i>` (since 31-Oct-2026; runs
  without `+ital` have no italics), small caps and letter-spacing as plain text,
  `[?]` for unreadable text, Semitic scripts and Greek in Unicode, logical order.

### Gold pages

`data/gold/{vol}/{page}.txt`, blocks separated by a blank line, a footnote starts with its mark.
`eval.py draft` writes `{page}.draft.txt`; correct it against `data/raw/{vol}/{page}.jpg` and
rename it to `{page}.txt`. Only `*.txt` without `.draft` is scored.

- **Bd. I p. 194 is gold** (31-Oct-2026): the Opus @low draft, read and approved by me, with
  italic tags added from the `+ital` run. Its Syriac words are not verified; see
  `data/gold/I/194.notes.md`. The Opus @low engine produced the draft, so it scores 0% there.
- Bd. IV p. 684 (index) has a draft only. Index pages are not a priority; the focus is the main
  text and the notes.
- `{page}.scan.jpg` next to a gold file is a copy of the scan for review.

CER = edit distance / gold length after NFC, removal of bidi control marks and `<i>` tags, and collapsing all
whitespace to one space. Per script (Latin, Hebrew, Arabic, Syriac, Greek, common = digits,
punctuation, spaces), each error counts for the script of the gold character it touches.

## Sample

| Vol. | Scan | Page | Kind |
|---|---|---|---|
| IV | 611 | 595 | Index, start of Hebrew/Aramaic plant names |
| IV | 650 | 634 | Index, Latin/Greek names |
| IV | 700 | 684 | Index, dense Hebrew/Aramaic |
| IV | 747 | 731 | Abbreviations, first page |
| I | 211–220 | 191–200 | The whole Pistacia entry (Terebinthus, Lentiscus, vera): Hebrew, Aramaic, Syriac (Estrangela), Arabic, Greek, footnotes |
| II | 307 | 289 | Olea: Hebrew verbs, footnote |
| III | 301 | 287 | Citrus (etrog): rabbinic sources, Hebrew, Persian |

## Translation

`translate.py` sends the blocks of one page to a model with a JSON schema and gets back one
English block per source block. The source is the gold text if `data/gold/{vol}/{page}.txt`
exists, else the OCR (default `or-claude-opus-5.5@low+ital`). Rules (v3, 31-Oct-2026):

- Translate German and French. Keep Latin, English, references and the author's own
  romanizations (with italics).
- **Hebrew script** (Hebrew, Aramaic, Samaritan, Yiddish, Judeo-Arabic): kept as is, **no
  transliteration**.
- **Syriac**: kept, followed by a letter-for-letter rendering in Hebrew characters in square
  brackets, e.g. `ܒܛܡܬܐ [בטמתא]`. Done in code (fixed mapping with final forms), not by the model.
- **Arabic, Persian, Greek**: kept, followed by a Latin transliteration in square brackets
  (IJMES for Arabic and Persian, SBL for Greek).
- **Abbreviations**: at the first use on a page, the expansion from `abbreviations.json` follows
  in brackets, e.g. `BB. [=Bar Bahlūl, Lexicon syriacum]`; unknown ones get `[=?]`. This is done
  by the model, guided by the table (see Notes).
- **Eretz Yisrael** for "Palästina" / "Palestine" (and "Eretz-Yisrael" for the adjective, e.g. `Ph. [=Eretz-Yisrael Hebrew]`); titles of works, journals and societies, and English quotations, stay as printed. New in v3.
- **Roman numerals** become Arabic numerals: `p. XXXIX` → `p. 39`, `Robinson I 346` → `Robinson 1, 346`.
- Lines are joined and end-of-line hyphenation is undone.

### Whole entries

`entry.py` joins the pages of one entry (configured in `ENTRIES`: volume, pages, a start and an
end heading) into continuous text and translates it in chunks of whole paragraphs (about 6,000
characters each), with the same rules. Per page the source is the gold text if it exists, else
the OCR. Running heads are dropped; `[p. N]` marks where page N begins, also inside a paragraph
that runs over the page break; footnotes are listed after the text, grouped by page.
Output: `data/entries/{entry}/de.md` (joined German) and `en.md` (English), plus `.json`.

A paragraph is taken to continue on the next page when the page ends without sentence-final
punctuation. This fails for a page that ends with an abbreviation or a closing bracket mid-sentence
(e.g. "(3.—4. Jh.)" at the end of Bd. I p. 196), so each entry has a `continue` / `break` list,
checked by eye.

### Output folders

Output: `data/translation/{model}@{effort}-{rules version}/{vol}/{page}.json` and `.md`
(footnotes at the end). Every rendered paragraph starts with an invisible left-to-right mark
(U+200E): GitHub sets `dir="auto"` on paragraphs, so a paragraph that starts with a Hebrew word
would otherwise be laid out right to left. The rules version is `RULES_VERSION` in `translate.py`; change it when
the rules change, so that older outputs are kept. Current: `claude-opus-5.5@medium-v3`; `-v2` is the same without the Eretz Yisrael rule.
`claude-opus-5.5@medium-v1` holds the first version (every non-Latin word transliterated,
no abbreviation expansion), kept for comparison.

v2, 7 main-text pages with Opus 5.5 @medium: $0.61 total, about $0.06–0.13 and 26–59 s per page.

## Results so far (31-Oct-2026)

CER on the one gold page (Bd. I p. 194):

| Engine | All | Latin | Hebrew | Arabic | Syriac* | Greek |
|---|---|---|---|---|---|---|
| Opus 5.5 @low (made the draft) | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| Opus 5.5 @low +ital | 1.5% | 0.0% | 4.8% | 0.0% | 23.6% | 0.0% |
| Opus 5.5 @high | 2.3% | 0.0% | 0.0% | 0.0% | 37.0% | 0.0% |
| Qwen 3.8 Max @low | 4.6% | 0.1% | 9.5% | 4.2% | 68.5% | 0.0% |
| Gemini 3.1 Pro @low | 5.5% | 0.1% | 0.0% | 16.9% | 65.4% | 0.0% |
| Sonnet 5.5 @low | 6.4% | 0.3% | 4.8% | 16.9% | 100% | 0.0% |
| GPT-5.6 Sol @low | 7.9% | 1.2% | 14.3% | 7.0% | 100% | 2.6% |
| Kraken + PP-OCRv6 medium | 17.0% | 7.8% | 90.5% | 91.5% | 92.1% | 37.2% |
| Tesseract | 24.3% | 16.0% | 28.6% | 73.2% | 70.9% | 101% |
| Kraken + printed-Syriac model | 69.9% | 72.9% | 100% | 101% | 80.3% | 100% |

\* Syriac gold not verified (127 characters); Hebrew is only 21 characters on this page.
One page, and the gold comes from one of the engines: read these as rough signals only.

Cost and time:

| Engine | Pages | Cost / page | Time / page |
|---|---|---|---|
| tesseract `deu+heb+ara+syr` | 9 | $0 | 11 s |
| `anthropic/claude-opus-5.5` @low | 9 | $0.093 | 31 s |
| `anthropic/claude-sonnet-5.5` @low | 9 | $0.047 | 17 s |
| `google/gemini-3.1-pro-preview` @low | 9 | $0.053 | 32 s |
| `anthropic/claude-opus-5.5` @high | 1 (I/194) | $0.337 | 178 s |
| `openai/gpt-5.6-sol` @low | 1 (I/194) | $0.097 | 23 s |
| `qwen/qwen3.8-max-prime` @low | 1 (I/194) | $0.177 | 235 s |
| `google/gemini-3.8-flash` @low | 1 (I/194) | $0.019 | 26 s |
| `google/gemini-3.8-flash` default effort | 1 (I/194) | $0.116 | 204 s |
| `anthropic/claude-opus-5.5` @low +ital | 7 | $0.103 | 36 s |

OpenRouter prices, effort `low` unless noted. Total OpenRouter spend for the whole project so far (OCR, abbreviations, translation): about $7.00.

## Notes

What I saw by reading the outputs against the scans (not yet measured against gold):

- **German/Latin text** is close to solved for all LLM engines (they differ from each other
  by about 0.5% of Latin-script characters). Tesseract has about 14% there, plus errors from
  small caps and transliteration diacritics.
- **Syriac (Estrangela) is the hard part.** Only Claude Opus 5.5 gives readings that mostly match
  the print. Sonnet 5.5 and GPT-5.6 Sol put `[?]` (honest). Gemini 3.1 Pro, Gemini Flash and
  Qwen write fluent Syriac that is often a different word, sometimes a word that fits the sense
  (e.g. ܨܡܓܐ "resin") but is not on the page. That kind of error is hard to notice.
  Opus @high changes about a third of the Syriac characters on p. 194 compared with @low, at
  3.6× the cost. Three Opus runs give three readings for some words (see
  `data/gold/I/194.notes.md`). The Syriac in gold pages needs a reader who knows Syriac.
- **Hebrew index pages (right-to-left lines with numbers):** Gemini 3.1 Pro reverses the order of
  entries inside a line on p. 684, so page references attach to the wrong headword. Opus keeps
  the printed order but has some ד/ר confusions (`בר` for `בד`).
- **Dropped text:** Sonnet 5.5 returned only the first 5 lines of p. 684 (313 of about
  2,300 characters), with no error. A length check against another engine catches this.
- **Tesseract** puts Hebrew/Arabic words in visual order and turns Greek and small caps into
  Latin junk. Use it only as a baseline.
- **Reasoning budget:** Gemini 3.8 Flash at default effort spent 26k reasoning tokens on one
  page (6× the cost of effort low); the first try hit the 32k output limit. Set effort.
- **Image size:** the APIs downscale to 2576 px long edge and 3.75 MP. `ocr.py` crops to the
  text block and cuts the page in two at a blank line, so each half goes at about 68% of scan
  resolution (about 48% for a whole page).
- The direct Anthropic API engine (`claude`) is written but not run; the
  OpenRouter path covers the same model.
- **Frankfurt has no OCR text** for this work (checked 31-Oct-2026): the IIIF manifests have no
  annotations, the METS record has only image file groups, the full-text download URLs return
  404, and the PDF (its single Helvetica font is generator boilerplate with an empty text block)
  has no text on any of 51 sampled pages.
- **Translation, v1 problem fixed in v2:** v1 transliterated inconsistently (vowels for known
  words, consonants for others). v2 drops transliteration for Hebrew script and renders Syriac
  in Hebrew letters by code; the open question is now only Arabic and Greek.
- **Abbreviation expansion in the translation is done by the model.** Bekiut's Jastrow/BDB
  readers do it deterministically (reviewed mapping, longest match first, conservative with
  short forms, tested). That approach is safer and should replace the model step here.
- Roman numerals: the model leaves some unclear cases (e.g. "1882 21. II. Nr. 2") as printed.
- **Kraken** (7.1.1, CPU, in `.venv-kraken`, Python 3.12): the HTR-United/Zenodo model repository
  has no printed-Hebrew model, only medieval Hebrew manuscript models. Tested on p. 194 with the
  default baseline segmenter:
  - PP-OCRv6 medium, multilingual print (zenodo.21788410): 17.0% CER overall, 7.8% on Latin-script
    letters (Tesseract 16%), but about 90% on Hebrew, Arabic and Syriac (mostly missing or in
    visual order). Transliteration diacritics are dropped (`butm` for `buṭm`). 2 min 21 s.
  - "Experimental printed Syriac" (zenodo.8425684): 70% overall, 80% on Syriac; it reads Latin
    as garbage, and its Syriac comes out in visual (reversed) order.
  - Windows needs `PYTHONUTF8=1` (the model-repository code reads a file as cp1252).
  - Conclusion: a usable non-LLM baseline for Latin script only. Kraken would need a model trained
    on this typeface (the corrected pages from this project could be training data).

## Next decision points

1. More gold pages from main text (e.g. I/193, III/287), and a Syriac reader for the Syriac.
2. Choose the engine: Opus 5.5 for pages with Syriac, maybe a cheaper model for German-only
   pages; or two engines plus a disagreement check, so a person reviews only where they differ.
3. Segment into entries: index paragraphs into single entries (split at ` — `); text pages into
   plant entries by the headings.
4. Abbreviation expansion: move it from the model to a deterministic step after translation
   (as in Bekiut), with tooltip or bracket display.
5. Other targets: see [TARGETS.md](TARGETS.md).

## Abbreviations and bibliography

See [ABBREVIATIONS.md](ABBREVIATIONS.md): every abbreviation and short reference on the OCR'd pages, expanded from Löw's own list (Bd. IV pp. 731–740) where possible. Maintained by `abbrev.py` from `abbreviations.json`.

## Ideas

Brainstorm, not a plan. Rough order: cheap and useful first.

**Quality and cost**
- More gold pages (about 10, main text with footnotes), so that the CER numbers mean something;
  track CER for each prompt version as a regression test.
- A Syriac reader for the Syriac in gold pages; check Syriac words against lexicon headwords
  (Payne Smith, Brockelmann, Sokoloff) and flag words that are in no lexicon.
- Review triage: run two engines (e.g. Opus + Gemini) and send to a person only the lines where
  they disagree, plus pages whose length differs a lot (catches dropped text).
- ~~Check whether Frankfurt's Visual Library already has an OCR text layer~~: done, it has none
  (see Notes).
- Hebrew-specific OCR (Kraken/eScriptorium) as a non-LLM baseline: started, see "Kraken" in Notes.
  The Kraken model repository has no model for printed Hebrew (only medieval manuscripts); a
  printed-Hebrew model would have to be trained, e.g. on corrected pages from this project.
- Full run of all 4 volumes (about 2,700 scans): Opus at about $0.10/page is about $270;
  the Batch API (half price), prompt caching of the abbreviation list, and a cheaper model
  for pages without Syriac/Arabic would lower this.

**Structure**
- Merge pages into continuous text before translation (paragraphs and footnotes that cross
  a page break), and link each footnote mark to its note.
- Segment into plant entries: Latin name, Hebrew/Aramaic/Syriac/Arabic names, sources, notes,
  one JSON record per plant.
- Parse the vol. IV indexes into data (headword → vol., page) and use them to check the entry
  segmentation.
- Parse references with the abbreviation table: rabbinic and Bible references (Rh. 23a,
  jKil. 1, 27a, B. r.) to Sefaria links; bibliography short titles to full records
  (and to scans on archive.org / HathiTrust where they exist).

**Linking**
- Plants to modern taxonomy (POWO / GBIF IDs) and to Wikidata; note where Löw's botanical names
  are now synonyms.
- Bekiut: a plant glossary in the Talmud reader, from a Talmud word to the Löw entry and its
  English translation.
- The talmud-names-discovery work: plant names as a further entity type.

**Readability and access** (for the English output)
- A reading edition as a web page (GitHub Pages): German and English side by side by paragraph,
  the page scan next to them, `[p. N]` as links to the scan.
- Abbreviations as tooltips (`<abbr title="…">`) instead of `[=…]` in the text, with a switch
  to show them inline; the same for transliterations. The text stays clean; nothing is lost.
- Expand references fully in the text where the full form is short and certain:
  `Rh. 23a` → `Rosh Hashanah 23a`, `Gn. 35, 4` → `Genesis 35:4`, linked to Sefaria; keep the
  bracket only for bibliography.
- Footnotes as numbered notes linked from their marks (per entry, not `*)`, `**)` per page),
  shown on hover or at the end of each paragraph.
- A "names at a glance" box at the top of each entry: the plant's names in Hebrew, Aramaic,
  Syriac, Arabic, Greek and Latin, with the main sources, built from the entry.
- A short plain-English summary at the top of each entry (marked as machine-written), and the
  modern scientific and English plant name with a link (POWO / Wikipedia), plus a photo.
- Headings for the sub-sections Löw implies (names, identification, use, rabbinic sources,
  folklore), so a reader can skim.
- Typography: a Hebrew/Syriac font (Noto), slightly larger right-to-left text, `<bdi>` around
  each right-to-left run so punctuation stays in place.
- Exports: PDF and EPUB of each entry; a search page over all entries.

**Translation and publication**
- A term base for recurring German botanical and philological terms, so that the English is
  consistent across volumes.
- A side-by-side view: page image (IIIF viewer, e.g. Mirador), German text, English translation.
- TEI XML output; the text is public domain, so Wikisource and Sefaria are possible homes.
- The blog post with technical appendix (in the to-do list); a short paper on LLM OCR for
  multi-script scholarly prints, with the Syriac findings.

**Other targets** (details in [TARGETS.md](TARGETS.md))
- **Priority:** Lewysohn, *Die Zoologie des Talmuds* (1858), the animal counterpart of the Flora;
  scan on archive.org; Natan Slifkin proposed a collaborative translation in 2012.
- Krauss, *Griechische und lateinische Lehnwörter im Talmud, Midrasch und Targum* (1898–99),
  following my earlier translations of Krauss's transcription rules.
- Löw, *Aramäische Pflanzennamen* (1881), the predecessor of the Flora.
- Other public-domain German works on rabbinic realia (e.g. Krauss, *Talmudische Archäologie*);
  check first what is already OCR'd or translated.
