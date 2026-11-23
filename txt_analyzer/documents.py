from __future__ import annotations
import re
from collections import Counter
from copy import deepcopy
from io import BytesIO
from typing import Iterable
from docx import Document
from docx.shared import RGBColor
from docx.text.run import Run
from fastapi import HTTPException
from .database import db_connect
from .utils import normalize
from .name_dictionary import load_patterns, train_similarity_model, predict_variant
from .origin_dictionary import load_origin_model, language_color, predict_origin
def mark_origin_paragraph(paragraph, model, exact_map, language_index, cache):
    runs = list(paragraph.runs)
    text = "".join(run.text for run in runs)
    exact_counts, predicted_counts = Counter(), Counter()
    if not text:
        return exact_counts, predicted_counts, 0, 0, 0
    marks = []
    ambiguous = 0
    for match in re.finditer(r"(?<!\w)[^\W_]+(?!\w)", text, re.UNICODE):
        token = match.group()
        key = normalize(token)
        langs = exact_map.get(key, set())
        if len(langs) == 1:
            language = next(iter(langs))
            marks.append((match.start(), match.end(), language, False))
            exact_counts[(language, token)] += 1
        elif len(langs) > 1:
            ambiguous += 1
        else:
            prediction = predict_origin(token, model, cache)
            if prediction:
                language, nearest, score = prediction
                marks.append((match.start(), match.end(), language, True))
                predicted_counts[(language, token, nearest, round(score * 100))] += 1
    if marks:
        offsets, offset = [], 0
        for run in runs:
            offsets.append((offset, offset + len(run.text), run))
            offset += len(run.text)
        element = paragraph._p
        for start_run, end_run, source in offsets:
            if start_run == end_run:
                continue
            points = {start_run, end_run}
            for start, end, _, _ in marks:
                if start_run < start < end_run: points.add(start)
                if start_run < end < end_run: points.add(end)
            ordered = sorted(points)
            for start, end in zip(ordered, ordered[1:]):
                clone = deepcopy(source._r)
                element.insert(element.index(source._r), clone)
                replacement = Run(clone, paragraph)
                replacement.text = source.text[start-start_run:end-start_run]
                found = next((mark for mark in marks if start >= mark[0] and end <= mark[1]), None)
                if found:
                    replacement.font.color.rgb = RGBColor.from_string(language_color(language_index[found[2]]))
                    if found[3]: replacement.font.underline = True
            element.remove(source._r)
    token_count = sum(1 for _ in re.finditer(r"(?<!\w)[^\W_]+(?!\w)", text, re.UNICODE))
    recognized = sum(exact_counts.values()) + sum(predicted_counts.values())
    return exact_counts, predicted_counts, ambiguous, token_count - recognized - ambiguous, token_count


def analyze_origins_docx(content: bytes):
    from io import BytesIO
    try:
        document = Document(BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Word dosýasyny okap bolanok; .docx olmalı: {exc}") from exc
    model, exact_map, languages = load_origin_model()
    if model is None:
        raise HTTPException(status_code=400, detail="Ilki dil sütüni bolan kök sözlügi ýükläň.")
    language_index = {language: index for index, language in enumerate(languages)}
    exact, predicted, cache = Counter(), Counter(), {}
    ambiguous = unknown = total = 0
    for paragraph in iter_paragraphs(document):
        found, guessed, amb, unk, tokens = mark_origin_paragraph(paragraph, model, exact_map, language_index, cache)
        exact.update(found); predicted.update(guessed); ambiguous += amb; unknown += unk; total += tokens
    for section in document.sections:
        for container in (section.header, section.footer, section.first_page_header, section.first_page_footer):
            for paragraph in iter_paragraphs(container):
                found, guessed, amb, unk, tokens = mark_origin_paragraph(paragraph, model, exact_map, language_index, cache)
                exact.update(found); predicted.update(guessed); ambiguous += amb; unknown += unk; total += tokens
    output = BytesIO(); document.save(output)
    return output.getvalue(), exact, predicted, ambiguous, unknown, total, languages

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
        raise HTTPException(status_code=400, detail=f"Word dosýasy okap bolanok; .docx formatda bolmaly: {exc}") from exc
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
