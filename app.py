"""Local MVP for importing a name dictionary and marking DOCX variants."""

from __future__ import annotations

import ast
import html
import os
import re
import sqlite3
import sys
import unicodedata
import uuid
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.shared import RGBColor
from docx.text.run import Run
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from openpyxl import load_workbook
from sklearn.feature_extraction.text import TfidfVectorizer

BASE_DIR = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):
    default_data_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TurkmenAdDenetleyici"
else:
    default_data_dir = BASE_DIR / "data"
DATA_DIR = Path(os.environ.get("TXT_ANALYZER_DATA_DIR", default_data_dir))
DB_PATH = DATA_DIR / "names.sqlite3"
OUTPUT_DIR = DATA_DIR / "processed"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Türkmen Toponomik atlary barlaýjy", version="0.1.0")


def db_connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with db_connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS names (
            id INTEGER PRIMARY KEY,
            canonical TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            variant TEXT NOT NULL,
            UNIQUE(canonical, category, variant)
        )""")


init_db()


def normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold().strip()


def split_variants(value: object) -> list[str]:
    if value is None:
        return []
    raw = str(value).strip()
    if not raw:
        return []
    if raw.startswith("[") and raw.endswith("]"):
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, (list, tuple, set)):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (ValueError, SyntaxError):
            raw = raw[1:-1]
    return [item.strip().strip("\"'") for item in re.split(r"[,;|\n\r]+", raw) if item.strip().strip("\"'")]


def import_workbook(content: bytes) -> tuple[int, int]:
    try:
        from io import BytesIO
        workbook = load_workbook(filename=BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Excel dosýasyny okap bolmady: {exc}") from exc

    rows: list[tuple[str, str, str]] = []
    for row in workbook.active.iter_rows(min_col=1, max_col=3, values_only=True):
        canonical = str(row[0]).strip() if row[0] is not None else ""
        category = str(row[1]).strip() if row[1] is not None else ""
        if not canonical or normalize(canonical) in {"dogru ad", "doğru ad", "standart ad", "canonical"}:
            continue
        for variant in split_variants(row[2]):
            if normalize(variant) != normalize(canonical):
                rows.append((canonical, category, variant))
    workbook.close()

    if not rows:
        raise HTTPException(status_code=400, detail="Excelde A sütünde standart at we C sütüninde azyndan 1 warýant tapyp bolmady.")
    with db_connect() as db:
        db.executemany(
            "INSERT INTO names(canonical, category, variant) VALUES (?, ?, ?) "
            "ON CONFLICT(canonical, category, variant) DO NOTHING", rows,
        )
        stored = db.execute("SELECT COUNT(*) FROM names").fetchone()[0]
    return len(rows), stored


def load_patterns() -> list[tuple[re.Pattern[str], str, str, str]]:
    with db_connect() as db:
        records = db.execute("SELECT canonical, category, variant FROM names ORDER BY length(variant) DESC").fetchall()
    patterns = []
    for record in records:
        variant = record["variant"].strip()
        expression = r"\s+".join(re.escape(part) for part in re.split(r"\s+", variant) if part)
        if expression:
            patterns.append((re.compile(rf"(?<!\w){expression}(?!\w)", re.IGNORECASE | re.UNICODE), record["canonical"], record["category"], variant))
    return patterns


def train_similarity_model():
    """Fit a character n-gram nearest-neighbor index from the current SQLite data."""
    with db_connect() as db:
        rows = db.execute("SELECT canonical, category, variant FROM names ORDER BY id").fetchall()
    aliases = []
    for row in rows:
        variant = unicodedata.normalize("NFC", row["variant"]).strip()
        if variant:
            aliases.append((normalize(variant), row["canonical"], row["category"], variant))
    if not aliases:
        return None
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(1, 3), lowercase=False, norm="l2")
    matrix = vectorizer.fit_transform([alias[0] for alias in aliases])
    canonical_names = {normalize(row["canonical"]) for row in rows}
    return vectorizer, matrix, aliases, canonical_names


def predict_variant(word: str, model, cache: dict):
    """Predict from learned character features; score is similarity, not probability."""
    key = normalize(word)
    if key in cache:
        return cache[key]
    if len(key) < 4 or model is None:
        cache[key] = None
        return None
    vectorizer, matrix, aliases, canonical_names = model
    if key in canonical_names or any(key == alias[0] for alias in aliases):
        cache[key] = None
        return None
    query = vectorizer.transform([key])
    cosine_scores = (query @ matrix.T).toarray()[0]
    candidates = cosine_scores.argsort()[-min(25, len(aliases)):][::-1]
    from difflib import SequenceMatcher
    best_by_name = {}
    for index in candidates:
        alias_key, canonical, category, variant = aliases[int(index)]
        edit_score = SequenceMatcher(None, key, alias_key).ratio()
        score = 0.35 * float(cosine_scores[index]) + 0.65 * edit_score
        identity = (normalize(canonical), category)
        previous = best_by_name.get(identity)
        if previous is None or score > previous[0]:
            best_by_name[identity] = (score, canonical, category, variant, edit_score)
    ranked = sorted(best_by_name.values(), key=lambda item: item[0], reverse=True)
    if not ranked:
        cache[key] = None
        return None
    best = ranked[0]
    margin = best[0] - ranked[1][0] if len(ranked) > 1 else 1.0
    # Conservative thresholds reduce false positives on short/common words.
    if best[0] < 0.60 or best[4] < 0.70 or margin < 0.06:
        cache[key] = None
        return None
    result = (best[1], best[2], best[3], best[0])
    cache[key] = result
    return result


def mark_paragraph(paragraph, patterns, model, prediction_cache: dict, auto_correct: bool = False):
    runs = list(paragraph.runs)
    if not runs:
        return Counter(), Counter()
    text = "".join(run.text for run in runs)
    if not text:
        return Counter(), Counter()

    matches: list[tuple[int, int, str, str, str]] = []
    for pattern, canonical, category, variant in patterns:
        for match in pattern.finditer(text):
            matches.append((match.start(), match.end(), canonical, category, variant))
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    selected: list[tuple[int, int, str, str, str]] = []
    last_end = -1
    for match in matches:
        if match[0] >= last_end:
            selected.append(match)
            last_end = match[1]
    exact_spans = [(start, end) for start, end, *_ in selected]
    predictions = []
    predicted_counts = Counter()
    for token_match in re.finditer(r"(?<!\w)[^\W_]+(?!\w)", text, re.UNICODE):
        start, end = token_match.span()
        if any(start < exact_end and end > exact_start for exact_start, exact_end in exact_spans):
            continue
        predicted = predict_variant(token_match.group(), model, prediction_cache)
        if predicted is not None:
            canonical, category, nearest_variant, score = predicted
            predictions.append((start, end, canonical, category, nearest_variant, score))
            predicted_counts[(token_match.group(), canonical, category, nearest_variant, round(score * 100))] += 1

    if not selected and not predictions:
        return Counter(), Counter()

    marked = [(start, end, "red") for start, end, *_ in selected]
    marked.extend((start, end, "blue") for start, end, *_ in predictions)
    source_runs = []
    offset = 0
    for run in runs:
        source_runs.append((offset, offset + len(run.text), run))
        offset += len(run.text)
    paragraph_element = paragraph._p
    corrected_spans = set()
    for run_start, run_end, source_run in source_runs:
        if run_start == run_end:
            continue
        split_points = {run_start, run_end}
        for start, end, _ in marked:
            if run_start < start < run_end:
                split_points.add(start)
            if run_start < end < run_end:
                split_points.add(end)
        points = sorted(split_points)
        replacements = []
        for start, end in zip(points, points[1:]):
            if start == end:
                continue
            local_start, local_end = start - run_start, end - run_start
            fragment = source_run.text[local_start:local_end]
            mark_color = next((color for mark_start, mark_end, color in marked if start >= mark_start and end <= mark_end), None)
            exact_match = next((match for match in selected if start >= match[0] and end <= match[1]), None)
            was_corrected = False
            if auto_correct and exact_match is not None:
                match_key = (exact_match[0], exact_match[1])
                if match_key in corrected_spans:
                    continue
                corrected_spans.add(match_key)
                fragment = exact_match[2]
                was_corrected = True
            cloned = deepcopy(source_run._r)
            paragraph_element.insert(paragraph_element.index(source_run._r), cloned)
            replacement_run = Run(cloned, paragraph)
            replacement_run.text = fragment
            if mark_color == "red" and not was_corrected:
                replacement_run.font.color.rgb = RGBColor(255, 0, 0)
            elif mark_color == "blue":
                replacement_run.font.color.rgb = RGBColor(0, 112, 192)
        paragraph_element.remove(source_run._r)
    exact_counts = Counter((canonical, category, variant) for _, _, canonical, category, variant in selected)
    return exact_counts, predicted_counts


def iter_paragraphs(container) -> Iterable:
    for paragraph in container.paragraphs:
        yield paragraph
    for table in container.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from iter_paragraphs(cell)


def analyze_docx(content: bytes, auto_correct: bool = False) -> tuple[bytes, Counter, Counter]:
    try:
        from io import BytesIO
        document = Document(BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Word dosýasy okalmady; .docx formatda bolmaly: {exc}") from exc
    patterns = load_patterns()
    if not patterns:
        raise HTTPException(status_code=400, detail="Ilki excel sözlügini ýükläň.")
    model = train_similarity_model()
    counts: Counter = Counter()
    predicted_counts: Counter = Counter()
    prediction_cache = {}
    for paragraph in iter_paragraphs(document):
        exact, predicted = mark_paragraph(paragraph, patterns, model, prediction_cache, auto_correct)
        counts.update(exact)
        predicted_counts.update(predicted)
    for section in document.sections:
        for container in (section.header, section.footer, section.first_page_header, section.first_page_footer):
            for paragraph in iter_paragraphs(container):
                exact, predicted = mark_paragraph(paragraph, patterns, model, prediction_cache, auto_correct)
                counts.update(exact)
                predicted_counts.update(predicted)
    output = BytesIO()
    document.save(output)
    return output.getvalue(), counts, predicted_counts


def page(message: str = "", error: bool = False) -> str:
    with db_connect() as db:
        total = db.execute("SELECT COUNT(*) FROM names").fetchone()[0]
        canonicals = db.execute("SELECT COUNT(DISTINCT canonical) FROM names").fetchone()[0]
    notice = f'<p class="notice {"error" if error else ""}">{html.escape(message) if error else message}</p>' if message else ""
    return f"""<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Türkmen toponomik atlar boýunça ýalňyşlary ýüze çykaryjy</title><style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:850px;margin:40px auto;padding:0 20px;color:#18212f;background:#f5f7fa}}
h1{{margin-bottom:4px}}.sub{{color:#596579;margin-top:0}}section{{background:white;padding:24px;margin:20px 0;border:1px solid #dce2ea;border-radius:12px}}
label{{display:block;font-weight:650;margin:14px 0 6px}}input[type=file]{{display:block;margin:8px 0 16px}}button{{background:#174ea6;color:white;border:0;border-radius:7px;padding:10px 16px;font-size:15px;cursor:pointer}}
.notice{{background:#e9f5ec;padding:12px;border-radius:8px}}.error{{background:#fdeaea}}small{{color:#596579}}
</style><body><h1>Türkmen toponomik ýalňyş ýazylanlary kesgitleýji</h1><p class="sub">Excel sözlügindäki ýalňyş at warýantlaryny Word dokumentinde gyzyl bilen belgileýär.</p>
{notice}<p><b>Sözlük:</b> {canonicals} standart at · {total} ýazylyş warýanty</p>
<section><h2>1. Excel sözlügini ýükle</h2><p>A sütüni: standart at · B sütünü: görnüşi/etiketi · C sütünü: ýalňyş ýazylyşlary (mysal. <code>[Daşhowuz, Taşhowuz, Taşowuz]</code>).</p>
<form action="/dictionary" method="post" enctype="multipart/form-data"><label for="excel">Excel dosýasy (.xlsx)</label><input id="excel" type="file" name="file" accept=".xlsx" required><button>Ýükle we sözlüge goş</button></form></section>
<section><h2>2. Wordy barla</h2><form action="/analyze" method="post" enctype="multipart/form-data"><label for="docx">Word dosýasy (.docx)</label><input id="docx" type="file" name="file" accept=".docx" required><label><input type="checkbox" name="auto_correct" value="true"> Awtomatiki düzetmelimi?</label><button>Barla</button></form></section>
<small>Gyzyl bilen reňklenen sanawdaky warýantlardyr; Gök reňdäkiler meňzeşligi bar diýlip çaklanylýanlar.</small></body></html>"""


@app.get("/", response_class=HTMLResponse)
def home():
    controls = '''<p>Reňk açarlary: <span style="color:#f00">gyzyl = hasaba alnan ýalňyşlyk</span>; <span style="color:#0070c0">gök = model çaklamasy</span>.</p>
    <section><h2>Sözlügi nolla</h2><p>Hasaba alnan Excel maglumatlaryny pozýar. Täze Excel ýüklenende model täzeden öwrenýär.</p>
    <form action="/reset" method="post" onsubmit="return confirm('Sözlük maglumatlarynyň ählisi pozulsynmy?')"><button style="background:#8b2635">Sözlügi we öwrenilen maglumatlary poz</button></form></section>
    <small>Excel ýüklenende bar bolan sözlüge goşulýar. Her skän edilende model aktual maglumatdan öwrenýär; çaklamalary awtomatiki ýagdaýda düzetmeýär.</small>'''
    return page().replace("</body></html>", controls + "</body></html>")


@app.post("/reset", response_class=HTMLResponse)
def reset_dictionary():
    with db_connect() as db:
        db.execute("DELETE FROM names")
    return HTMLResponse(page("Sözlük we modeliň öwrenjegi maglumatlar pozuldy. Täze Excel dosýa ýükläp bilersiňiz."))


@app.post("/dictionary", response_class=HTMLResponse)
async def upload_dictionary(file: UploadFile = File(...)):
    if not file.filename or Path(file.filename).suffix.lower() != ".xlsx":
        return HTMLResponse(page(".xlsx formatdaky dosýany saýlamaly.", True), status_code=400)
    try:
        added, total = import_workbook(await file.read())
    except HTTPException as exc:
        return HTMLResponse(page(str(exc.detail), True), status_code=exc.status_code)
    return HTMLResponse(page(f"Excel özleşdirildi: {added} warýant okaldy. Jemi özboluşly bolan: {total}."))


@app.post("/analyze", response_class=HTMLResponse)
async def upload_document(file: UploadFile = File(...), auto_correct: bool = Form(False)):
    if not file.filename or Path(file.filename).suffix.lower() != ".docx":
        return HTMLResponse(page(".docx formatynda bir Word dosýasyny saýlaň.", True), status_code=400)
    try:
        output, counts, predicted_counts = analyze_docx(await file.read(), auto_correct)
    except HTTPException as exc:
        return HTMLResponse(page(str(exc.detail), True), status_code=exc.status_code)
    output_name = f"{uuid.uuid4().hex}_marked.docx"
    (OUTPUT_DIR / output_name).write_bytes(output)
    total = sum(counts.values()) + sum(predicted_counts.values())
    if counts or predicted_counts:
        details = "".join(f"<li><b>{html.escape(variant)}</b> → {html.escape(canonical)} ({html.escape(category or 'etiketsiz')}): {count}</li>" for (canonical, category, variant), count in counts.items())
        summary = f"Ylmy-iş skän edildi: {total} sany gabat geldi. <a href=\"/download/{output_name}\">Yşaratlanan word dokumenti ýükläp al</a>.<ul>{details}</ul>"
    else:
        summary = f'Ylmy-iş skän edildi; ýalňyşlyk gabat gelmedi. <a href="/download/{output_name}">Işlenen dokumendi ýükläp al</a>.'
    if auto_correct and counts:
        summary = "Awtomatiki düzediş açyk: gyzyl gabat gelişler standart at bilen çalşyryldy. Gök çaklamalar üýtgedilmedi.<br>" + summary
    if predicted_counts:
        predictions_html = "".join(
            f"<li><b>{html.escape(observed)}</b> → {html.escape(canonical)} "
            f"(çaklama; iň ýakyn hasaba alnan warýant: {html.escape(nearest_variant)}, meňzeşlik %{score}): {count}</li>"
            for (observed, canonical, category, nearest_variant, score), count in predicted_counts.items()
        )
        summary += f"<h3>Gök çaklamalar</h3><ul>{predictions_html}</ul>"
    return HTMLResponse(page(summary))


@app.get("/download/{filename}")
def download(filename: str):
    if Path(filename).name != filename or not filename.endswith("_marked.docx"):
        raise HTTPException(status_code=404)
    path = OUTPUT_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, filename="marked_document.docx", media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
