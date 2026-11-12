# Vendored: Intentionality Engine

- Upstream: <https://github.com/lilbihhh/intentional-architecture>
- Pinned commit: `8035e2befd93d2f10947e708fc4a021cb1393c5a` (`main`, version 1.1.0 Production Candidate)
- License: MIT — see [`LICENSE`](LICENSE). Upstream also offers a separate commercial license.

## What was copied
| Vendored path | Upstream path |
| --- | --- |
| `metrics.py` | `src/metrics.py` |
| `regimes.py` | `src/regimes.py` |
| `policy_graph.py` | `langgraph/policy_graph.py` |
| `verify_audit.py` | `scripts/verify_audit.py` |
| `schemas/audit-log.schema.json` | `schemas/audit-log.schema.json` |
| `calibration/config.json` | `calibration/config.json` |
| `calibration/sequences.json` | `calibration/sequences.json` |

## Local edits (kept minimal)
- Imports are package-relative (`from .metrics import ...` instead of
  `from src.metrics import ...`) and the `sys.path` bootstrap was dropped.
- `DEFAULT_LEDGER` is configurable through the `NEXUS_LEDGER` environment
  variable; it defaults to the package directory.
- `SCHEMA_PATH` resolves inside this package instead of the repo root.

No policy, metric, regime or schema logic was modified. To update, re-copy the
upstream files at a new pinned commit and re-apply those three edits.

## Scope and safety
This is an auditable software simulation only. There is no neural input,
hardware interface, stimulation parameter or actuator command. It is not a
medical device, treatment, clinical protocol or validated BCI, and makes no
clinical efficacy or safety claims. All calibration data is synthetic and every
proposal is advisory.
