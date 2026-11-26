"""Gift Exchange Forge - core engine.

Pure standard library. No network calls, no API keys, no LLM.

Holds the data model for a Secret-Santa style gift exchange, the constraint
solver that produces a valid draw, the review rules that score how ready the
exchange is, and the exporters that turn the result into Markdown / CSV /
ICS / JSON.
"""

from __future__ import annotations

import datetime as _dt
import random
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable, Optional

ENGINE_VERSION = "1.0.0"

AXES = [
    ("setup", "Setup completeness", 0.25),
    ("constraints", "Constraint integrity", 0.20),
    ("timeline", "Timeline feasibility", 0.20),
    ("budget", "Budget coherence", 0.15),
    ("fairness", "Privacy and fairness", 0.20),
]

AXIS_LABELS = {key: label for key, label, _ in AXES}
AXIS_WEIGHTS = {key: weight for key, _, weight in AXES}

SEVERITY_PENALTY = {"critical": 25.0, "high": 15.0, "medium": 8.0, "low": 3.0}
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

VERDICT_BANDS = [
    (90.0, "ready_to_draw", "Ready to draw"),
    (75.0, "mostly_ready", "Mostly ready"),
    (60.0, "needs_tweaks", "Needs tweaks"),
    (40.0, "needs_work", "Needs work"),
    (0.0, "not_ready", "Not ready"),
]


# --------------------------------------------------------------------------
# data model
# --------------------------------------------------------------------------


@dataclass
class Wish:
    item: str
    price: Optional[float] = None
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Wish":
        return Wish(
            item=str(d.get("item", "")),
            price=_as_float(d.get("price")),
            note=str(d.get("note", "")),
        )


@dataclass
class Participant:
    id: str
    name: str
    email: str = ""
    household: str = ""
    groups: list[str] = field(default_factory=list)
    access_code: str = ""
    wishes: list[Wish] = field(default_factory=list)
    purchased: dict[str, float] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["wishes"] = [w.to_dict() if isinstance(w, Wish) else w for w in self.wishes]
        return d

    @staticmethod
    def from_dict(d: dict) -> "Participant":
        return Participant(
            id=str(d.get("id", "")),
            name=str(d.get("name", "")),
            email=str(d.get("email", "")),
            household=str(d.get("household", "")),
            groups=[str(g) for g in (d.get("groups") or [])],
            access_code=str(d.get("access_code", "")),
            wishes=[Wish.from_dict(w) for w in (d.get("wishes") or [])],
            purchased={
                str(k): float(v)
                for k, v in (d.get("purchased") or {}).items()
                if _as_float(v) is not None
            },
            notes=str(d.get("notes", "")),
        )


@dataclass
class Exchange:
    id: str
    name: str = "Secret Santa"
    kind: str = "secret_santa"
    budget: Optional[float] = None
    draw_date: Optional[_dt.date] = None
    shopping_deadline: Optional[_dt.date] = None
    exchange_date: Optional[_dt.date] = None
    shipping_days: int = 5
    circle: str = ""
    avoid_repeats: bool = True
    no_same_household: bool = True
    no_same_group: bool = False
    allow_reveal_early: bool = False
    notes: str = ""
    participants: list[Participant] = field(default_factory=list)
    exclusions: list[tuple[str, str]] = field(default_factory=list)
    history: list[tuple[str, str]] = field(default_factory=list)

    # -- helpers ----------------------------------------------------------
    def by_id(self) -> dict[str, Participant]:
        return {p.id: p for p in self.participants}

    def name_of(self, pid: str) -> str:
        p = self.by_id().get(pid)
        return p.name if p else pid

    def household_of(self, pid: str) -> str:
        p = self.by_id().get(pid)
        return p.household if p else ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "budget": self.budget,
            "draw_date": self.draw_date.isoformat() if self.draw_date else None,
            "shopping_deadline": (
                self.shopping_deadline.isoformat() if self.shopping_deadline else None
            ),
            "exchange_date": (
                self.exchange_date.isoformat() if self.exchange_date else None
            ),
            "shipping_days": self.shipping_days,
            "circle": self.circle,
            "avoid_repeats": self.avoid_repeats,
            "no_same_household": self.no_same_household,
            "no_same_group": self.no_same_group,
            "allow_reveal_early": self.allow_reveal_early,
            "notes": self.notes,
            "participants": [p.to_dict() for p in self.participants],
            "exclusions": [list(e) for e in self.exclusions],
            "history": [list(h) for h in self.history],
        }

    @staticmethod
    def from_dict(d: dict) -> "Exchange":
        return Exchange(
            id=str(d.get("id", "")),
            name=str(d.get("name", "Secret Santa")),
            kind=str(d.get("kind", "secret_santa")),
            budget=_as_float(d.get("budget")),
            draw_date=_as_date(d.get("draw_date")),
            shopping_deadline=_as_date(d.get("shopping_deadline")),
            exchange_date=_as_date(d.get("exchange_date")),
            shipping_days=int(d.get("shipping_days") or 0),
            circle=str(d.get("circle", "")),
            avoid_repeats=bool(d.get("avoid_repeats", True)),
            no_same_household=bool(d.get("no_same_household", True)),
            no_same_group=bool(d.get("no_same_group", False)),
            allow_reveal_early=bool(d.get("allow_reveal_early", False)),
            notes=str(d.get("notes", "")),
            participants=[Participant.from_dict(p) for p in (d.get("participants") or [])],
            exclusions=[
                (str(e[0]), str(e[1]))
                for e in (d.get("exclusions") or [])
                if isinstance(e, (list, tuple)) and len(e) >= 2
            ],
            history=[
                (str(h[0]), str(h[1]))
                for h in (d.get("history") or [])
                if isinstance(h, (list, tuple)) and len(h) >= 2
            ],
        )


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def _as_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _as_date(value: Any) -> Optional[_dt.date]:
    if value is None or value == "":
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d %b %Y", "%b %d %Y", "%Y/%m/%d"):
        try:
            return _dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def slugify(name: str, taken: Optional[set] = None) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", str(name).strip().lower()).strip("-")
    if not base:
        base = "participant"
    if taken is None:
        return base
    slug = base
    n = 2
    while slug in taken:
        slug = "%s-%d" % (base, n)
        n += 1
    return slug


def make_access_code(seed: Optional[str] = None) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    rng = random.Random(seed) if seed else random.SystemRandom()
    return "".join(rng.choice(alphabet) for _ in range(6))


def pair_key(a: str, b: str) -> frozenset:
    return frozenset((a, b))


# --------------------------------------------------------------------------
# solver
# --------------------------------------------------------------------------


@dataclass
class SolveResult:
    ok: bool
    assignment: dict[str, str] = field(default_factory=dict)
    strict: bool = True
    repeat_pairs: list[tuple[str, str]] = field(default_factory=list)
    blocked_groups: list[list[str]] = field(default_factory=list)
    zero_candidate: list[str] = field(default_factory=list)
    relaxations: list[str] = field(default_factory=list)
    attempts: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _build_allowed(
    ex: Exchange,
    history_pairs: Iterable[tuple[str, str]] = (),
    extra_forbidden: Iterable[tuple[str, str]] = (),
    skip_exclusions: Iterable[tuple[str, str]] = (),
) -> dict[str, list[str]]:
    ids = [p.id for p in ex.participants]
    known = set(ids)
    forb: dict[str, set[str]] = {i: {i} for i in ids}

    def block(a: str, b: str) -> None:
        if a in forb and b in forb and a != b:
            forb[a].add(b)
            forb[b].add(a)

    skipped = set()
    for pair in skip_exclusions:
        skipped.add(tuple(pair))
    for a, b in ex.exclusions:
        if (a, b) in skipped or (b, a) in skipped:
            continue
        block(a, b)

    if ex.no_same_household:
        by_house: dict[str, list[str]] = {}
        for p in ex.participants:
            if p.household:
                by_house.setdefault(p.household, []).append(p.id)
        for members in by_house.values():
            for a in members:
                for b in members:
                    block(a, b)

    if ex.no_same_group:
        by_group: dict[str, list[str]] = {}
        for p in ex.participants:
            for g in p.groups:
                by_group.setdefault(g, []).append(p.id)
        for members in by_group.values():
            for a in members:
                for b in members:
                    block(a, b)

    for a, b in history_pairs:
        if a in known and b in known:
            block(a, b)

    for a, b in extra_forbidden:
        if a in known and b in known:
            block(a, b)

    return {a: [b for b in ids if b not in forb[a]] for a in ids}


def _augment(giver: str, allowed, match_giver, match_receiver, seen) -> bool:
    for receiver in allowed[giver]:
        if receiver in seen:
            continue
        seen.add(receiver)
        holder = match_receiver.get(receiver)
        if holder is None or _augment(holder, allowed, match_giver, match_receiver, seen):
            match_giver[giver] = receiver
            match_receiver[receiver] = giver
            return True
    return False


def _max_matching(allowed, ids, order=None):
    """Kuhn's algorithm. Returns (perfect, match_giver, match_receiver)."""
    match_giver: dict[str, str] = {}
    match_receiver: dict[str, str] = {}
    for giver in order or ids:
        if not _augment(giver, allowed, match_giver, match_receiver, set()):
            continue
    return len(match_giver) == len(ids), match_giver, match_receiver


def _hall_violators(allowed, ids, match_giver, match_receiver) -> list[list[str]]:
    """Find the classic Hall violator set via alternating BFS from an unmatched giver."""
    unmatched = [g for g in ids if g not in match_giver]
    if not unmatched:
        return []
    seen_g: set[str] = set()
    seen_r: set[str] = set()
    queue = list(unmatched)
    while queue:
        giver = queue.pop(0)
        if giver in seen_g:
            continue
        seen_g.add(giver)
        for receiver in allowed[giver]:
            if receiver in seen_r:
                continue
            seen_r.add(receiver)
            holder = match_receiver.get(receiver)
            if holder is not None and holder not in seen_g:
                queue.append(holder)
    if len(seen_r) < len(seen_g):
        return [sorted(seen_g)]
    return []


def _relaxation_hints(ex: Exchange, ids) -> list[str]:
    """Concrete changes that would make an impossible draw possible."""
    hints: list[str] = []
    for a, b in ex.exclusions:
        trial = _build_allowed(ex, set(), skip_exclusions={(a, b)})
        ok, _, _ = _max_matching(trial, ids)
        if ok:
            hints.append(
                "Remove the exclusion between %s and %s and the draw becomes possible."
                % (ex.name_of(a), ex.name_of(b))
            )
            break
    if ex.no_same_household:
        relaxed = Exchange.from_dict(ex.to_dict())
        relaxed.no_same_household = False
        trial = _build_allowed(relaxed, set())
        ok, _, _ = _max_matching(trial, ids)
        if ok:
            hints.append(
                "Allow same-household draws and the draw becomes possible - "
                "at least one pair is currently impossible."
            )
        households: dict[str, int] = {}
        for p in ex.participants:
            if p.household:
                households[p.household] = households.get(p.household, 0) + 1
        for hh, size in sorted(households.items(), key=lambda kv: -kv[1]):
            others = len(ids) - size
            if size > others:
                hints.append(
                    "Household '%s' has %d members but only %d people outside it, so they "
                    "cannot all draw out. Merge the exchange or allow same-household draws."
                    % (hh, size, others)
                )
                break
    return hints


def solve_assignment(
    ex: Exchange,
    history_pairs: Iterable[tuple[str, str]] = (),
    seed: Optional[int] = None,
    attempts: int = 24,
) -> SolveResult:
    """Draw a valid assignment: everyone gives to exactly one person, nobody to themselves."""
    ids = [p.id for p in ex.participants]
    history = [tuple(p) for p in history_pairs]
    history_set = {pair_key(a, b) for a, b in history}

    if len(ids) < 2:
        return SolveResult(
            ok=False,
            zero_candidate=list(ids),
            notes=["At least two participants are needed before a draw is possible."],
        )

    allowed_base = _build_allowed(ex, set())
    zero_base = [g for g in ids if not allowed_base[g]]
    if zero_base:
        return SolveResult(
            ok=False,
            zero_candidate=zero_base,
            blocked_groups=[sorted(zero_base)],
            relaxations=_relaxation_hints(ex, ids),
            notes=[
                "These participants have nobody they are allowed to draw: "
                + ", ".join(ex.name_of(g) for g in zero_base)
            ],
        )
    allowed = _build_allowed(ex, history_set)

    rng = random.Random(seed)
    tried = 0
    for _ in range(attempts):
        tried += 1
        order = list(ids)
        rng.shuffle(order)
        perfect, match_giver, match_receiver = _max_matching(allowed, ids, order)
        if perfect:
            return SolveResult(ok=True, assignment=match_giver, strict=True, attempts=tried)

    # No perfect matching with the no-repeat history included: diagnose and relax.
    perfect_base, match_base, recv_base = _max_matching(allowed_base, ids)
    blocked = _hall_violators(allowed_base, ids, match_base, recv_base)
    relaxations: list[str] = []

    if perfect_base:
        repeats = [
            (g, r) for g, r in match_base.items() if pair_key(g, r) in history_set
        ]
        for hp in history_set:
            pair = tuple(hp)
            trial = _build_allowed(ex, history_set - {hp})
            ok, _, _ = _max_matching(trial, ids)
            if ok:
                relaxations.append(
                    "Drop the no-repeat rule between %s and %s and the draw becomes possible."
                    % (ex.name_of(pair[0]), ex.name_of(pair[1]))
                )
                break
        return SolveResult(
            ok=False,
            assignment=match_base,
            strict=False,
            repeat_pairs=repeats,
            blocked_groups=blocked,
            relaxations=relaxations,
            attempts=tried,
            notes=[
                "A valid draw exists only if a pair repeats from a previous year."
            ],
        )

    # Base constraints are impossible on their own.
    relaxations = _relaxation_hints(ex, ids)
    zero_base = [g for g in ids if not allowed_base[g]]
    return SolveResult(
        ok=False,
        assignment={},
        strict=False,
        blocked_groups=blocked,
        zero_candidate=zero_base,
        relaxations=relaxations,
        attempts=tried,
        notes=["No valid draw exists under the current rules."],
    )


# ENGINE_PART_TWO_MARKER
