---
description: Show lifetime TOON token savings accumulated by ToonEconomy
---

Display ToonEconomy's lifetime savings by running its stats reporter script,
then show the output verbatim to the user.

Steps:

1. Locate the ToonEconomy plugin directory (`toon-economy`). 
2. Run the reporter read-only:

   ```bash
   python3 "<plugin_dir>/scripts/stats.py" show
   ```

3. Print the script's stdout verbatim to the user.

Do not modify any files. This is read-only reporting. If the script prints
zeroes everywhere, that means the hook has not converted any JSON yet this
session lifetime — say so plainly.
