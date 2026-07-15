---
name: testing-dreamweaver-flows
description: End-to-end test the DreamWeaver N1 Flask app (dream record/playback, TMR sessions, persistence, Grok Coach degradation). Use when verifying UI or route changes in app.py / dreamweaver_enhanced.py.
---

# Testing DreamWeaver flows

## What this app does
Flask app (`app.py`) + service layer (`dreamweaver_enhanced.py`, `DreamStore`/`GrokCoach`) backed by SQLite. Core flows: record a dream → animated playback → TMR session (start → deliver cue → complete) → dashboard history. Grok Coach streams advice when configured.

## Run it locally
Use the production server against a throwaway DB so tests don't pollute state:
```
rm -f /tmp/dw-test.db
SECRET_KEY=e2e DREAMWEAVER_DB=/tmp/dw-test.db PORT=5000 \
  .venv/bin/gunicorn app:app --bind 127.0.0.1:5000 --workers 1 --access-logfile - --error-logfile -
```
Health check: `curl -f http://127.0.0.1:5000/healthz` → `{"status":"ok"}`.

## Golden-path UI test (record a browser session)
1. Dashboard `/` — precondition: empty state + "Grok Coach is offline" notice.
2. `/record` — fill Title, Intention, Scene, and optionally a public MP4/GIF/image URL; Save → redirects to `/play/<id>` with a success flash.
3. Playback `/play/<id>` — confirm scene caption + animated `#dreamscape`. With media, assert a real `#dream-media` video/image loads; Pause must freeze HTML5 video and overlays, and Play must resume them.
4. `/tmr` — recorded dream appears in the select; Start Session → `/tmr/<id>`, status `active`, cues `0`.
5. Deliver Cue → cue count increments by exactly 1 (assert the number, not just the click).
6. Complete Session → status `completed`, completion timestamp shown, cue/complete buttons disappear.
7. Dashboard `/` — dream + completed session listed.
8. When session highlights are present, assert exact values (for one completed one-cue session: Recent 1, Active 0, Completed 1, Cues 1).

## Rich media fixture
For deterministic HTML5 video testing, generate and serve a changing local MP4:
```
mkdir -p /home/ubuntu/dreamweaver-test-media
ffmpeg -y -f lavfi -i 'testsrc2=size=960x540:rate=30' -t 8 \
  -c:v libx264 -pix_fmt yuv420p -movflags +faststart \
  /home/ubuntu/dreamweaver-test-media/dreamscape.mp4
.venv/bin/python -m http.server 5051 --bind 127.0.0.1 \
  --directory /home/ubuntu/dreamweaver-test-media
```
Record with `http://127.0.0.1:5051/dreamscape.mp4`. The moving test pattern makes Pause/Play objectively visible. Also submit a `.txt` URL once and expect the styled 400 supported-format error.

## Persistence check (important)
Kill and restart Gunicorn against the SAME `DREAMWEAVER_DB`, reload `/`, and confirm the dream and session are still there. This is the real proof of SQLite persistence, cheap to do.

## Grok Coach
- Without a key: `/coach` shows the offline notice and the Ask button is `disabled`. `/coach/ask` returns HTTP 503 plain text. This is the degradation path — always testable.
- Live streaming needs `GROK_API_KEY` or its supported alias `XAI_API_KEY`. If both are absent, mark live streaming **untested** rather than claiming it works. Env vars: `GROK_API_KEY`, `XAI_API_KEY`, `GROK_API_URL`, `GROK_MODEL`.

## Production checks
- Coverage: `.venv/bin/python -m pytest --cov-report=term-missing --cov-report=html` (coverage targets are already in `pytest.ini`).
- Lint: `.venv/bin/ruff check . && .venv/bin/ruff format --check .`.
- Docker: build the image, run with `DREAMWEAVER_DB=/data/dreams.db` and a host/volume mount at `/data`, then assert `docker inspect` reports `healthy` and `/healthz` returns `{"status":"ok"}`.

## Error handling
`/play/999` (missing id) → styled 404 page "Dream 999 not found". Good quick adversarial check.

## Gotchas
- Maximize the browser before recording: `wmctrl -r :ACTIVE: -b add,maximized_vert,maximized_horz` (install wmctrl if missing). Avoid xdotool super+key.
- The Vercel PR preview is SSO-protected — it may not be usable for functional testing; prefer local Gunicorn.
- Assert on DOM/text (cue count, status badge) not just screenshots; the stripped DOM returned with each computer screenshot is reliable for this.

## Devin Secrets Needed
- `GROK_API_KEY` (or `XAI_API_KEY`) — only required to test live Grok Coach streaming. All other flows need no secrets.
