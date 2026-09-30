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

## Dev server notes
- Flask debug server auto-reloads on source changes — no manual restart needed
  for template/Python edits.
- No HOST/ORIGIN allowlist issues with Flask's dev server.

## Tests
```
docker compose -f docker-compose.base44.yml exec web pytest
```
