#!/usr/bin/env python3
"""
Counts tokens in a string using tiktoken (cl100k_base, the encoding used by
Claude-family and GPT-4-family models) when available, and falls back to a
cheap heuristic when tiktoken is not installed in the host environment.
"""

from __future__ import annotations

import importlib
import re
from functools import lru_cache

_ENCODER = None
_ENCODER_PROBED = False

# Roughly: English text averages ~4 chars/token for cl100k_base, JSON averages
# somewhat fewer because of dense punctuation. We split on word/non-word
# boundaries and count both words and punctuation tokens, then scale.
_WORD_RE = re.compile(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]")


@lru_cache(maxsize=1)
def _probe_tiktoken():
    global _ENCODER, _ENCODER_PROBED
    if _ENCODER_PROBED:
        return _ENCODER
    _ENCODER_PROBED = True
    try:
        tiktoken = importlib.import_module("tiktoken")
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _ENCODER = None
    return _ENCODER


def count_tokens(text: str) -> int:
    if not text:
        return 0
    enc = _probe_tiktoken()
    if enc is not None:
        return len(enc.encode(text))
    return _heuristic_count(text)


def _heuristic_count(text: str) -> int:
    matches = _WORD_RE.findall(text)
    base = len(matches)
    floor = len(text) // 6
    return max(base, floor)


def token_savings(before: str, after: str) -> tuple[int, int, float]:
    tb = count_tokens(before)
    ta = count_tokens(after)
    pct = ((tb - ta) / tb * 100.0) if tb > 0 else 0.0
    return tb, ta, pct


if __name__ == "__main__":
    import sys

    blob = sys.stdin.read()
    print(f"{count_tokens(blob)} tokens")
