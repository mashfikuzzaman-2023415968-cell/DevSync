# DAST (ZAP) configuration

`make zap` and gate step 17 run ZAP's passive scan of the test stack, signed in as a seeded
developer (`backend/scripts/zap_scan.py`, DECISIONS D157 and D171). Any High or Medium alert
fails the step.

`ignore.json` lists alerts that are false positives, as `[{"pluginid": "10020", "decision":
"D180"}]`. Each entry must name a DECISIONS entry that exists and explains why the alert is a
false positive. The script refuses any entry that doesn't. Never use this file to silence a real
finding, or to relax a header or a security default: fix the cause instead.
