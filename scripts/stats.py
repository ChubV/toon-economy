#!/usr/bin/env python3
"""Lifetime stats accumulation and reporting for ToonEconomy.

Stats live at `${CLAUDE_PLUGIN_DATA}/stats.json`.

CLI:
  python3 stats.py show              # pretty-print lifetime stats (default)
  python3 stats.py json              # raw JSON to stdout
  python3 stats.py reset --yes       # zero out the stats (confirmation required)
  python3 stats.py path              # print the resolved stats file path
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:
    fcntl = None  # Windows: locking is best-effort skipped

STATS_FILENAME = "stats.json"


def _data_dir() -> Path:
    """Resolve the plugin's persistent data directory. Honors
    $CLAUDE_PLUGIN_DATA (set by Claude Code for plugin hooks); falls back to a
    local `data/` dir next to the plugin so the script is runnable standalone
    for tests and demos."""
    env = os.environ.get("CLAUDE_PLUGIN_DATA")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "data"


def stats_path() -> Path:
    return _data_dir() / STATS_FILENAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _empty_stats() -> dict[str, Any]:
    now = _now_iso()
    return {
        "version": 1,
        "started_at": now,
        "updated_at": now,
        "calls": 0,
        "fields": 0,
        "tokens_before": 0,
        "tokens_after": 0,
        "tokens_saved": 0,
        "by_tool": {},
    }


def _empty_tool_entry() -> dict[str, int]:
    return {"calls": 0, "fields": 0, "tokens_before": 0, "tokens_after": 0, "tokens_saved": 0}


def _lock(fd) -> None:
    if fcntl is None:
        return
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
    except OSError:
        pass


def _unlock(fd) -> None:
    if fcntl is None:
        return
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def load_stats() -> dict[str, Any]:
    p = stats_path()
    if not p.exists():
        return _empty_stats()
    try:
        with p.open() as f:
            data = json.load(f)
        return data if isinstance(data, dict) else _empty_stats()
    except (json.JSONDecodeError, OSError):
        return _empty_stats()


def save_stats(stats: dict[str, Any]) -> None:
    p = stats_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with tmp.open("w") as f:
        json.dump(stats, f, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def record_conversion(
    tool_name: str,
    tokens_before: int,
    tokens_after: int,
    fields_converted: int = 1,
) -> None:
    try:
        p = stats_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a+") as f:
            _lock(f)
            try:
                f.seek(0)
                content = f.read()
                stats = json.loads(content) if content.strip() else _empty_stats()
            except (json.JSONDecodeError, ValueError):
                stats = _empty_stats()

            saved = tokens_before - tokens_after
            stats["calls"] = int(stats.get("calls", 0)) + 1
            stats["fields"] = int(stats.get("fields", 0)) + fields_converted
            stats["tokens_before"] = int(stats.get("tokens_before", 0)) + tokens_before
            stats["tokens_after"] = int(stats.get("tokens_after", 0)) + tokens_after
            stats["tokens_saved"] = int(stats.get("tokens_saved", 0)) + saved
            stats["updated_at"] = _now_iso()
            stats.setdefault("started_at", _now_iso())

            by_tool = stats.setdefault("by_tool", {})
            entry = by_tool.setdefault(tool_name or "<unknown>", _empty_tool_entry())
            entry["calls"] = int(entry.get("calls", 0)) + 1
            entry["fields"] = int(entry.get("fields", 0)) + fields_converted
            entry["tokens_before"] = int(entry.get("tokens_before", 0)) + tokens_before
            entry["tokens_after"] = int(entry.get("tokens_after", 0)) + tokens_after
            entry["tokens_saved"] = int(entry.get("tokens_saved", 0)) + saved

            f.seek(0)
            f.truncate()
            json.dump(stats, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        # Stats are advisory; never propagate to the hook caller.
        pass


def format_stats(stats: dict[str, Any]) -> str:
    calls = int(stats.get("calls", 0))
    fields = int(stats.get("fields", 0))
    saved = int(stats.get("tokens_saved", 0))
    before = int(stats.get("tokens_before", 0))
    after = int(stats.get("tokens_after", 0))
    pct = (saved / before * 100.0) if before else 0.0
    started = stats.get("started_at", "?")
    updated = stats.get("updated_at", "?")

    lines = [
        "ToonEconomy lifetime stats",
        "==========================",
        f"  tool calls with conversions: {calls}",
        f"  JSON fields converted:       {fields}",
        f"  tokens saved:                {saved}",
        f"  tokens (before):             {before}",
        f"  tokens (after):              {after}",
        f"  avg reduction:               {pct:.1f}%",
        f"  tracked since:               {started}",
        f"  last updated:                {updated}",
    ]

    by_tool = stats.get("by_tool") or {}
    if by_tool:
        lines.append("")
        lines.append("  By tool (sorted by tokens saved):")
        ordered = sorted(
            by_tool.items(),
            key=lambda kv: -int(kv[1].get("tokens_saved", 0)),
        )
        for tool, entry in ordered:
            lines.append(
                f"    {tool:<32}  calls={int(entry.get('calls', 0)):>4}  "
                f"fields={int(entry.get('fields', 0)):>4}  "
                f"saved={int(entry.get('tokens_saved', 0)):>7}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "show"

    if cmd == "show":
        print(format_stats(load_stats()))
        return 0
    if cmd == "json":
        print(json.dumps(load_stats(), indent=2, sort_keys=True))
        return 0
    if cmd == "path":
        print(stats_path())
        return 0
    if cmd == "reset":
        if "--yes" not in argv:
            print("reset requires --yes to confirm", file=sys.stderr)
            return 1
        save_stats(_empty_stats())
        print("stats reset")
        return 0

    print(f"unknown command: {cmd}", file=sys.stderr)
    print("usage: stats.py [show|json|reset --yes|path]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
