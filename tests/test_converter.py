#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

from toon_converter import to_toon, json_to_toon, looks_like_json  # noqa: E402
from token_counter import count_tokens, token_savings  # noqa: E402
import toon_hook  # noqa: E402


results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, cond, detail))


# --- Converter: scalars ---------------------------------------------------

check("null serializes",
      to_toon(None) == "null")
check("bool serializes",
      to_toon(True) == "true" and to_toon(False) == "false")
check("int serializes",
      to_toon(42) == "42")
check("negative int serializes",
      to_toon(-7) == "-7")
check("integer-valued float drops .0",
      to_toon(3.0) == "3")
check("fractional float keeps digits",
      to_toon(0.75) == "0.75")
check("plain string passes through",
      to_toon("hello") == "hello")
check("string with comma is quoted",
      to_toon("a,b") == '"a,b"')
check("empty string is quoted",
      to_toon("") == '""')
check("string with leading space is quoted",
      to_toon(" leading") == '" leading"')
check("string that looks like a number is quoted",
      to_toon("42") == '"42"')
check("string that looks like a bool is quoted",
      to_toon("true") == '"true"')
check("string with embedded quote escapes doubled",
      to_toon('a"b') == '"a""b"')


# --- Converter: objects ---------------------------------------------------

check("empty object becomes {}",
      to_toon({}) == "{}")
check("flat object serializes key: value lines",
      to_toon({"a": 1, "b": 2}) == "a: 1\nb: 2")
check("nested object indents children",
      to_toon({"outer": {"inner": 1}}) == "outer:\n  inner: 1")


# --- Converter: primitive arrays -----------------------------------------

check("empty array keeps length decl",
      to_toon([]) == "[0]")
check("primitive array collapses to one line",
      to_toon([1, 2, 3]) == "[3]: 1,2,3")
check("primitive array with strings uses quoting",
      to_toon(["a,b", "c"]) == '[2]: "a,b",c')


# --- Converter: object arrays (tabular) ----------------------------------

tabular = [
    {"id": 1, "name": "Alice", "role": "admin"},
    {"id": 2, "name": "Bob", "role": "user"},
]
expected_tabular = (
    "users[2]{id,name,role}:\n"
    "1,Alice,admin\n"
    "2,Bob,user"
)
check("uniform object array becomes tabular",
      to_toon({"users": tabular}) == expected_tabular, to_toon({"users": tabular}))

check("non-uniform array falls back to indexed form",
      to_toon({"items": [{"a": 1}, {"b": 2}]}) ==
      "items[2]:\n  0:\n    a: 1\n  1:\n    b: 2",
      to_toon({"items": [{"a": 1}, {"b": 2}]}))

check("array with nested object value falls back",
      to_toon({"items": [{"id": 1, "meta": {"k": "v"}}]}) ==
      "items[1]:\n  0:\n    id: 1\n    meta:\n      k: v",
      to_toon({"items": [{"id": 1, "meta": {"k": "v"}}]}))


# --- Converter: looks_like_json ------------------------------------------

check("looks_like_json accepts object",
      looks_like_json('{"a":1}') is True)
check("looks_like_json accepts array",
      looks_like_json('[1,2,3]') is True)
check("looks_like_json rejects prose",
      looks_like_json("hello world") is False)
check("looks_like_json rejects malformed",
      looks_like_json("{not json") is False)
check("looks_like_json rejects empty",
      looks_like_json("") is False)


# --- Token counter -------------------------------------------------------

check("count_tokens returns 0 on empty",
      count_tokens("") == 0)
check("count_tokens is positive on text",
      count_tokens("the quick brown fox") > 0)
check("count_tokens is monotonic-ish (longer text more tokens)",
      count_tokens("a") < count_tokens("a " * 1000))

before, after, pct = token_savings(
    '{"users":[{"id":1,"name":"Alice","role":"admin"},{"id":2,"name":"Bob","role":"user"}]}',
    json_to_toon('{"users":[{"id":1,"name":"Alice","role":"admin"},{"id":2,"name":"Bob","role":"user"}]}'),
)
check("TOON is smaller than JSON for tabular data",
      after < before,
      f"before={before} after={after} pct={pct:.1f}")
check("pct_savings reports a positive reduction",
      pct > 0,
      f"pct={pct:.1f}")


# --- Hook ----------------------------------------------------------------

def _hook_output(payload: dict) -> dict | None:
    return toon_hook.process_hook(payload)


bash_with_json = {
    "hook_event_name": "PostToolUse",
    "tool_name": "Bash",
    "tool_input": {"command": "cat data.json"},
    "tool_response": {
        "stdout": '{"users":[{"id":1,"name":"Alice"},{"id":2,"name":"Bob"}]}',
        "stderr": "",
        "interrupted": False,
        "isImage": False,
    },
}
out = _hook_output(bash_with_json)
check("hook converts Bash JSON stdout", out is not None)
if out:
    hso = out["hookSpecificOutput"]
    check("hook output preserves Bash shape",
          set(hso["updatedToolOutput"].keys()) == {"stdout", "stderr", "interrupted", "isImage"})
    check("hook output stdout is TOON (has tabular header)",
          "users[2]{id,name}:" in hso["updatedToolOutput"]["stdout"],
          hso["updatedToolOutput"]["stdout"])
    check("hook surfaces systemMessage",
          "ToonEconomy" in out["systemMessage"] and "saved" in out["systemMessage"])
    check("hook surfaces additionalContext for the model",
          "TOON" in hso["additionalContext"])

check("hook skips non-JSON string response",
      _hook_output({
          "tool_name": "Read",
          "tool_response": "     1\timport os\n",
      }) is None)

check("hook skips when tool_response missing",
      _hook_output({"tool_name": "Bash"}) is None)

check("hook skips tiny JSON that doesn't save tokens",
      _hook_output({
          "tool_name": "Bash",
          "tool_response": {"stdout": "{}", "stderr": "", "interrupted": False, "isImage": False},
      }) is None)

mcp = {
    "tool_name": "mcp__api__query",
    "tool_response": [
        {"type": "text", "text": '{"hits":[{"id":1,"name":"Ada"},{"id":2,"name":"Bob"}]}'}
    ],
}
out = _hook_output(mcp)
check("hook converts MCP content blocks", out is not None)
if out:
    block = out["hookSpecificOutput"]["updatedToolOutput"][0]
    check("MCP block text becomes TOON",
          "hits[2]{id,name}:" in block["text"], block["text"])

check("hook handles malformed stdin gracefully",
      toon_hook._replace_json_strings("not a dict") == ("not a dict", 0, 0, 0))


# --- Round-trip property: TOON preserves information ---------------------

# For each fixture, verify the TOON form is strictly smaller in tokens than
# the JSON form. We don't assert strict losslessness (no parser here), but
# smaller-or-equal token count is the load-bearing property for the plugin.
FIXTURES = [
    {"users": [{"id": i, "name": f"user{i}", "active": i % 2 == 0} for i in range(20)]},
    {"config": {"endpoint": "https://api.example.com", "timeout_ms": 30000, "retries": 3}},
    [1, 2, 3, "four", True, None],
    {"empty": [], "nested": {"deep": {"deeper": {"value": 42}}}},
]
for i, fx in enumerate(FIXTURES):
    j = json.dumps(fx)
    t = to_toon(fx)
    bj = count_tokens(j)
    bt = count_tokens(t)
    check(f"fixture {i}: TOON <= JSON in tokens", bt <= bj, f"json={bj} toon={bt}")


# --- Report --------------------------------------------------------------

passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
for name, ok, detail in results:
    if not ok:
        print(f"  FAIL: {name}" + (f" — {detail}" if detail else ""))
print(f"\n{passed}/{len(results)} passed, {failed} failed.")
sys.exit(1 if failed else 0)
