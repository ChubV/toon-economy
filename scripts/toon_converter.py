#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from typing import Any, Iterable

INDENT = "  "        # two spaces; the TOON default
DELIM = ","          # CSV-style cell delimiter

# Characters that force a string to be quoted (delimiter, structural punctuation,
# any whitespace, quote char). Whitespace anywhere inside also forces quoting
# so values can never accidentally span rows.
_STRUCTURAL_RE = re.compile(r'[,"\[\]{}]')
_NUMERIC_OR_KEYWORD_RE = re.compile(
    r"^(?:true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)$"
)


def _needs_quote(s: str) -> bool:
    if s == "":
        return True
    if s != s.strip():
        return True
    if _STRUCTURAL_RE.search(s):
        return True
    if _NUMERIC_OR_KEYWORD_RE.match(s):
        return True
    return False


def _quote(s: str) -> str:
    if not _needs_quote(s):
        return s
    return '"' + s.replace('"', '""') + '"'


def _format_number(n) -> str:
    if isinstance(n, bool):
        return "true" if n else "false"
    if isinstance(n, int):
        return str(n)
    if isinstance(n, float):
        if n != n:        # NaN
            return "nan"
        if n in (float("inf"), float("-inf")):
            return "inf" if n > 0 else "-inf"
        if n.is_integer():
            return str(int(n))
        return repr(n)
    return str(n)


def _format_scalar(v: Any) -> str:
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return _format_number(v)
    return _quote(str(v))


def _is_scalar(v: Any) -> bool:
    return v is None or isinstance(v, (bool, int, float, str))


def _is_uniform_object_array(arr: list) -> tuple[bool, list[str] | None]:
    if not arr or not all(isinstance(x, dict) for x in arr):
        return False, None
    keys = list(arr[0].keys())
    if not keys:
        return False, None
    for x in arr:
        if list(x.keys()) != keys:
            return False, None
        if not all(_is_scalar(v) for v in x.values()):
            return False, None
    return True, keys


def _is_primitive_array(arr: list) -> bool:
    return bool(arr) and all(_is_scalar(x) for x in arr)


def _emit_value(
    lines: list[str],
    key: str | None,
    value: Any,
    indent_level: int,
    indent: str,
    delim: str,
) -> None:
    pad = indent * indent_level

    if isinstance(value, dict):
        if not value:
            lines.append(f"{pad}{key}: {{}}" if key is not None else "{}")
            return
        if key is not None:
            lines.append(f"{pad}{key}:")
        child_indent = indent_level + (1 if key is not None else 0)
        for k, v in value.items():
            _emit_value(lines, str(k), v, child_indent, indent, delim)
        return

    if isinstance(value, list):
        _emit_array(lines, key, value, indent_level, indent, delim)
        return

    if key is not None:
        lines.append(f"{pad}{key}: {_format_scalar(value)}")
    else:
        lines.append(f"{pad}{_format_scalar(value)}")


def _emit_array(
    lines: list[str],
    key: str | None,
    arr: list,
    indent_level: int,
    indent: str,
    delim: str,
) -> None:
    pad = indent * indent_level
    n = len(arr)
    key_prefix = f"{pad}{key}" if key is not None else pad
    # top-level array uses a bare [N] prefix; keyed arrays use key[N].
    length_token = f"[{n}]"

    if n == 0:
        suffix = f"{length_token}:" if key is not None else f"{length_token}"
        lines.append(f"{key_prefix}{suffix}")
        return

    uniform, fields = _is_uniform_object_array(arr)
    if uniform and fields is not None:
        header = "{" + ",".join(fields) + "}"
        lines.append(f"{key_prefix}{length_token}{header}:")
        for row in arr:
            cells = delim.join(_format_scalar(row[f]) for f in fields)
            lines.append(f"{pad}{cells}")
        return

    if _is_primitive_array(arr):
        cells = delim.join(_format_scalar(x) for x in arr)
        lines.append(f"{key_prefix}{length_token}: {cells}")
        return

    # Fallback: non-uniform or nested array. Emit the length declaration,
    # then each element as an indexed child so structure is preserved.
    lines.append(f"{key_prefix}{length_token}:")
    for i, x in enumerate(arr):
        _emit_value(lines, str(i), x, indent_level + 1, indent, delim)


def to_toon(
    value: Any,
    *,
    indent: str = INDENT,
    delim: str = DELIM,
) -> str:
    """Serialize a JSON-compatible Python value to TOON text.

    Args:
        value: anything json.load() could return: dict, list, str, int, float,
            bool, None.
        indent: indentation unit per nesting level (default two spaces).
        delim: cell delimiter for tabular and primitive arrays (default comma).

    Returns:
        TOON text, newline-terminated lines joined with "\\n". No trailing
        newline.
    """
    lines: list[str] = []
    _emit_value(lines, None, value, 0, indent, delim)
    return "\n".join(lines)


def json_to_toon(
    json_text: str,
    *,
    indent: str = INDENT,
    delim: str = DELIM,
) -> str:
    """Parse a JSON string and re-serialize it as TOON.

    Raises json.JSONDecodeError if the input is not valid JSON.
    """
    return to_toon(json.loads(json_text), indent=indent, delim=delim)


def looks_like_json(text: str) -> bool:
    if not text:
        return False
    stripped = text.lstrip()
    if not stripped:
        return False
    if stripped[0] not in '{[ "-0123456789tfn':
        return False

    try:
        json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return False
    return True


if __name__ == "__main__":
    import sys

    data = sys.stdin.read()
    if not data:
        print("usage: toon_converter.py < input.json", file=sys.stderr)
        sys.exit(2)
    try:
        print(json_to_toon(data))
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
