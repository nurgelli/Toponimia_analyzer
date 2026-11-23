from __future__ import annotations
import re
import unicodedata
from io import BytesIO
from difflib import SequenceMatcher
from fastapi import HTTPException
from openpyxl import load_workbook
from sklearn.feature_extraction.text import TfidfVectorizer
from .database import db_connect
from .utils import normalize, split_variants
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
        if not canonical or normalize(canonical) in {"dogry at", "standart at", "canonical"}:
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
