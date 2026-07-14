# DreamWeaver N1

Turning sleep into deliberate creation.

Built by AleXus — The Architect.

DreamWeaver N1 is a Flask application for recording dream intentions, replaying animated dream scenes, running Targeted Memory Reactivation (TMR) sessions, and receiving streaming lucid-dreaming guidance from Grok.

## Features

- Persistent SQLite storage for multiple dreams and TMR sessions
- Dashboard with recent dreams and TMR activity
- Dream recording and animated, video-style scene playback
- TMR start, cue logging, and completion workflow
- Streaming Grok Coach responses with lucid-dreaming-specific prompting
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
| `GROK_API_KEY` | For Coach | — | xAI API key; never commit it |
| `GROK_API_URL` | No | `https://api.x.ai/v1/chat/completions` | Grok chat-completions endpoint |
| `GROK_MODEL` | No | `grok-4.5` | xAI model used by the coach |
| `DREAMWEAVER_DB` | No | `dreams.db` | SQLite database path |
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

## Health check

`GET /healthz` returns:

```json
{"status": "ok"}
```
