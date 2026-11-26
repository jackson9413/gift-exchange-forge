"""Gift Exchange Forge - Flask application.

A local-first web app for running a Secret Santa style gift exchange: paste a
brief or build the roster by hand, run a constraint-checked draw, check the
exchange is actually ready, and hand each participant a code that shows only
their own pairing.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import uuid

from flask import Flask, jsonify, request, send_file

import exporters
import samples
from briefparse import parse_brief
from engine import (
    ENGINE_VERSION,
    Exchange,
    Participant,
    Wish,
    _as_date,
    _as_float,
    make_access_code,
    slugify,
    solve_assignment,
)
from rules import review
from storage import DEFAULT_DB, Store

BOOL_FIELDS = (
    "avoid_repeats",
    "no_same_household",
    "no_same_group",
    "allow_reveal_early",
)


def _payload() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    for key, value in request.args.items():
        data.setdefault(key, value)
    return data


def _clean_id(value: str) -> str:
    return "".join(ch for ch in str(value) if ch.isalnum() or ch in "-_").strip().lower()


def create_app(db_path: str = None) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    store = Store(db_path or os.environ.get("GIFT_EXCHANGE_DB", DEFAULT_DB))
    app.config["STORE"] = store

    # ------------------------------------------------------------ helpers
    def load(eid: str):
        return store.load_exchange(eid)

    def history_for(ex: Exchange) -> list[tuple[str, str]]:
        pairs = list(ex.history or [])
        pairs.extend(store.history_pairs(ex.circle, ex.id))
        return pairs

    def build_report(ex: Exchange, assignment=None, solve=None):
        return review(
            ex,
            assignment=assignment,
            solve=solve,
            history_pairs=history_for(ex),
        )

    def save(ex: Exchange) -> Exchange:
        return store.save_exchange(ex)

    def exchange_payload(ex: Exchange, assignment=None) -> dict:
        assignment = assignment if assignment is not None else store.load_assignment(ex.id)
        return {
            "exchange": ex.to_dict(),
            "assignment": assignment or {},
            "report": build_report(ex, assignment or {}),
        }

    # ------------------------------------------------------------- routes
    @app.route("/")
    def index():
        return send_file(
            os.path.join(app.static_folder, "index.html"), mimetype="text/html"
        )

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True, "version": ENGINE_VERSION})

    @app.get("/api/samples")
    def list_samples():
        return jsonify({"samples": samples.sample_briefs()})

    @app.post("/api/samples/load")
    def load_sample():
        data = _payload()
        sample_id = str(data.get("sample", ""))
        try:
            ex, warnings, history = samples.build_sample(sample_id)
        except KeyError:
            return jsonify({"error": "unknown sample '%s'" % sample_id}), 400
        ex.id = "%s-%s" % (sample_id, uuid.uuid4().hex[:6])
        ex.history = history
        save(ex)
        assignment = store.load_assignment(ex.id)
        return jsonify(
            {
                "warnings": warnings,
                "exchange": ex.to_dict(),
                "assignment": assignment or {},
                "report": build_report(ex, assignment or {}),
            }
        )

    @app.get("/api/exchanges")
    def list_exchanges():
        return jsonify({"exchanges": store.list_exchanges()})

    @app.post("/api/exchanges")
    def create_exchange():
        data = _payload()
        brief = data.get("brief")
        if isinstance(brief, str) and brief.strip():
            ex, warnings = parse_brief(brief, exchange_id="exchange")
            ex.id = "exchange-%s" % uuid.uuid4().hex[:8]
            save(ex)
            return jsonify(
                {
                    "warnings": warnings,
                    "exchange": ex.to_dict(),
                    "assignment": {},
                    "report": build_report(ex, {}),
                }
            )
        ex = Exchange.from_dict(data.get("exchange") or {})
        ex.id = ex.id or ("exchange-%s" % uuid.uuid4().hex[:8])
        save(ex)
        return jsonify({"exchange": ex.to_dict(), "assignment": {}, "report": build_report(ex, {})})

    @app.get("/api/exchanges/<eid>")
    def get_exchange(eid):
        ex = load(eid)
        if not ex:
            return jsonify({"error": "exchange '%s' not found" % eid}), 404
        return jsonify(exchange_payload(ex))

    @app.put("/api/exchanges/<eid>")
    def update_exchange(eid):
        ex = load(eid)
        if not ex:
            return jsonify({"error": "exchange '%s' not found" % eid}), 404
        data = _payload()
        if "name" in data:
            ex.name = str(data["name"])
        if "budget" in data:
            ex.budget = _as_float(data["budget"])
        if "draw_date" in data:
            ex.draw_date = _as_date(data["draw_date"])
        if "shopping_deadline" in data:
            ex.shopping_deadline = _as_date(data["shopping_deadline"])
        if "exchange_date" in data:
            ex.exchange_date = _as_date(data["exchange_date"])
        if "shipping_days" in data:
            try:
                ex.shipping_days = int(float(data["shipping_days"]))
            except (TypeError, ValueError):
                pass
        if "circle" in data:
            ex.circle = str(data["circle"])
        if "notes" in data:
            ex.notes = str(data["notes"])
        for field in BOOL_FIELDS:
            if field in data:
                setattr(ex, field, bool(data[field]))
        save(ex)
        return jsonify(exchange_payload(ex))

    @app.delete("/api/exchanges/<eid>")
    def delete_exchange(eid):
        ok = store.delete_exchange(eid)
        if not ok:
            return jsonify({"error": "exchange '%s' not found" % eid}), 404
        return jsonify({"deleted": True})

    # ------------------------------------------------------- participants
    @app.post("/api/exchanges/<eid>/participants")
    def add_participant(eid):
        ex = load(eid)
        if not ex:
            return jsonify({"error": "exchange '%s' not found" % eid}), 404
        data = _payload()
        name = str(data.get("name", "")).strip()
        if not name:
            return jsonify({"error": "a participant needs a name"}), 400
        taken = set(ex.by_id().keys())
        pid = slugify(name, taken)
        participant = Participant(
            id=pid,
            name=name,
            email=str(data.get("email", "")).strip(),
            household=str(data.get("household", "")).strip(),
            groups=[str(g).strip() for g in (data.get("groups") or []) if str(g).strip()],
            access_code=make_access_code(pid + name),
            notes=str(data.get("notes", "")),
        )
        ex.participants.append(participant)
        save(ex)
        return jsonify(exchange_payload(ex))

    @app.patch("/api/exchanges/<eid>/participants/<pid>")
    def update_participant(eid, pid):
        ex = load(eid)
        if not ex:
            return jsonify({"error": "exchange '%s' not found" % eid}), 404
        pmap = ex.by_id()
        if pid not in pmap:
            return jsonify({"error": "participant '%s' not found" % pid}), 404
        p = pmap[pid]
        data = _payload()
        if "name" in data:
            p.name = str(data["name"]).strip() or p.name
        if "email" in data:
            p.email = str(data["email"]).strip()
        if "household" in data:
            p.household = str(data["household"]).strip()
        if "groups" in data:
            p.groups = [str(g).strip() for g in (data.get("groups") or []) if str(g).strip()]
        if "access_code" in data:
            p.access_code = str(data["access_code"]).strip().upper()
        if "notes" in data:
            p.notes = str(data["notes"])
        if "wishes" in data:
            p.wishes = [
                Wish.from_dict(w) if isinstance(w, dict) else w
                for w in (data.get("wishes") or [])
            ]
        if "purchased" in data:
            p.purchased = {
                str(k): float(v)
                for k, v in (data.get("purchased") or {}).items()
                if _as_float(v) is not None
            }
        save(ex)
        return jsonify(exchange_payload(ex))

    @app.delete("/api/exchanges/<eid>/participants/<pid>")
    def delete_participant(eid, pid):
        ex = load(eid)
        if not ex:
            return jsonify({"error": "exchange '%s' not found" % eid}), 404
        before = len(ex.participants)
        ex.participants = [p for p in ex.participants if p.id != pid]
        if len(ex.participants) == before:
            return jsonify({"error": "participant '%s' not found" % pid}), 404
        ex.exclusions = [
            (a, b) for a, b in ex.exclusions if pid not in (a, b)
        ]
        save(ex)
        return jsonify(exchange_payload(ex))

    # --------------------------------------------------------- exclusions
    @app.post("/api/exchanges/<eid>/exclude")
    def add_exclusion(eid):
        ex = load(eid)
        if not ex:
            return jsonify({"error": "exchange '%s' not found" % eid}), 404
        data = _payload()
        a = _resolve(ex, data.get("a"))
        b = _resolve(ex, data.get("b"))
        if not a or not b:
            return jsonify({"error": "both people must be on the list"}), 400
        if a == b:
            return jsonify({"error": "somebody cannot be excluded from themselves"}), 400
        if (a, b) not in ex.exclusions and (b, a) not in ex.exclusions:
            ex.exclusions.append((a, b))
        save(ex)
        return jsonify(exchange_payload(ex))

    @app.delete("/api/exchanges/<eid>/exclude")
    def remove_exclusion(eid):
        ex = load(eid)
        if not ex:
            return jsonify({"error": "exchange '%s' not found" % eid}), 404
        data = _payload()
        a = _resolve(ex, data.get("a"))
        b = _resolve(ex, data.get("b"))
        ex.exclusions = [
            (x, y) for (x, y) in ex.exclusions if not ({x, y} == {a, b})
        ]
        save(ex)
        return jsonify(exchange_payload(ex))

    # -------------------------------------------------------------- draw
    @app.post("/api/exchanges/<eid>/draw")
    def run_draw(eid):
        ex = load(eid)
        if not ex:
            return jsonify({"error": "exchange '%s' not found" % eid}), 404
        data = _payload()
        seed = data.get("seed")
        solve = solve_assignment(
            ex, history_pairs=history_for(ex), seed=seed if seed is not None else None
        )
        if solve.ok:
            store.save_assignment(eid, solve.assignment)
        report = build_report(ex, solve.assignment if solve.ok else {}, solve)
        return jsonify(
            {
                "ok": solve.ok,
                "solve": solve.to_dict(),
                "assignment": solve.assignment if solve.ok else {},
                "report": report,
            }
        )

    @app.get("/api/exchanges/<eid>/report")
    def get_report(eid):
        ex = load(eid)
        if not ex:
            return jsonify({"error": "exchange '%s' not found" % eid}), 404
        assignment = store.load_assignment(eid) or {}
        return jsonify({"report": build_report(ex, assignment)})

    @app.get("/api/exchanges/<eid>/export")
    def export_exchange(eid):
        ex = load(eid)
        if not ex:
            return jsonify({"error": "exchange '%s' not found" % eid}), 404
        assignment = store.load_assignment(eid) or {}
        report = build_report(ex, assignment)
        fmt = (request.args.get("format") or "md").lower()
        if fmt == "csv":
            body = exporters.to_csv(ex, assignment)
            mimetype = "text/csv"
        elif fmt == "ics":
            body = exporters.to_ics(ex, assignment)
            mimetype = "text/calendar"
        elif fmt == "json":
            body = exporters.to_json(ex, report, assignment)
            mimetype = "application/json"
        elif fmt == "sheet":
            body = exporters.to_participant_sheet(ex, assignment)
            mimetype = "text/plain"
        else:
            body = exporters.to_markdown(ex, report, assignment)
            mimetype = "text/markdown"
        return app.response_class(body, mimetype=mimetype)

    # ------------------------------------------------------------ reveal
    @app.get("/api/reveal")
    def reveal():
        code = (request.args.get("code") or "").strip().upper()
        if not code:
            return jsonify({"error": "enter your access code"}), 400
        found = None
        for row in store.list_exchanges():
            ex = store.load_exchange(row["id"])
            if not ex:
                continue
            for p in ex.participants:
                if p.access_code.strip().upper() == code:
                    found = (ex, p)
                    break
            if found:
                break
        if not found:
            return jsonify({"error": "no participant has that code"}), 404
        ex, p = found
        assignment = store.load_assignment(ex.id) or {}
        receiver_id = assignment.get(p.id)
        receiver = ex.by_id().get(receiver_id) if receiver_id else None
        return jsonify(
            {
                "exchange": {
                    "id": ex.id,
                    "name": ex.name,
                    "draw_date": ex.draw_date.isoformat() if ex.draw_date else None,
                    "shopping_deadline": (
                        ex.shopping_deadline.isoformat() if ex.shopping_deadline else None
                    ),
                    "exchange_date": (
                        ex.exchange_date.isoformat() if ex.exchange_date else None
                    ),
                    "budget": ex.budget,
                    "shipping_days": ex.shipping_days,
                },
                "you": p.name,
                "drawn": receiver.name if receiver else None,
                "drawn_notes": receiver.notes if receiver else "",
                "wishes": [w.to_dict() for w in receiver.wishes] if receiver else [],
                "drawn_at": None,
            }
        )

    # -------------------------------------------------------------- runs
    @app.get("/api/runs")
    def list_runs():
        return jsonify({"runs": store.list_runs()})

    @app.post("/api/exchanges/<eid>/runs")
    def log_run(eid):
        ex = load(eid)
        if not ex:
            return jsonify({"error": "exchange '%s' not found" % eid}), 404
        data = _payload()
        assignment = store.load_assignment(eid) or {}
        report = build_report(ex, assignment)
        rating = data.get("rating")
        rating = int(rating) if rating not in (None, "") else None
        notes = str(data.get("notes", ""))
        run_id = store.log_run(eid, report, rating=rating, notes=notes)
        return jsonify({"run_id": run_id, "report": report})

    @app.post("/api/runs/<int:run_id>/rating")
    def rate_run(run_id):
        data = _payload()
        rating = data.get("rating")
        if rating in (None, ""):
            return jsonify({"error": "a rating is required"}), 400
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            return jsonify({"error": "rating must be a number"}), 400
        if rating < 1 or rating > 5:
            return jsonify({"error": "rating must be 1-5"}), 400
        ok = store.rate_run(run_id, rating, str(data.get("notes", "")))
        if not ok:
            return jsonify({"error": "run %s not found" % run_id}), 404
        return jsonify({"updated": True, "run_id": run_id, "rating": rating})

    return app


def _resolve(ex: Exchange, value) -> str:
    """Accept an id or a name and return the participant id."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    pmap = ex.by_id()
    if text in pmap:
        return text
    lowered = text.lower()
    for pid, p in pmap.items():
        if p.name.strip().lower() == lowered:
            return pid
    return ""


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))
    app.run(host="127.0.0.1", port=port, debug=False)
