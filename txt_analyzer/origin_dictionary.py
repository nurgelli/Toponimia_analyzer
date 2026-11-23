from __future__ import annotations
import colorsys
import re
from io import BytesIO
from fastapi import HTTPException
from openpyxl import load_workbook
from sklearn.feature_extraction.text import TfidfVectorizer
from .database import db_connect
from .utils import normalize, split_variants
def import_origin_workbook(content: bytes) -> tuple[int, list[tuple[str, int]]]:
    """Replace the origin lexicon using one language per first-row column."""
    from io import BytesIO
    try:
        workbook = load_workbook(filename=BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Excel dosýasyny okap bolanok: {exc}") from exc
    sheet = workbook.active
    first_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
    languages = [(index, str(value).strip()) for index, value in enumerate(first_row) if value is not None and str(value).strip()]
    if not languages:
        workbook.close()
        raise HTTPException(status_code=400, detail="Ilkinji hatarda dil atlary bolmaly, Mysal üçin: Arapça, Parsça, Rusça.")
    rows: list[tuple[str, str, str]] = []
    for column_index, language in languages:
        for (value,) in sheet.iter_rows(min_row=2, min_col=column_index + 1, max_col=column_index + 1, values_only=True):
            for word in split_variants(value):
                normalized = normalize(word)
                if normalized:
                    rows.append((language, word, normalized))
    workbook.close()
    if not rows:
        raise HTTPException(status_code=400, detail="Dil sütünleriniň aşagynda azyndan bir söz bolmaly.")
    # Validate first, then replace the previous lexicon atomically.
    with db_connect() as db:
        db.execute("DELETE FROM origin_words")
        db.executemany(
            "INSERT OR IGNORE INTO origin_words(language, word, normalized_word) VALUES (?, ?, ?)", rows,
        )
        summary = db.execute("SELECT language, COUNT(*) AS amount FROM origin_words GROUP BY language ORDER BY MIN(id)").fetchall()
    return len(rows), [(row["language"], row["amount"]) for row in summary]


def load_origin_model():
    with db_connect() as db:
        rows = db.execute("SELECT language, word, normalized_word FROM origin_words ORDER BY id").fetchall()
    if not rows:
        return None, {}, []
    exact: dict[str, set[str]] = {}
    aliases: list[tuple[str, str, str]] = []
    for row in rows:
        exact.setdefault(row["normalized_word"], set()).add(row["language"])
        aliases.append((row["normalized_word"], row["language"], row["word"]))
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(1, 3), lowercase=False, norm="l2")
    matrix = vectorizer.fit_transform([row[0] for row in aliases])
    return (vectorizer, matrix, aliases), exact, list(dict.fromkeys(row["language"] for row in rows))


def predict_origin(word: str, model, cache: dict):
    key = normalize(word)
    if key in cache:
        return cache[key]
    if len(key) < 4 or model is None:
        cache[key] = None
        return None
    vectorizer, matrix, aliases = model
    from difflib import SequenceMatcher
    scores = (vectorizer.transform([key]) @ matrix.T).toarray()[0]
    candidates = scores.argsort()[-min(30, len(aliases)):][::-1]
    best_by_language = {}
    for index in candidates:
        alias_key, language, display_word = aliases[int(index)]
        edit_score = SequenceMatcher(None, key, alias_key).ratio()
        score = 0.35 * float(scores[index]) + 0.65 * edit_score
        if language not in best_by_language or score > best_by_language[language][0]:
            best_by_language[language] = (score, language, display_word, edit_score)
    ranked = sorted(best_by_language.values(), key=lambda item: item[0], reverse=True)
    if not ranked:
        cache[key] = None
        return None
    best = ranked[0]
    margin = best[0] - ranked[1][0] if len(ranked) > 1 else 1.0
    if best[0] < 0.60 or best[3] < 0.70 or margin < 0.06:
        cache[key] = None
        return None
    cache[key] = (best[1], best[2], best[0])
    return cache[key]


def language_color(index: int) -> str:
    palette = ["C00000", "0070C0", "548235", "7030A0", "ED7D31", "008C95", "BF9000", "C0007F", "4472C4", "70AD47"]
    if index < len(palette):
        return palette[index]
    hue = (index * 0.61803398875) % 1
    red, green, blue = colorsys.hsv_to_rgb(hue, 0.72, 0.68)
    return "{:02X}{:02X}{:02X}".format(round(red * 255), round(green * 255), round(blue * 255))
