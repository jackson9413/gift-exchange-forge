"""Gift Exchange Forge - SQLite storage.

Stores exchanges, the current draw for each exchange, and a log of review runs
with a 1-5 star self-rating. Standard library only.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3

from engine import Exchange

DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "gift_exchange.db"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS exchanges (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    circle TEXT DEFAULT '',
    budget REAL,
    draw_date TEXT,
    exchange_date TEXT,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assignments (
    exchange_id TEXT NOT NULL,
    giver_id TEXT NOT NULL,
    receiver_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (exchange_id, giver_id)
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    verdict TEXT,
    score REAL,
    rating INTEGER,
    notes TEXT,
    summary TEXT
);
"""


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


class _Closing:
    """sqlite3 connection wrapper that commits and closes on exit."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self.conn.close()
        return False


class Store:
    def __init__(self, path: str = DEFAULT_DB):
        self.path = path
        self.init_schema()

    def connect(self) -> _Closing:
        if self.path != ":memory:":
            folder = os.path.dirname(os.path.abspath(self.path))
            if folder:
                os.makedirs(folder, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return _Closing(conn)

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    # -- exchanges --------------------------------------------------------
    def save_exchange(self, ex: Exchange) -> Exchange:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO exchanges
                   (id, name, circle, budget, draw_date, exchange_date, payload,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name, circle=excluded.circle, budget=excluded.budget,
                     draw_date=excluded.draw_date, exchange_date=excluded.exchange_date,
                     payload=excluded.payload, updated_at=excluded.updated_at""",
                (
                    ex.id,
                    ex.name,
                    ex.circle,
                    ex.budget,
                    ex.draw_date.isoformat() if ex.draw_date else None,
                    ex.exchange_date.isoformat() if ex.exchange_date else None,
                    json.dumps(ex.to_dict()),
                    _now(),
                    _now(),
                ),
            )
        return ex

    def load_exchange(self, exchange_id: str):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload FROM exchanges WHERE id = ?", (exchange_id,)
            ).fetchone()
        if not row:
            return None
        return Exchange.from_dict(json.loads(row["payload"]))

    def list_exchanges(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT id, name, circle, budget, draw_date, exchange_date,
                          updated_at, payload
                   FROM exchanges ORDER BY updated_at DESC"""
            ).fetchall()
        out = []
        for row in rows:
            payload = json.loads(row["payload"])
            out.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "circle": row["circle"],
                    "budget": row["budget"],
                    "draw_date": row["draw_date"],
                    "exchange_date": row["exchange_date"],
                    "updated_at": row["updated_at"],
                    "participants": len(payload.get("participants") or []),
                    "has_draw": self.load_assignment(row["id"]) is not None,
                }
            )
        return out

    def delete_exchange(self, exchange_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM exchanges WHERE id = ?", (exchange_id,))
            conn.execute("DELETE FROM assignments WHERE exchange_id = ?", (exchange_id,))
            conn.execute("DELETE FROM runs WHERE exchange_id = ?", (exchange_id,))
            return cur.rowcount > 0

    # -- assignments ------------------------------------------------------
    def save_assignment(self, exchange_id: str, assignment: dict) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM assignments WHERE exchange_id = ?", (exchange_id,))
            for giver, receiver in assignment.items():
                conn.execute(
                    """INSERT INTO assignments
                       (exchange_id, giver_id, receiver_id, created_at)
                       VALUES (?,?,?,?)""",
                    (exchange_id, giver, receiver, _now()),
                )

    def load_assignment(self, exchange_id: str):
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT giver_id, receiver_id FROM assignments WHERE exchange_id = ?",
                (exchange_id,),
            ).fetchall()
        if not rows:
            return None
        return {r["giver_id"]: r["receiver_id"] for r in rows}

    def history_pairs(self, circle: str, exclude_exchange: str = "") -> list[tuple[str, str]]:
        """Pairings from previous exchanges in the same circle."""
        if not circle:
            return []
        pairs: list[tuple[str, str]] = []
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id FROM exchanges WHERE circle = ? AND id != ?",
                (circle, exclude_exchange),
            ).fetchall()
            for row in rows:
                arows = conn.execute(
                    "SELECT giver_id, receiver_id FROM assignments WHERE exchange_id = ?",
                    (row["id"],),
                ).fetchall()
                for a in arows:
                    pairs.append((a["giver_id"], a["receiver_id"]))
        return pairs

    # -- run log ----------------------------------------------------------
    def log_run(self, exchange_id: str, report: dict, rating=None, notes: str = "") -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """INSERT INTO runs
                   (exchange_id, created_at, verdict, score, rating, notes, summary)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    exchange_id,
                    _now(),
                    report.get("verdict"),
                    report.get("score"),
                    rating,
                    notes,
                    json.dumps(report.get("summary") or {}),
                ),
            )
            return int(cur.lastrowid)

    def list_runs(self, limit: int = 50) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT r.*, e.name AS exchange_name
                   FROM runs r LEFT JOIN exchanges e ON e.id = r.exchange_id
                   ORDER BY r.id DESC LIMIT ?""",
                (int(limit),),
            ).fetchall()
        return [dict(r) for r in rows]

    def rate_run(self, run_id: int, rating: int, notes: str = "") -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "UPDATE runs SET rating = ?, notes = ? WHERE id = ?",
                (int(rating), notes, int(run_id)),
            )
            return cur.rowcount > 0
