from __future__ import annotations

import html
import uuid
from collections import Counter
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from .config import OUTPUT_DIR
from .database import db_connect
from .documents import analyze_docx, analyze_origins_docx
from .name_dictionary import import_workbook
from .origin_dictionary import import_origin_workbook, language_color, load_origin_model

app = FastAPI(title="Türkmen Toponomik atlary barlaýjy", version="0.1.0")


def page(message: str = "", error: bool = False) -> str:
    with db_connect() as db:
        total = db.execute("SELECT COUNT(*) FROM names").fetchone()[0]
        canonicals = db.execute(
            "SELECT COUNT(DISTINCT canonical) FROM names"
        ).fetchone()[0]
    notice = (
        f'<p class="notice {"error" if error else ""}">{html.escape(message) if error else message}</p>'
        if message
        else ""
    )
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
    controls = """<p>Reňk açarlary: <span style="color:#f00">gyzyl = hasaba alnan ýalňyşlyk</span>; <span style="color:#0070c0">gök = model çaklamasy</span>.</p>
    <section><h2>Sözlügi nolla</h2><p>Hasaba alnan Excel maglumatlaryny pozýar. Täze Excel ýüklenende model täzeden öwrenýär.</p>
    <form action="/reset" method="post" onsubmit="return confirm('Sözlük maglumatlarynyň ählisi pozulsynmy?')"><button style="background:#8b2635">Sözlügi we öwrenilen maglumatlary poz</button></form></section>
    <small>Excel ýüklenende bar bolan sözlüge goşulýar. Her skän edilende model aktual maglumatdan öwrenýär; çaklamalary awtomatiki ýagdaýda düzetmeýär.</small>"""
    navigation = '<nav class="sidebar" style="position:fixed;left:20px;top:32px;width:190px;background:#fff;padding:18px;border:1px solid #dce2ea;border-radius:12px"><b>ANALİZLER</b><a style="display:block;margin-top:12px;color:#174ea6" href="/">Ýer-ýurt atlary</a><a style="display:block;margin-top:12px;color:#174ea6" href="/origins">Sözüň gelip çykyşy</a></nav>'
    return (
        page()
        .replace("</style><body>", "</style><body>" + navigation)
        .replace("</body></html>", controls + "</body></html>")
    )


@app.post("/reset", response_class=HTMLResponse)
def reset_dictionary():
    with db_connect() as db:
        db.execute("DELETE FROM names")
    return HTMLResponse(
        page(
            "Sözlük we modeliň öwrenjegi maglumatlar pozuldy. Täze Excel dosýa ýükläp bilersiňiz."
        )
    )


@app.post("/dictionary", response_class=HTMLResponse)
async def upload_dictionary(file: UploadFile = File(...)):
    if not file.filename or Path(file.filename).suffix.lower() != ".xlsx":
        return HTMLResponse(
            page(".xlsx formatdaky dosýany saýlamaly.", True), status_code=400
        )
    try:
        added, total = import_workbook(await file.read())
    except HTTPException as exc:
        return HTMLResponse(page(str(exc.detail), True), status_code=exc.status_code)
    return HTMLResponse(
        page(
            f"Excel özleşdirildi: {added} warýant okaldy. Jemi özboluşly bolan: {total}."
        )
    )


@app.post("/analyze", response_class=HTMLResponse)
async def upload_document(
    file: UploadFile = File(...), auto_correct: bool = Form(False)
):
    if not file.filename or Path(file.filename).suffix.lower() != ".docx":
        return HTMLResponse(
            page(".docx formatynda bir Word dosýasyny saýlaň.", True), status_code=400
        )
    try:
        output, counts, predicted_counts = analyze_docx(await file.read(), auto_correct)
    except HTTPException as exc:
        return HTMLResponse(page(str(exc.detail), True), status_code=exc.status_code)
    output_name = f"{uuid.uuid4().hex}_marked.docx"
    (OUTPUT_DIR / output_name).write_bytes(output)
    total = sum(counts.values()) + sum(predicted_counts.values())
    if counts or predicted_counts:
        details = "".join(
            f"<li><b>{html.escape(variant)}</b> → {html.escape(canonical)} ({html.escape(category or 'etiketsiz')}): {count}</li>"
            for (canonical, category, variant), count in counts.items()
        )
        summary = f'Ylmy-iş skän edildi: {total} sany gabat geldi. <a href="/download/{output_name}">Yşaratlanan word dokumenti ýükläp al</a>.<ul>{details}</ul>'
    else:
        summary = f'Ylmy-iş skän edildi; ýalňyşlyk gabat gelmedi. <a href="/download/{output_name}">Işlenen dokumendi ýükläp al</a>.'
    if auto_correct and counts:
        summary = (
            "Awtomatiki düzediş açyk: gyzyl gabat gelişler standart at bilen çalşyryldy. Gök çaklamalar üýtgedilmedi.<br>"
            + summary
        )
    if predicted_counts:
        predictions_html = "".join(
            f"<li><b>{html.escape(observed)}</b> → {html.escape(canonical)} "
            f"(çaklama; iň ýakyn hasaba alnan warýant: {html.escape(nearest_variant)}, meňzeşlik %{score}): {count}</li>"
            for (
                observed,
                canonical,
                category,
                nearest_variant,
                score,
            ), count in predicted_counts.items()
        )
        summary += f"<h3>Gök çaklamalar</h3><ul>{predictions_html}</ul>"
    return HTMLResponse(page(summary))


@app.get("/download/{filename}")
def download(filename: str):
    if Path(filename).name != filename or not (
        filename.endswith("_marked.docx") or filename.endswith("_origins.docx")
    ):
        raise HTTPException(status_code=404)
    path = OUTPUT_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404)
    download_name = (
        "origin_analysis.docx"
        if filename.endswith("_origins.docx")
        else "marked_document.docx"
    )
    return FileResponse(
        path,
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def origin_page(message: str = "", error: bool = False, report: str = "") -> str:
    model, exact_map, languages = load_origin_model()
    with db_connect() as db:
        summary = db.execute(
            "SELECT language, COUNT(*) AS amount FROM origin_words GROUP BY language ORDER BY MIN(id)"
        ).fetchall()
    lexicon_status = (
        " · ".join(
            f"{html.escape(row['language'])}: {row['amount']} sözcük" for row in summary
        )
        or "Henüz dil sözlüğü yüklenmedi."
    )
    notice = (
        f'<p class="notice {"error" if error else ""}">{html.escape(message)}</p>'
        if message
        else ""
    )
    nav = '<nav class="sidebar"><b>ANALİZLER</b><a href="/">Ýer-ýurt atlary</a><a href="/origins">Sözüň gelip çykyşy</a></nav>'
    return f"""<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Sözcük kökeni analizi</title><style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:900px;margin:40px auto;padding:0 20px;color:#18212f;background:#f5f7fa}}
.sidebar{{position:fixed;left:20px;top:32px;width:190px;background:#fff;padding:18px;border:1px solid #dce2ea;border-radius:12px}}.sidebar a{{display:block;margin-top:12px;color:#174ea6}}
@media(max-width:1100px){{.sidebar{{position:static;width:auto;display:flex;gap:18px;align-items:center}}.sidebar a{{margin:0}}}}
h1{{margin-bottom:4px}}.sub{{color:#596579;margin-top:0}}section{{background:white;padding:24px;margin:20px 0;border:1px solid #dce2ea;border-radius:12px}}
label{{display:block;font-weight:650;margin:14px 0 6px}}input[type=file]{{display:block;margin:8px 0 16px}}button{{background:#174ea6;color:white;border:0;border-radius:7px;padding:10px 16px;font-size:15px;cursor:pointer}}
.notice{{background:#e9f5ec;padding:12px;border-radius:8px}}.error{{background:#fdeaea}}.bar{{height:15px;background:#e8edf3;border-radius:8px;overflow:hidden}}.fill{{height:100%}}.lang{{display:grid;grid-template-columns:160px 1fr 180px;gap:12px;align-items:center;margin:12px 0}}small{{color:#596579}}
</style><body>{nav}<h1>Sözcükleriň gelip çykyşy</h1><p class="sub">Excel sözlügindäki dillere görä sözcükleri tapar we meňzeşlikleri çaklar.</p>{notice}
<p><b>Ýüklenen sözlük:</b> {lexicon_status}</p>
<section><h2>1. Dil sözlügini ýükläň</h2><p>Excel-iň birinji setirinde dil atlary bolmaly. Her dili aýratyn sütünde görkeziň, aşagyna şol dile degişli sözcükleri ýazyň. Mysal: Arapça, Türkmençe, Farsça, Rusça, Türkçe. Täze faýl öňki gelip çykyş sözlüginiň üstüne ýazýar.</p>
<form action="/origins/dictionary" method="post" enctype="multipart/form-data"><label for="origin-excel">Excel (.xlsx)</label><input id="origin-excel" type="file" name="file" accept=".xlsx" required><button>Sözlügi öwren</button></form>
<form action="/origins/reset" method="post" onsubmit="return confirm('Gelip çykyş sözlügi doly pozulsynmy?')"><button style="background:#8b2635">Gelip çykyş sözlügini nolla</button></form></section>
<section><h2>2. Word resminamasyny derňäň</h2><form action="/origins/analyze" method="post" enctype="multipart/form-data"><label for="origin-docx">Word (.docx)</label><input id="origin-docx" type="file" name="file" accept=".docx" required><button>Derňew</button></form></section>{report}
<small>Gaty meňzeş sözcükler şol diliň reňki bilen we aşagy çyzylan görnüşde çaklama hökmünde görkezilýär. Meňzeşlik göterimi takyk ähtimallyk däldir. Birnäçe diliň sözlüginde bar bolan sözcükler düşnüksiz hökmünde aýratyn hasaplanýar.</small></body></html>"""


@app.get("/origins", response_class=HTMLResponse)
def origin_home():
    return origin_page()


@app.post("/origins/dictionary", response_class=HTMLResponse)
async def upload_origin_dictionary(file: UploadFile = File(...)):
    if not file.filename or Path(file.filename).suffix.lower() != ".xlsx":
        return HTMLResponse(
            origin_page(".xlsx formatdaky faýly saýlaň.", True), status_code=400
        )
    try:
        added, languages = import_origin_workbook(await file.read())
    except HTTPException as exc:
        return HTMLResponse(
            origin_page(str(exc.detail), True), status_code=exc.status_code
        )
    language_text = ", ".join(f"{name}: {count}" for name, count in languages)
    return HTMLResponse(
        origin_page(f"Sözlük täzelendi. {added} öýjük okaldy. {language_text}")
    )


@app.post("/origins/reset", response_class=HTMLResponse)
def reset_origin_dictionary():
    with db_connect() as db:
        db.execute("DELETE FROM origin_words")
    return HTMLResponse(
        origin_page("Gelip çykyş sözlügi we model maglumatlary pozuldy.")
    )


@app.post("/origins/analyze", response_class=HTMLResponse)
async def upload_origin_document(file: UploadFile = File(...)):
    if not file.filename or Path(file.filename).suffix.lower() != ".docx":
        return HTMLResponse(
            origin_page(".docx formatynda Word faýly saýlaň.", True), status_code=400
        )
    try:
        output, exact, predicted, ambiguous, unknown, total, languages = (
            analyze_origins_docx(await file.read())
        )
    except HTTPException as exc:
        return HTMLResponse(
            origin_page(str(exc.detail), True), status_code=exc.status_code
        )
    filename = f"{uuid.uuid4().hex}_origins.docx"
    (OUTPUT_DIR / filename).write_bytes(output)
    totals = Counter()
    predictions = Counter()
    for (language, word), count in exact.items():
        totals[language] += count
    for (language, word, nearest, score), count in predicted.items():
        predictions[language] += count
    rows = []
    for index, language in enumerate(languages):
        count = totals[language]
        percent = 100 * count / total if total else 0
        color = language_color(index)
        rows.append(
            f'<div class="lang"><b style="color:#{color}">{html.escape(language)}</b><div class="bar"><div class="fill" style="width:{percent:.2f}%;background:#{color}"></div></div><span>{count} anyk · {percent:.1f}% · {predictions[language]} çaklama</span></div>'
        )
    exact_items = (
        "".join(
            f"<li>{html.escape(language)}: <b>{html.escape(word)}</b> — {count}</li>"
            for (language, word), count in exact.most_common(60)
        )
        or "<li>Anyk gabat geliş ýok.</li>"
    )
    predicted_items = (
        "".join(
            f"<li>{html.escape(word)} → {html.escape(nearest)} ({html.escape(language)}, meňzeşlik %{score}): {count}</li>"
            for (language, word, nearest, score), count in predicted.most_common(60)
        )
        or "<li>Çaklama ýok.</li>"
    )
    report = f"""<section><h2>Netije</h2><p>Jemi <b>{total}</b> sözcük: <b>{sum(totals.values())}</b> anyk tapyldy, <b>{sum(predictions.values())}</b> çaklandy, <b>{ambiguous}</b> birnäçe dile gabat geldi, <b>{unknown}</b> näbelli galdy.</p>{"".join(rows)}<p><small>Göterim her diliň anyk gabat gelen sözcükleriniň resminamadaky ähli sözcüklere gatnaşygydyr. Çaklamalar aýratyn görkezilýär we göterime goşulmaýar.</small></p><p><a href="/download/{filename}">Reňklenen Word resminamasyny ýükläň</a></p><h3>Any tak gabat gelişler</h3><ul>{exact_items}</ul><h3>Model çaklamalary</h3><ul>{predicted_items}</ul></section>""".replace(
        "Any tak", "Anyk"
    )
    return HTMLResponse(origin_page(report=report))
