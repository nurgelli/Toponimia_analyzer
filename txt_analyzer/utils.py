from __future__ import annotations
import ast
import re
import unicodedata

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