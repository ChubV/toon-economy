# Architectural decisions

The choices that shaped ToonEconomy, with the reasoning so every1
can judge whether they still apply.

## 1. PostToolUse, not PostToolBatch

**Decision.** Register on `PostToolUse` only.

**Why.** The Claude Code hook protocol distinguishes the two events:

- `PostToolUse` fires once per tool call and **can rewrite the tool's output**
  via `hookSpecificOutput.updatedToolOutput`. The replacement reaches the
  model in place of the original.
- `PostToolBatch` fires once per batch of parallel tool calls and **can only
  inject `additionalContext`**, not replace outputs.

The whole point of ToonEconomy is to replace the JSON the model would
otherwise see with smaller TOON text. Only PostToolUse can do that. PostToolBatch
is a strict subset of capability for our use case.

**Cost.** PostToolUse fires concurrently when Claude makes parallel tool
calls — multiple hook processes can run at once. Each is independent
(stateless, no shared state), so this is fine.

**Trade-off accepted.** PostToolUse is on the hot path of every tool call,
adding a few milliseconds of latency even when no conversion happens. We keep
this cost tiny by bailing on a first-character check (must be `{` or `[`)
before paying for `json.loads`.

## 2. `updatedToolOutput` over `additionalContext`

**Decision.** Replace the tool output entirely (`updatedToolOutput`). Use
`additionalContext` only for the brief "this was converted, here's how to read
TOON" note.

**Why.** The token saving only materializes if the original JSON never reaches
the model. `additionalContext` *adds* to context, it doesn't replace — using
it to deliver TOON alongside JSON would double the cost, not halve it.

**Constraint.** `updatedToolOutput` "must match the tool's output shape" per
the Claude Code docs. So we preserve the shape exactly: Bash stays a
`{stdout, stderr, interrupted, isImage}` dict, MCP content stays a list of
`{type, text}` blocks, Read stays a string. Only the JSON-bearing *contents*
are converted to TOON.

## 3. `systemMessage` for the savings notification

**Decision.** Surface `~N tokens saved (Y%)` via the universal `systemMessage`
field, not stderr, not `/dev/tty`, not a file.

**Why.** Per the Claude Code docs:
- Hooks run without a controlling terminal (as of v2.1.139). Writing to
  `/dev/tty` fails.
- Stderr from PostToolUse is shown to the *model*, not the user — wrong
  audience.
- `systemMessage` is a universal field that shows a warning to the *user* in
  the interface.

**Cost.** The message occupies one yellow line per tool call that converts.
For tools that don't return JSON, no message appears (the hook returns no
output and exits 0).

## 4. Python, not Node

**Decision.** Implement the hook in Python 3.

**Why.**
- `tiktoken` is Python-first.
- Python ships pre-installed on macOS and almost every Linux distro the user
  might run Claude Code on. `python3` on `PATH` is a reasonable assumption.
- The standard library alone (`json`, `re`, `sys`) is enough for the
  converter. Zero runtime dependencies when tiktoken is absent.

**Cost.** Adds a `python3` startup (~30–50 ms) to every tool call. For a
non-converting call, total hook time is well under 100 ms. Acceptable.

## 5. Graceful tiktoken fallback

**Decision.** `token_counter.py` tries `import tiktoken`; on any failure it
falls back to a word+punctuation heuristic.

**Why.** tiktoken is **not** installed in many Claude Code environments. The
plugin must not break the user's session over a missing optional dependency.
Both code paths produce an estimate good enough for the "saved ~N tokens"
display; exact counts are not load-bearing.

**Heuristic.** Count word-like and punctuation runs (`[A-Za-z0-9_]+|[^\sA-Za-z0-9_]`),
take `max(count, len/6)` as a floor. Stays within ~10% of cl100k_base on
prose and typical JSON.

**Switching cost.** When tiktoken is installed, the encoder is created once
and cached (`@lru_cache`). The probe runs at most once per process.

## 6. Only swap when TOON is strictly smaller

**Decision.** After conversion, compare token counts. Only emit
`updatedToolOutput` when the TOON form has strictly fewer tokens.

**Why.** Tiny JSON like `{}` or `{"a":1}` already has minimal overhead; the
TOON length declaration (`a[0]:`, `key:` headers) can actually be larger. We
measure both forms and keep whichever is smaller — the hook can never
*increase* the model's context.

## 7. Plugin format, not a settings.json hook

**Decision.** Ship as a marketplace-format plugin (`.claude-plugin/plugin.json`
+ `hooks/hooks.json`).

**Why.** Plugins are distributable, versioned, and self-contained. A
`settings.json` hook would require every user to hand-copy a command path
into their config. The plugin form lets users do `claude plugin add <path>`
and be done.

## 8. Non-blocking on any internal error

**Decision.** The hook script catches all exceptions, logs to stderr (visible
in `--debug`), and exits 0 with no output.

**Why.** A hook that crashes the user's session over a token-economy nicety
is hostile. The worst case we accept is "no conversion happened this turn";
the worst case we refuse is "the user's session broke."

## 9. Lifetime stats persisted to `${CLAUDE_PLUGIN_DATA}`

**Decision.** Every successful conversion appends to a counter at
`${CLAUDE_PLUGIN_DATA}/stats.json`. A `/toon-economy-stats` slash command
reads it via `scripts/stats.py show` and renders a per-tool breakdown.

**Why.** Per-call `systemMessage` shows one turn's savings; users also want
to know whether the plugin is paying off over a session, week, or project
lifetime. Persisting lets the slash command answer that without re-deriving
it from the transcript.

**Concurrency.** PostToolUse hooks fire in parallel when Claude makes
parallel tool calls. The accumulator does a read-modify-write under
`fcntl.flock(LOCK_EX)` on POSIX, so concurrent writers serialize. On Windows
`fcntl` is unavailable and the lock is skipped — a rare race may lose one
increment, which is fine for an advisory counter.

**Why `CLAUDE_PLUGIN_DATA`.** It is the documented plugin-persistent dir
that survives plugin updates, distinct from `CLAUDE_PLUGIN_ROOT` (which is
replaced on update). Putting stats there means upgrading the plugin keeps
the user's totals.

**Failure isolation.** `record_conversion` swallows all exceptions. Stats
are advisory: if the data dir is unwritable or the JSON corrupt, the hook
still returns its primary output to Claude Code.

**Slash command form.** Plugin commands are markdown files in `commands/`
whose body becomes a prompt. `/toon-economy-stats` instructs Claude to
locate the plugin (via `$CLAUDE_PLUGIN_ROOT`, with a Glob fallback), run the
reporter read-only, and display its stdout verbatim. The command never
writes — `reset --yes` is a direct script invocation, not a command.

## Future work

- **A `--no-additional-context` mode** for users who don't want even the
  one-sentence model note eating tokens.
- Hook to report the saving. And/or OTel attribute to set when one is available in `gen_ai.*`
