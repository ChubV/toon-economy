#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from toon_converter import json_to_toon  # noqa: E402
from token_counter import token_savings  # noqa: E402
from stats import record_conversion  # noqa: E402

MAX_DEPTH = 4
MAX_BYTES = 5 * 1024 * 1024  # 5 MB cap per string; TOON conversion is O(n) but no need to be heroic

MODEL_NOTE = (
    "JSON outputs from the tool calls were "
    "rewritten to TOON (indent-based JSON alternative). "
    "TOON reads like indented key:value pairs with CSV-style rows; "
    "interpret it as the equivalent JSON."
)


def _is_json_struct(s: str) -> bool:
    if not s or len(s) > MAX_BYTES:
        return False
    stripped = s.lstrip()
    if not stripped or stripped[0] not in "[{":
        return False
    try:
        json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return False
    return True


def _replace_json_strings(
    value: Any, depth: int = 0
) -> tuple[Any, int, int, int]:
    if isinstance(value, str):
        if _is_json_struct(value):
            try:
                toon = json_to_toon(value)
            except Exception:
                return value, 0, 0, 0
            before, after, _ = token_savings(value, toon)
            if after < before:
                return toon, before, after, 1
        return value, 0, 0, 0

    if depth >= MAX_DEPTH:
        return value, 0, 0, 0

    if isinstance(value, dict):
        new: dict = {}
        tb_total = ta_total = count = 0
        for k, v in value.items():
            nv, tb, ta, c = _replace_json_strings(v, depth + 1)
            new[k] = nv
            tb_total += tb
            ta_total += ta
            count += c
        return new, tb_total, ta_total, count

    if isinstance(value, list):
        new_list: list = []
        tb_total = ta_total = count = 0
        for v in value:
            nv, tb, ta, c = _replace_json_strings(v, depth + 1)
            new_list.append(nv)
            tb_total += tb
            ta_total += ta
            count += c
        return new_list, tb_total, ta_total, count

    return value, 0, 0, 0


def process_hook(input_obj: dict) -> dict | None:
    tool_response = input_obj.get("tool_response")
    if tool_response is None:
        return None

    new_response, before, after, count = _replace_json_strings(tool_response)
    if count == 0:
        return None

    saved = before - after
    if saved <= 0:
        return None

    pct = (saved / before * 100.0) if before else 0.0
    field_word = "field" if count == 1 else "fields"
    system_message = (
        f"ToonEconomy: converted {count} JSON {field_word} to TOON, "
        f"~{saved} tokens saved ({pct:.0f}% of {before})."
    )

    tool_name = input_obj.get("tool_name") or "<unknown>"
    record_conversion(tool_name, before, after, fields_converted=count)

    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": MODEL_NOTE,
            "updatedToolOutput": new_response,
        },
        "systemMessage": system_message,
    }


def main() -> int:
    raw = sys.stdin.read()
    if not raw:
        return 0
    try:
        input_obj = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Malformed input — nothing to do, let Claude Code proceed normally.
        return 0

    try:
        output = process_hook(input_obj)
    except Exception as e:
        # Never break the user's session over a token-economy nicety. Log to
        # stderr (visible in --debug) and bail.
        print(f"toon-economy: {e}", file=sys.stderr)
        return 0

    if output is None:
        return 0

    sys.stdout.write(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
