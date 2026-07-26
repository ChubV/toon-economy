# TOON format reference (as implemented by ToonEconomy)

TOON — **Token-Oriented Object Notation** — is a compact, indentation-based
alternative to JSON designed so LLMs consume fewer tokens reading the same
data. The format trades parser simplicity (no streaming parser here) for
readability and density. This document is the reference for the variant
ToonEconomy emits; the canonical spec is TOON v3.0.

## Goals (in priority order)

1. **Fewer tokens than JSON** for typical structured data. Tabular arrays are
   the big win — a 100-row array of records collapses from one object literal
   per row to one CSV-style row per record.
2. **Unambiguous to a human or model reading it.** No sigils that need a
   legend; field names appear once in a header rather than repeated on every
   row.
3. **Faithful** to the source JSON. Any JSON value can be serialized; types
   are preserved by quoting when needed.

Non-goals: streaming parse, schema validation, comments.

## Lexical rules

### Indentation

Two spaces per level (default; configurable via `INDENT` / the `indent=` kwarg).
Children of a `key:` are indented one level deeper than the key. Tabular rows
align with their declaring key (no extra indent), matching the canonical spec
example.

### Delimiter

Comma (default; configurable via `DELIM` / `delim=` kwarg). Tabular cells and
inline primitive arrays are joined by it. The TOON spec also permits tab or
pipe; this implementation emits commas only.

### Scalars

| JSON value     | TOON form            | Notes                                            |
|----------------|----------------------|--------------------------------------------------|
| `null`         | `null`               | bare keyword                                     |
| `true`/`false` | `true` / `false`     | bare keyword                                     |
| `42`           | `42`                 | int unchanged                                    |
| `-7`           | `-7`                 | negative int unchanged                           |
| `3.0`          | `3`                  | integer-valued float drops `.0`                  |
| `0.75`         | `0.75`               | fractional float, no trailing zeros              |
| `"hello"`      | `hello`              | bareword when safe                               |
| `"a,b"`        | `"a,b"`              | quoted (contains delimiter)                      |
| `""`           | `""`                 | quoted (empty string)                            |
| `" leading"`   | `" leading"`         | quoted (leading whitespace)                      |
| `"42"`         | `"42"`               | quoted (would otherwise parse as a number)       |
| `"true"`       | `"true"`             | quoted (would otherwise parse as bool)           |
| `'a"b'`        | `"a""b"`             | quote escaped by doubling                        |

**Quoting trigger.** A string is quoted iff any of:
- it is empty;
- it has leading or trailing whitespace;
- it contains any of `, " [ ] { }`;
- it matches the regex for a typed scalar (`true|false|null|-?\d+(\.\d+)?([eE][+-]?\d+)?`).

This last rule preserves string-ness: `"42"` round-trips as a string, not an
int.

### Numbers

`nan`, `inf`, `-inf` are emitted as barewords (TOON has no NaN literal). These
can only arise from `json.loads` if `parse_constant` is hooked; standard JSON
does not produce them.

## Structural forms

### Object

```
key:
  child1: value
  child2:
    grandchild: value
```

Empty object: `key: {}`. Top-level empty object: `{}`.

### Primitive array (one line)

```
tags[3]: admin,ops,dev
```

The `[3]` is a length declaration. Empty primitive array: `tags[0]:`.

### Tabular array (array of uniform, flat objects)

When every element is a dict with the same keys in the same order and every
value is scalar, TOON emits a header row plus one CSV row per element:

```
users[2]{id,name,role}:
1,Alice,admin
2,Bob,user
```

The header `{id,name,role}` declares field order. Length `[2]` documents the
row count. Rows align with the declaring key's indent (no extra level).

This is where the token savings come from. JSON would repeat `{"id":...,"name":...,"role":...}`
per row; TOON states the schema once and emits just the values.

### Fallback: non-uniform or nested array

If elements have differing keys, or any value is itself a dict or list, the
converter falls back to an indexed form so no information is lost:

```
items[3]:
  0:
    id: 1
    meta:
      kind: widget
  1:
    id: 2
    meta:
      kind: gadget
      color: red
  2: skip
```

Index keys are `0`, `1`, `2`, … (valid TOON bareword keys).

### Top-level value

A top-level object, array, or scalar is emitted directly. Top-level arrays use
the same form as keyed arrays but without a key prefix:

```
[2]{id,name}:
1,Alice
2,Bob
```

Top-level scalar: just the scalar on one line.

## Quoting worked example

Source JSON:

```json
{"path": "/items/{id}", "label": "items, by id", "count": "3"}
```

TOON output:

```
path: "/items/{id}"
label: "items, by id"
count: "3"
```

- `/items/{id}` is quoted because of `{` and `}`.
- `items, by id` is quoted because of `,` and the spaces would be ambiguous.
- `3` is quoted because the source was the string `"3"`, not the number `3`.

## What this implementation does NOT do

- **Parse TOON back to JSON.** One-way only; the model reads TOON, never writes
  it. If you need a parser, the canonical spec defines an ABNF grammar.
- **Stream.** The whole input is materialized.
- **Comments.** None emitted, none parsed.
- **Alternate delimiters.** Only comma is emitted (spec also allows tab/pipe).

## Measured savings

On `examples/sample.json` (a realistic API-status payload with nested arrays
of records): JSON 298 tokens, TOON 139 tokens, **53.4% reduction**.

Savings scale with how tabular the data is. Pure key-value objects save less
(20–30%); long arrays of uniform records save the most (50–70%).

## References

- TOON v3.0 spec: https://github.com/toon-format/spec/blob/main/SPEC.md
- Original benchmarks cited by the spec: ~40% token reduction over JSON with
  76.4% model accuracy vs JSON's 75.0% (i.e. no measurable accuracy cost).
