"""DreamWeaver N1 Flask web application.

Turning sleep into deliberate creation. This module is a thin adapter over the
service layer in :mod:`dreamweaver_enhanced`: it wires HTTP routes to the
``DreamStore`` (persistent SQLite) and ``GrokCoach`` (streaming lucid-dreaming
advice), renders the dashboard/record/playback/TMR/coach pages and centralises
error handling.
"""

from __future__ import annotations

import os

from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    stream_with_context,
    url_for,
)

from dreamweaver_enhanced import (
    DreamStore,
    DreamWeaverError,
    GrokCoach,
    GrokError,
    NotFoundError,
    ValidationError,
)


def create_app(
    store: "DreamStore | None" = None, coach: "GrokCoach | None" = None
) -> Flask:
    """Application factory.

    Accepting ``store``/``coach`` makes the app trivially testable with an
    in-memory database and a fake coach, while production callers rely on the
    environment-driven defaults.
    """

    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
    app.config["STORE"] = store or DreamStore()
    app.config["COACH"] = coach or GrokCoach()

    def get_store() -> DreamStore:
        return app.config["STORE"]

    def get_coach() -> GrokCoach:
        return app.config["COACH"]

    @app.route("/")
    def dashboard():
        store = get_store()
        dreams = store.list_dreams(limit=10)
        sessions = store.list_tmr_sessions(limit=10)
        session_summary = {
            "total": len(sessions),
            "active": sum(session.status == "active" for session in sessions),
            "completed": sum(session.status == "completed" for session in sessions),
            "cues": sum(session.cue_count for session in sessions),
        }
        return render_template(
            "dashboard.html",
            dreams=dreams,
            sessions=sessions,
            session_summary=session_summary,
            coach_ready=get_coach().is_configured,
        )

    @app.route("/record", methods=["GET", "POST"])
    def record():
        if request.method == "POST":
            store = get_store()
            dream = store.add_dream(
                title=request.form.get("title", ""),
                intention=request.form.get("intention", ""),
                scene=request.form.get("scene", ""),
                media_url=request.form.get("media_url", ""),
            )
            flash(f"Dream '{dream.title}' recorded.", "success")
            return redirect(url_for("play", dream_id=dream.id))
        return render_template("record.html")

    @app.route("/play/<int:dream_id>")
    def play(dream_id: int):
        dream = get_store().get_dream(dream_id)
        return render_template("play.html", dream=dream)

    @app.route("/tmr")
    def tmr():
        store = get_store()
        return render_template(
            "tmr.html",
            dreams=store.list_dreams(limit=50),
            sessions=store.list_tmr_sessions(limit=10),
        )

    @app.route("/tmr/start", methods=["POST"])
    def tmr_start():
        try:
            dream_id = int(request.form.get("dream_id", 0))
        except (TypeError, ValueError) as exc:
            raise ValidationError("Select a valid dream.") from exc
        session = get_store().start_tmr_session(dream_id)
        flash("TMR session started.", "success")
        return redirect(url_for("tmr_session", session_id=session.id))

    @app.route("/tmr/<int:session_id>")
    def tmr_session(session_id: int):
        store = get_store()
        session = store.get_tmr_session(session_id)
        dream = store.get_dream(session.dream_id)
        return render_template("tmr_session.html", session=session, dream=dream)

    @app.route("/tmr/<int:session_id>/cue", methods=["POST"])
    def tmr_cue(session_id: int):
        get_store().record_cue(session_id)
        return redirect(url_for("tmr_session", session_id=session_id))

    @app.route("/tmr/<int:session_id>/complete", methods=["POST"])
    def tmr_complete(session_id: int):
        get_store().complete_tmr_session(session_id)
        flash("TMR session completed.", "success")
        return redirect(url_for("tmr_session", session_id=session_id))

    @app.route("/coach")
    def coach():
        return render_template("coach.html", coach_ready=get_coach().is_configured)

    @app.route("/coach/ask", methods=["POST"])
    def coach_ask():
        coach = get_coach()
        question = request.form.get("question", "")
        intention = request.form.get("intention", "")
        if not coach.is_configured:
            return Response(
                "The Grok coach is not configured. Set GROK_API_KEY or "
                "XAI_API_KEY to enable it.",
                status=503,
                mimetype="text/plain",
            )

        @stream_with_context
        def generate():
            try:
                for token in coach.stream(question, intention):
                    yield token
            except DreamWeaverError as exc:
                yield f"\n[error] {exc}"

        return Response(
            generate(),
            mimetype="text/plain",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.route("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.errorhandler(ValidationError)
    def handle_validation(exc: ValidationError):
        return render_template("error.html", code=400, message=str(exc)), 400

    @app.errorhandler(NotFoundError)
    def handle_not_found(exc: NotFoundError):
        return render_template("error.html", code=404, message=str(exc)), 404

    @app.errorhandler(GrokError)
    def handle_grok(exc: GrokError):
        return render_template("error.html", code=503, message=str(exc)), 503

    @app.errorhandler(404)
    def handle_404(exc):
        return render_template("error.html", code=404, message="Page not found."), 404

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
