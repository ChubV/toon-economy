#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

import stats  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, cond, detail))


def with_tmp_dir(fn):
    tmp = Path(tempfile.mkdtemp(prefix="toon-stats-test-"))
    orig_data_dir = stats._data_dir
    stats._data_dir = lambda: tmp
    try:
        fn(stats)
    finally:
        stats._data_dir = orig_data_dir
        shutil.rmtree(tmp, ignore_errors=True)


def test_load_empty(_stats):
    s = _stats.load_stats()
    check("load on missing file returns empty record",
          s["calls"] == 0 and s["tokens_saved"] == 0 and s["by_tool"] == {},
          str(s))
    check("empty record has started_at",
          "started_at" in s and len(s["started_at"]) > 10)


def test_record_once(_stats):
    _stats.record_conversion("Bash", tokens_before=100, tokens_after=40, fields_converted=1)
    s = _stats.load_stats()
    check("single conversion increments calls", s["calls"] == 1, str(s))
    check("single conversion tracks tokens_saved", s["tokens_saved"] == 60, str(s))
    check("single conversion tracks tokens_before", s["tokens_before"] == 100, str(s))
    check("single conversion tracks tokens_after", s["tokens_after"] == 40, str(s))
    check("single conversion records by_tool entry",
          s["by_tool"].get("Bash", {}).get("calls") == 1, str(s))


def test_record_many(_stats):
    for tool, b, a in [("Bash", 100, 40), ("Bash", 200, 80), ("mcp__api__q", 50, 20)]:
        _stats.record_conversion(tool, b, a, fields_converted=1)
    s = _stats.load_stats()
    check("multiple conversions sum calls", s["calls"] == 3, str(s))
    check("multiple conversions sum tokens_saved", s["tokens_saved"] == 210, str(s))
    check("by_tool groups by tool name",
          s["by_tool"]["Bash"]["calls"] == 2 and s["by_tool"]["Bash"]["tokens_saved"] == 180,
          str(s.get("by_tool")))
    check("by_tool keeps separate tools",
          s["by_tool"]["mcp__api__q"]["calls"] == 1, str(s))


def test_record_unknown_tool(_stats):
    _stats.record_conversion("", 10, 5, fields_converted=1)
    s = _stats.load_stats()
    check("empty tool name bucketed as <unknown>",
          "<unknown>" in s["by_tool"], str(s.get("by_tool")))


def test_reset(_stats):
    _stats.record_conversion("Bash", 100, 40, fields_converted=1)
    rc = _stats.main(["reset", "--yes"])
    check("reset --yes exits 0", rc == 0)
    s = _stats.load_stats()
    check("reset clears calls", s["calls"] == 0, str(s))
    check("reset clears by_tool", s["by_tool"] == {}, str(s))


def test_reset_requires_confirm(_stats):
    rc = _stats.main(["reset"])
    check("reset without --yes exits non-zero", rc != 0)


def test_format_does_not_crash_on_empty(_stats):
    out = _stats.format_stats(_stats.load_stats())
    check("format on empty stats returns header",
          "ToonEconomy lifetime stats" in out and "tokens saved:                0" in out,
          out)


def test_format_shows_by_tool(_stats):
    _stats.record_conversion("Bash", 100, 40, fields_converted=1)
    _stats.record_conversion("mcp__api__q", 200, 80, fields_converted=2)
    out = _stats.format_stats(_stats.load_stats())
    check("format includes By tool section", "By tool" in out, out)
    check("format lists each tool", "Bash" in out and "mcp__api__q" in out, out)
    check("format reports aggregate tokens_saved",
          "tokens saved:                180" in out, out)


def test_main_show_and_json(_stats):
    _stats.record_conversion("Bash", 100, 40, fields_converted=1)
    # Capture stdout
    import io
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        _stats.main(["show"])
        show_out = buf.getvalue()
    finally:
        sys.stdout = old
    check("main show prints formatted stats", "ToonEconomy lifetime stats" in show_out, show_out)

    buf = io.StringIO()
    sys.stdout = buf
    try:
        _stats.main(["json"])
        json_out = buf.getvalue()
    finally:
        sys.stdout = old
    parsed = json.loads(json_out)
    check("main json prints valid JSON with calls field",
          isinstance(parsed, dict) and parsed.get("calls") == 1, json_out)


def test_persistence_across_load(_stats):
    _stats.record_conversion("Bash", 100, 40, fields_converted=1)
    s1 = _stats.load_stats()
    s2 = _stats.load_stats()
    check("stats persist across loads", s1 == s2, f"{s1} vs {s2}")


def test_hook_integration_accumulates():
    tmp = Path(tempfile.mkdtemp(prefix="toon-stats-hook-"))
    orig_data_dir = stats._data_dir
    stats._data_dir = lambda: tmp
    try:
        import toon_hook
        payload_a = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_response": {
                "stdout": '{"users":[{"id":1,"name":"Alice"},{"id":2,"name":"Bob"}]}',
                "stderr": "", "interrupted": False, "isImage": False,
            },
        }
        payload_b = {
            "hook_event_name": "PostToolUse",
            "tool_name": "mcp__api__query",
            "tool_response": [
                {"type": "text", "text": '{"hits":[{"id":1,"name":"Ada"}]}'}
            ],
        }
        toon_hook.process_hook(payload_a)
        toon_hook.process_hook(payload_b)
        s = stats.load_stats()
        check("hook integration: two conversions recorded", s["calls"] == 2, str(s))
        check("hook integration: both tools tracked",
              "Bash" in s["by_tool"] and "mcp__api__query" in s["by_tool"], str(s["by_tool"]))
        check("hook integration: tokens_saved is positive",
              s["tokens_saved"] > 0, str(s))
    finally:
        stats._data_dir = orig_data_dir
        shutil.rmtree(tmp, ignore_errors=True)


for fn in [
    test_load_empty,
    test_record_once,
    test_record_many,
    test_record_unknown_tool,
    test_reset,
    test_reset_requires_confirm,
    test_format_does_not_crash_on_empty,
    test_format_shows_by_tool,
    test_main_show_and_json,
    test_persistence_across_load,
    test_hook_integration_accumulates,
]:
    if fn is test_hook_integration_accumulates:
        fn()
    else:
        with_tmp_dir(fn)

passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
for name, ok, detail in results:
    if not ok:
        print(f"  FAIL: {name}" + (f" — {detail}" if detail else ""))
print(f"\n{passed}/{len(results)} passed, {failed} failed.")
sys.exit(1 if failed else 0)
