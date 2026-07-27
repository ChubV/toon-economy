# ToonEconomy

A Claude Code plugin that rewrites JSON tool output as **TOON** (Token-Oriented
Object Notation) to shrink the model's context window, then reports how many
tokens it saved in the Claude Code interface.

On a realistic 830-character API-status payload (see `examples/sample.json`),
TOON cuts the token count by **~53%** (298 → 139 tokens). Savings are highest
on repeated-shape data — lists of records, API responses, config dumps.

## How it works

The plugin registers a single **PostToolUse** hook. After every successful
tool call, the hook:

1. Reads the tool's response from stdin (Claude Code passes the full
   PostToolUse payload as JSON).
2. Walks the response looking for any string field (or string-typed top-level
   response) that parses as a JSON object or array.
3. Re-serializes that JSON as TOON.
4. **Only swaps it in when TOON is strictly smaller in tokens** (skips tiny
   objects where length-declaration overhead would dominate).
5. Returns the rewritten response via `hookSpecificOutput.updatedToolOutput`
   so the model reads the TOON form, not the JSON.
6. Emits `systemMessage` so the user sees `ToonEconomy: converted N fields
   to TOON, ~X tokens saved (Y%)` in the interface, plus a short
   `additionalContext` note telling the model what TOON is and how to read it.

Non-JSON output is rejected by a cheap first-character check (must start with
`{` or `[`) and never pays the `json.loads` cost. File contents, grep results,
and other plain text pass through untouched in microseconds.

## Repository layout

```
toon-economy/
  .claude-plugin/plugin.json   # plugin manifest (marketplace format)
  hooks/hooks.json             # registers the PostToolUse hook
  commands/
    toon-economy-stats.md      # the /toon-economy-stats slash command
  scripts/
    toon_converter.py          # JSON -> TOON serializer (standalone, reusable)
    token_counter.py           # tiktoken with graceful heuristic fallback
    toon_hook.py               # the hook itself; reads stdin, emits decision JSON
    stats.py                   # lifetime savings accumulator & reporter
  tests/
    test_converter.py          # 47 unit tests; runs with plain python3, no deps
    test_stats.py              # 26 unit tests for stats accumulation
  examples/
    sample.json                # realistic API-status payload
    sample.toon                # what the converter turns it into
  KNOWLEDGE.md                 # TOON format reference
  DECISIONS.md                 # architectural rationale
```

## Slash command: `/toon-economy-stats`

The plugin ships a `/toon-economy-stats` command. Each conversion also writes
to a lifetime counter at `${CLAUDE_PLUGIN_DATA}/stats.json` (POSIX-locked to
survive parallel PostToolUse firings; advisory only, never blocks the hook).
The command runs the reporter read-only and shows:

- total tool calls with conversions
- total JSON fields converted
- total tokens saved (with before/after and average % reduction)
- per-tool breakdown, sorted by tokens saved

Example output:

```
ToonEconomy lifetime stats
==========================
  tool calls with conversions: 3
  JSON fields converted:       3
  tokens saved:                82
  tokens (before):             133
  tokens (after):              51
  avg reduction:               61.7%
  tracked since:               2026-06-27T13:26:57Z
  last updated:                2026-06-27T13:26:57Z

  By tool (sorted by tokens saved):
    Bash                              calls=   2  fields=   2  saved=     59
    mcp__api__query                   calls=   1  fields=   1  saved=     23
```

You can also run the reporter directly: `python3 scripts/stats.py show`
(or `json`, `path`, `reset --yes`).

## Install

### From a local checkout

1. Make sure `python3` is on `PATH` (the hook is invoked as
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/toon_hook.py`).
2. (Optional, for accurate counts) `pip install tiktoken`. Without it, the
   plugin falls back to a ~10%-accurate heuristic — fine for the "saved ~N
   tokens" message, not for billing.
3. Add the plugin from the project directory:

   ```bash
   claude --plugin-dir /path/to/plugin/toon-economy
   ```

   or, in a session, `/plugin` → add the path above.

4. Restart Claude Code (or run `/hooks` to confirm the PostToolUse entry
   appears with source `[Plugin]`).

### Verify

After the next tool call that returns JSON, you should see a yellow
`ToonEconomy: ... tokens saved` line in the interface.

To smoke-test the converter from the shell:

```bash
echo '{"users":[{"id":1,"name":"Ada"},{"id":2,"name":"Bob"}]}' \
  | python3 scripts/toon_converter.py
```

Expected:

```
users[2]{id,name}:
1,Ada
2,Bob
```

To run the test suite:

```bash
python3 tests/test_converter.py
```

## Configuration

The hook fires on every PostToolUse by default. To narrow it (e.g. only MCP
tools, where JSON output is most common), edit `hooks/hooks.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "mcp__.*",
        "hooks": [ /* ... */ ]
      }
    ]
  }
}
```

Or override per-project in `.claude/settings.json` rather than editing the
plugin.

### Tunable constants

In `scripts/toon_hook.py`:

- `MAX_DEPTH` (default 4) — how deep to recurse into dict/list structures
  when searching for JSON strings. Higher finds more, costs more.
- `MAX_BYTES` (default 5 MB) — strings larger than this are skipped to keep
  the hook fast on large outputs.

## What TOON looks like

Object:

```
user:
  id: 123
  name: Ada
  roles[2]: admin,ops
```

Uniform array of objects (tabular form — the big win for token economy):

```
users[2]{id,name,role}:
1,Alice,admin
2,Bob,user
```

Full format reference: see **KNOWLEDGE.md**. Architectural rationale (why
PostToolUse not PostToolBatch, why Python, why graceful fallbacks): see
**DECISIONS.md**.

## Limitations

- The converter is **one-way**. It targets the form an LLM reads; it does not
  ship a parser. A TOON string is still human-recoverable to JSON by hand.
- Strings that contain structural characters (`{`, `}`, `[`, `]`, `,`, `"`,
  or have leading/trailing whitespace) are quoted; strings that look like a
  number, `true`/`false`/`null`, are quoted too, so the round-trip preserves
  their string type.
- Non-uniform arrays (mixed shapes, nested object values) fall back to an
  indexed form rather than tabular, which saves less but loses nothing.
- The hook adds a few milliseconds of latency to every tool call. On
  non-JSON output this is dominated by the first-character check (microseconds).

## License

MIT. See plugin manifest.
