# DreamWeaver N1 — Base44 Dev Notes

## Overview
Flask app (single process) serving Jinja2 templates + JSON API. SQLite for
persistence (dreams + TMR sessions). Optional Grok/xAI integration powers the
streaming "Coach" feature.

## Running in Base44
- `docker compose -f docker-compose.base44.yml up -d` — starts the Flask dev
  server (debug mode, live reload) on host port 3000.
- Base image: `python:3.10-slim`; source is bind-mounted at `/app`; deps install
  on container startup from `requirements.txt`.
- SQLite DB lives in a named volume at `/data/dreams.db` (`DREAMWEAVER_DB`).
- Healthcheck: `GET /healthz` → `{"status": "ok"}`.

## Secrets
- `GROK_API_KEY` (optional): xAI API key for the Coach feature. Without it the
  app boots fine; the Coach page shows "not configured". Delivered via
  `/run/base44/app.env`; placeholder in `.env.base44-defaults` is empty.
- `SECRET_KEY`: defaults to `dev-secret-key` in code; override via secrets for
  production.

## Simulation section (Intentionality Engine)
- `intentionality_blueprint.py` registers `/simulation` (form + ALLOW/VETO
  result + recent-events table). `app.create_app(nexus_ledger=...)` overrides
  the ledger path for tests.
- `intentional_engine/` is a vendored copy of
  `lilbihhh/intentional-architecture` @ `8035e2befd93d2f10947e708fc4a021cb1393c5a`
  (see `intentional_engine/VENDORED.md`). Do not edit policy/metric/regime logic
  locally; re-vendor instead.
- `jsonschema` is required for strict NEXUS audit validation — it is pinned in
  `requirements.txt`.
- Ledger: `DREAMWEAVER_NEXUS_LEDGER`, defaulting to `/data/nexus_ledger.jsonl`
  (persistent volume) — append-only JSONL, hash-chained, one schema-validated
  event per pass. Verify with
  `python -m intentional_engine.verify_audit <ledger>`.
- The section is non-actuating: no envelope, no stimulation parameters, no
  device commands; `envelope_id` is always null.
- Form POST redirects back to `/simulation`; the decision shows once from the
  Flask session, while the ledger table persists across reloads.

## Dev server notes
- Flask debug server auto-reloads on source changes — no manual restart needed
  for template/Python edits.
- No HOST/ORIGIN allowlist issues with Flask's dev server.

## Tests
```
docker compose -f docker-compose.base44.yml exec web pytest
```
