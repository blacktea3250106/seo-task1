"""Tool 4 的核心：關鍵字次數（沿用 V2 規則，改成回傳原文裡的實際寫法）。

exact＝原字串逐字計數；loose＝NFKC＋不分大小寫，字元間允許空白、+、-、_。
ASCII 英數開頭／結尾的關鍵字要求邊界，避免雜湊字串裡的 3a 被算成命中。
"""
from __future__ import annotations

import re
import unicodedata

_SEP_CHARS = re.compile(r"[\s+\-_]")


def _norm_with_map(text: str) -> tuple[str, list[int]]:
    out, index = [], []
    for i, ch in enumerate(text):
        for n in unicodedata.normalize("NFKC", ch).casefold():
            out.append(n)
            index.append(i)
    return "".join(out), index


def _pattern(keyword: str) -> re.Pattern:
    norm, _ = _norm_with_map(keyword)
    chars = [c for c in norm if not _SEP_CHARS.match(c)]
    body = r"[\s+\-_]*".join(re.escape(c) for c in chars)
    head = r"(?<![0-9a-z])" if chars and chars[0].isascii() and chars[0].isalnum() else ""
    tail = r"(?![0-9a-z])" if chars and chars[-1].isascii() and chars[-1].isalnum() else ""
    return re.compile(head + body + tail)


def keyword_hits(text: str, keyword: str, max_variants: int = 6, contexts: int = 3) -> dict:
    text = text or ""
    if not keyword.strip():
        return {"exact": 0, "loose": 0, "variants": {}, "contexts": []}
    norm, index = _norm_with_map(text)
    variants: dict[str, int] = {}
    snippets = []
    loose = 0
    for m in _pattern(keyword).finditer(norm):
        loose += 1
        start, end = index[m.start()], index[m.end() - 1] + 1
        original = text[start:end]
        variants[original] = variants.get(original, 0) + 1
        if len(snippets) < contexts:
            snippets.append(text[max(0, start - 30):end + 30].replace("\n", " "))
    top = dict(sorted(variants.items(), key=lambda kv: (-kv[1], kv[0]))[:max_variants])
    return {"exact": text.count(keyword), "loose": loose, "variants": top, "contexts": snippets}
