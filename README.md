# DreamWeaver N1

Turning sleep into deliberate creation.

Built by AleXus — The Architect.

DreamWeaver N1 is a Flask application for recording dream intentions, replaying animated dream scenes, running Targeted Memory Reactivation (TMR) sessions, and receiving streaming lucid-dreaming guidance from Grok.

## Features

- Persistent SQLite storage for multiple dreams and TMR sessions
- Dashboard with recent dreams and TMR activity
- Dream recording with CSS dreamscapes plus optional HTML5 video or GIF playback
- TMR start, cue logging, and completion workflow
- Streaming Grok Coach responses with lucid-dreaming-specific prompting
- Simulation section running the vendored Intentionality Engine policy graph over synthetic inputs, with an append-only, schema-validated NEXUS audit ledger
- Friendly validation, not-found, API configuration, and health-check responses
- Gunicorn, Procfile, Dockerfile, and environment-variable configuration
- Comprehensive pytest suite with per-module coverage reporting

## Local setup

Python 3.10+ is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Export the variables from `.env` (or configure them in your shell), then run:

```bash
flask --app app run --debug
```

Open `http://127.0.0.1:5000`.

## Configuration

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `GROK_API_KEY` | For Coach | — | Preferred xAI API key variable; never commit it |
| `XAI_API_KEY` | For Coach | — | Supported alias when `GROK_API_KEY` is unset |
| `GROK_API_URL` | No | `https://api.x.ai/v1/chat/completions` | Grok chat-completions endpoint |
| `GROK_MODEL` | No | `grok-4.5` | xAI model used by the coach |
| `DREAMWEAVER_DB` | No | `dreams.db` | SQLite database path |
| `DREAMWEAVER_NEXUS_LEDGER` | No | `/data/nexus_ledger.jsonl` when `/data` exists, else `nexus_ledger.jsonl` | JSONL NEXUS audit ledger path |
| `SECRET_KEY` | Production | `dev-secret-key` | Flask session signing key |
| `PORT` | Deployment | `5000` | HTTP port |

## Tests and coverage

```bash
pytest
```

`pytest.ini` enables coverage for both production modules and prints missing lines. To generate an HTML report:

```bash
pytest --cov-report=html
open htmlcov/index.html
```

## Railway deployment

1. Create a Railway project from this repository.
2. Add `GROK_API_KEY` and a strong random `SECRET_KEY` in **Variables**.
3. Attach a persistent volume and set `DREAMWEAVER_DB` to its mounted path, for example `/data/dreams.db`.
4. Railway detects the `Procfile` and starts Gunicorn. The platform supplies `PORT`.

Without a volume, SQLite data is lost when the container is replaced.

## Vultr deployment

Build and run the included Dockerfile, mounting persistent storage for SQLite:

```bash
docker build -t dreamweaver-n1 .
docker run -d --name dreamweaver \
  -p 5000:5000 \
  -e GROK_API_KEY="$GROK_API_KEY" \
  -e SECRET_KEY="$SECRET_KEY" \
  -e DREAMWEAVER_DB=/data/dreams.db \
  -v dreamweaver-data:/data \
  dreamweaver-n1
```

Place a TLS-terminating reverse proxy or Vultr Load Balancer in front of port 5000 for public production use.

## Simulation (Intentionality Engine)

`/simulation` runs one offline policy pass over synthetic inputs:
Observe → Estimate → Propose → **SafetyGovernor** → SelectRegime → EmitAudit.
The form collects consent, input validity/freshness, cognitive liberty, stop
request, arousal + ceiling, coherence `C(S)`, broadcast density `I_broadcast`
and context. The page shows the ALLOW/VETO decision, the selected regime
(`Consolidation`, `Expansion`, `Stabilization`, `Safe-State`) and the reason
code, then appends the event to the local JSONL NEXUS ledger and lists recent
events.

The engine is vendored (not installed) from
[`lilbihhh/intentional-architecture`](https://github.com/lilbihhh/intentional-architecture)
at commit `8035e2befd93d2f10947e708fc4a021cb1393c5a` under `intentional_engine/`;
see `intentional_engine/VENDORED.md` for the file map and the minimal local
edits. Events are validated against the upstream Draft 2020-12 schema before
append and hash-chained (`prev_hash` → `event_hash`). Verify a ledger with:

```bash
python -m intentional_engine.verify_audit /data/nexus_ledger.jsonl
```

**Scope and safety:** this is a non-medical, non-actuating research simulation.
No neural input, stimulation parameter, device driver or actuator command is
implemented, `envelope_id` is always `null`, and every proposal is advisory. It
is not a medical device, treatment, clinical protocol or validated BCI, and all
calibration data is synthetic.

## Health check

`GET /healthz` returns:

```json
{"status": "ok"}
```
