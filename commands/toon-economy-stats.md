---
description: Show lifetime TOON token savings accumulated by ToonEconomy
---

Display ToonEconomy's lifetime savings by running its stats reporter script,
then show the output verbatim to the user.

Steps:

1. Locate the ToonEconomy plugin directory. Try `$CLAUDE_PLUGIN_ROOT` first;
   if it is unset or does not contain `scripts/stats.py`, fall back to Glob
   for `**/toon-economy/scripts/stats.py` (or find the nearest ancestor
   directory containing `.claude-plugin/plugin.json` with `name: "toon-economy"`).
2. Run the reporter read-only:

   ```bash
   python3 "<plugin_dir>/scripts/stats.py" show
   ```

3. Print the script's stdout verbatim to the user.

Do not modify any files. This is read-only reporting. If the script prints
zeroes everywhere, that means the hook has not converted any JSON yet this
session lifetime — say so plainly.
