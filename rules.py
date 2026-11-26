"""Gift Exchange Forge - review rules and scoring.

Every rule returns findings that carry the evidence that triggered them, why it
matters and a concrete fix. The five axes are weighted into a 0-100 readiness
score and structural caps stop an exchange from scoring well while the part
that actually breaks the draw is missing.
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

from engine import (
    AXES,
    AXIS_LABELS,
    AXIS_WEIGHTS,
    SEVERITY_PENALTY,
    SEVERITY_RANK,
    VERDICT_BANDS,
    Exchange,
    SolveResult,
    pair_key,
    solve_assignment,
)

TODAY = _dt.date.today()


def _finding(fid, severity, axis, title, evidence, why, fix) -> dict:
    return {
        "id": fid,
        "severity": severity,
        "axis": axis,
        "title": title,
        "evidence": evidence,
        "why": why,
        "fix": fix,
        "penalty": SEVERITY_PENALTY[severity],
    }


def _names(ex: Exchange, ids) -> str:
    return ", ".join(ex.name_of(i) for i in ids)


def _fmt_date(d: Optional[_dt.date]) -> str:
    return d.isoformat() if d else "not set"


def _verdict_for(score: float):
    for threshold, key, label in VERDICT_BANDS:
        if score >= threshold:
            return key, label
    return VERDICT_BANDS[-1][1], VERDICT_BANDS[-1][2]


def review(
    ex: Exchange,
    assignment: Optional[dict] = None,
    solve: Optional[SolveResult] = None,
    history_pairs=(),
    today: Optional[_dt.date] = None,
) -> dict:
    """Score an exchange and return the full review report."""
    today = today or TODAY
    assignment = assignment or {}
    history = [tuple(p) for p in history_pairs]
    history_set = {pair_key(a, b) for a, b in history}
    if solve is None:
        # Always know whether the rules are satisfiable, even before a draw is run.
        solve = solve_assignment(ex, history_pairs=history)
    findings: list[dict] = []
    pmap = ex.by_id()
    ids = [p.id for p in ex.participants]

    # ---------------------------------------------------------------- setup
    if not ex.participants:
        findings.append(
            _finding(
                "no_participants", "critical", "setup",
                "Nobody is on the list",
                "The exchange has 0 participants.",
                "A draw needs at least two people, one to give and one to receive.",
                "Add the participants (or paste a brief with a [Participants] section).",
            )
        )
    elif len(ex.participants) < 3:
        findings.append(
            _finding(
                "too_few_participants", "high", "setup",
                "Only %d participants" % len(ex.participants),
                "participants: %s" % _names(ex, ids),
                "With two people the draw is forced and the exchange is not much of an event.",
                "Add at least one more person, or accept that the draw is a formality.",
            )
        )

    seen_names: dict[str, list[str]] = {}
    seen_emails: dict[str, list[str]] = {}
    for p in ex.participants:
        key = p.name.strip().lower()
        if key:
            seen_names.setdefault(key, []).append(p.id)
        mail = p.email.strip().lower()
        if mail:
            seen_emails.setdefault(mail, []).append(p.id)

    for name, group in seen_names.items():
        if len(group) > 1:
            findings.append(
                _finding(
                    "duplicate_name", "high", "setup",
                    "Two people share the name '%s'" % pmap[group[0]].name,
                    "participants: %s" % _names(ex, group),
                    "The draw, the reveal page and the gift list all key off names, so duplicates "
                    "make it impossible to tell who bought what.",
                    "Give each participant a unique display name or an email address.",
                )
            )

    for mail, group in seen_emails.items():
        if len(group) > 1:
            findings.append(
                _finding(
                    "duplicate_email", "high", "setup",
                    "Two people share the email '%s'" % mail,
                    "participants: %s" % _names(ex, group),
                    "The same address means one person can open both reveal codes and see the "
                    "whole pairing.",
                    "Use one address per participant, or leave the email blank.",
                )
            )

    no_email = [p.id for p in ex.participants if not p.email.strip()]
    if no_email and ex.participants:
        findings.append(
            _finding(
                "missing_email", "medium", "setup",
                "%d participant(s) have no email" % len(no_email),
                "no email: %s" % _names(ex, no_email[:6]),
                "Without an address you cannot send the reveal code, so people find out late - "
                "or not at all.",
                "Add an email address, or hand the access code out by hand.",
            )
        )

    if ex.no_same_household:
        no_household = [p.id for p in ex.participants if not p.household.strip()]
        if no_household:
            findings.append(
                _finding(
                    "missing_household", "medium", "setup",
                    "%d participant(s) have no household" % len(no_household),
                    "no household: %s" % _names(ex, no_household[:6]),
                    "Households are what stop partners and siblings drawing each other. "
                    "Without one, the draw can put two people from the same home in each other's "
                    "shoes.",
                    "Set a household for every participant, or turn the household rule off.",
                )
            )
        households: dict[str, list[str]] = {}
        for p in ex.participants:
            if p.household.strip():
                households.setdefault(p.household.strip(), []).append(p.id)
        lonely = [h for h, members in households.items() if len(members) == 1]
        if lonely:
            findings.append(
                _finding(
                    "single_member_household", "low", "setup",
                    "%d household(s) have one member" % len(lonely),
                    "households: %s" % ", ".join(sorted(lonely)),
                    "A one-person household does nothing - the rule only matters for pairs and "
                    "families.",
                    "Merge it into the right household, or leave the field empty.",
                )
            )

    no_code = [p.id for p in ex.participants if not p.access_code.strip()]
    if no_code:
        findings.append(
            _finding(
                "missing_access_code", "high", "setup",
                "%d participant(s) have no access code" % len(no_code),
                "no code: %s" % _names(ex, no_code[:6]),
                "The access code is how one person sees their own pairing without seeing "
                "everyone else's. Without it you have to publish the whole list.",
                "Generate access codes for every participant.",
            )
        )

    code_hits: dict[str, list[str]] = {}
    for p in ex.participants:
        code = p.access_code.strip().upper()
        if code:
            code_hits.setdefault(code, []).append(p.id)
    for code, group in code_hits.items():
        if len(group) > 1:
            findings.append(
                _finding(
                    "duplicate_access_code", "high", "setup",
                    "Access code '%s' is used %d times" % (code, len(group)),
                    "participants: %s" % _names(ex, group),
                    "Two people with the same code both see the same reveal page.",
                    "Regenerate the code for one of them.",
                )
            )

    if not ex.exchange_date:
        findings.append(
            _finding(
                "missing_exchange_date", "critical", "setup",
                "No exchange date",
                "exchange_date: not set",
                "The exchange date is what every other date is measured from - draw, shopping "
                "deadline and shipping buffer.",
                "Set the date the gifts are exchanged.",
            )
        )
    if not ex.draw_date:
        findings.append(
            _finding(
                "missing_draw_date", "high", "setup",
                "No draw date",
                "draw_date: not set",
                "Without a draw date the participants cannot plan, and the shopping window has "
                "no start.",
                "Set the date the draw happens.",
            )
        )
    if not ex.shopping_deadline:
        findings.append(
            _finding(
                "missing_shopping_deadline", "medium", "timeline",
                "No shopping deadline",
                "shopping_deadline: not set",
                "A deadline is what stops the gift being bought two days before the exchange.",
                "Set the date everyone should have bought their gift by.",
            )
        )

    no_wishes = [p.id for p in ex.participants if not p.wishes]
    if no_wishes and ex.participants:
        findings.append(
            _finding(
                "no_wishlist", "low", "setup",
                "%d participant(s) have no wishlist" % len(no_wishes),
                "no wishes: %s" % _names(ex, no_wishes[:6]),
                "Without a wishlist the person drawing them has to guess, and guesses are how a "
                "40 dollar gift becomes a 9 dollar one.",
                "Ask everyone for two or three ideas, even if they only want a category.",
            )
        )

    # ----------------------------------------------------------- constraints
    if solve is not None and not solve.ok:
        findings.append(
            _finding(
                "unsatisfiable", "critical", "constraints",
                "No valid draw exists under the current rules",
                "; ".join(solve.notes) or "The constraint set has no solution.",
                "Every participant must give to exactly one person and receive exactly one "
                "gift. If the rules make that impossible, the draw simply cannot run.",
                "Relax a rule - the suggestions below name the smallest change that works.",
            )
        )
        if solve.blocked_groups:
            for group in solve.blocked_groups:
                findings.append(
                    _finding(
                        "blocked_group", "critical", "constraints",
                        "A closed group cannot all draw out",
                        "blocked: %s" % _names(ex, group),
                        "These participants can only draw inside the group, and there are not "
                        "enough people inside it to go round. It is the classic Hall violation.",
                        "Add people from outside the group, merge the group into a bigger "
                        "exchange, or allow the blocked pairings.",
                    )
                )
        if solve.zero_candidate:
            findings.append(
                _finding(
                    "zero_candidate", "critical", "constraints",
                    "%d participant(s) can draw nobody" % len(solve.zero_candidate),
                    "no candidates: %s" % _names(ex, solve.zero_candidate),
                    "Everyone else is excluded for them - a self draw, a household member, a "
                    "history pair or an explicit exclusion.",
                    "Remove the exclusion that blocks them, or add another participant.",
                )
            )
        if solve.repeat_pairs:
            findings.append(
                _finding(
                    "repeat_pairs_forced", "high", "constraints",
                    "%d pairing(s) would repeat a previous year" % len(solve.repeat_pairs),
                    "repeats: %s"
                    % ", ".join(
                        "%s -> %s" % (ex.name_of(a), ex.name_of(b))
                        for a, b in solve.repeat_pairs
                    ),
                    "Repeating a pair is usually fine in a small circle, but it is the rule the "
                    "organiser said they wanted.",
                    "Use one of the relaxations below, or accept the repeat and say so.",
                )
            )

    known_ids = set(ids)
    for a, b in ex.exclusions:
        if a not in known_ids or b not in known_ids:
            findings.append(
                _finding(
                    "exclusion_unknown", "medium", "constraints",
                    "An exclusion names somebody who is not on the list",
                    "exclusion: %s / %s" % (a, b),
                    "An exclusion for a person who is not participating silently does nothing, "
                    "which usually means a typo or a person who dropped out.",
                    "Remove the stale exclusion or add the participant back.",
                )
            )
        elif a == b:
            findings.append(
                _finding(
                    "exclusion_self", "medium", "constraints",
                    "Somebody is excluded from drawing themselves",
                    "exclusion: %s / %s" % (ex.name_of(a), ex.name_of(b)),
                    "Nobody draws themselves anyway - the rule is built in - so this exclusion "
                    "is dead weight that makes the constraint set harder to reason about.",
                    "Delete it.",
                )
            )

    if len(ids) >= 6:
        for p in ex.participants:
            blocked = sum(
                1
                for q in ex.participants
                if q.id != p.id and pair_key(p.id, q.id) in {
                    pair_key(a, b) for a, b in ex.exclusions
                }
            )
            if blocked >= max(2, int(0.6 * (len(ids) - 1))):
                findings.append(
                    _finding(
                        "over_excluded", "medium", "constraints",
                        "%s excludes most of the group" % p.name,
                        "excluded: %d of %d other participants" % (blocked, len(ids) - 1),
                        "Once a person is excluded from most of the circle, the draw becomes "
                        "fragile and usually ends in a forced repeat.",
                        "Drop the least important exclusions for this person.",
                    )
                )

    households_all: dict[str, list[str]] = {}
    for p in ex.participants:
        if p.household.strip():
            households_all.setdefault(p.household.strip(), []).append(p.id)
    if ex.no_same_household and len(households_all) <= 1 and ex.participants:
        findings.append(
            _finding(
                "household_rule_ineffective", "low", "constraints",
                "The household rule does nothing here",
                "households: %d" % len(households_all),
                "If everyone is in one household, or nobody is, the rule cannot block a single "
                "pairing.",
                "Set households so the rule can do its job, or turn it off.",
            )
        )
    if ex.no_same_group and not any(p.groups for p in ex.participants):
        findings.append(
            _finding(
                "group_rule_ineffective", "low", "constraints",
                "The group rule is on but nobody is in a group",
                "no_same_group: on, groups: none",
                "Without group tags the rule blocks nothing.",
                "Tag the book club, the choir or the team, or turn the rule off.",
            )
        )

    if assignment:
        missing_givers = [i for i in ids if i not in assignment]
        missing_receivers = [i for i in ids if i not in set(assignment.values())]
        if missing_givers or missing_receivers:
            findings.append(
                _finding(
                    "partial_assignment", "high", "constraints",
                    "The saved draw does not cover everybody",
                    "without a gift: %s; without a giver: %s"
                    % (_names(ex, missing_receivers), _names(ex, missing_givers)),
                    "A partial draw leaves someone out of the exchange with no way to tell it "
                    "happened.",
                    "Re-run the draw.",
                )
            )
        self_hits = [
            g for g, r in assignment.items() if g == r
        ]
        if self_hits:
            findings.append(
                _finding(
                    "self_assignment", "critical", "constraints",
                    "Somebody is assigned to themselves",
                    "self-draw: %s" % _names(ex, self_hits),
                    "A self draw is the one outcome that breaks the exchange completely.",
                    "Re-run the draw - the solver never produces this.",
                )
            )
    elif ex.participants:
        findings.append(
            _finding(
                "draw_not_run", "high", "constraints",
                "No draw has been run yet",
                "assignment: empty",
                "Everything else in this review assumes a draw exists - the dates, the budget and "
                "the fairness checks are all about the draw you are about to run.",
                "Run the draw once the participant list and rules look right.",
            )
        )

    # -------------------------------------------------------------- timeline
    if ex.draw_date and ex.exchange_date:
        if ex.draw_date > ex.exchange_date:
            findings.append(
                _finding(
                    "draw_after_exchange", "critical", "timeline",
                    "The draw happens after the exchange",
                    "draw: %s, exchange: %s"
                    % (_fmt_date(ex.draw_date), _fmt_date(ex.exchange_date)),
                    "Nobody can buy a gift for an exchange that already happened.",
                    "Move the draw date earlier than the exchange date.",
                )
            )
        elif ex.draw_date == ex.exchange_date:
            findings.append(
                _finding(
                    "same_day_draw", "high", "timeline",
                    "The draw and the exchange are on the same day",
                    "draw: %s, exchange: %s"
                    % (_fmt_date(ex.draw_date), _fmt_date(ex.exchange_date)),
                    "Same-day gives people no time to buy or ship anything.",
                    "Give the draw at least a week before the exchange.",
                )
            )
        window = (ex.exchange_date - ex.draw_date).days
        if window < ex.shipping_days:
            findings.append(
                _finding(
                    "shipping_window_too_short", "high", "timeline",
                    "Not enough time to buy and ship",
                    "window: %d days, shipping buffer: %d days"
                    % (window, ex.shipping_days),
                    "The window between the draw and the exchange is shorter than the shipping "
                    "buffer, so gifts bought on draw day cannot arrive on time.",
                    "Move the draw earlier, move the exchange later, or drop the shipping "
                    "buffer if everyone is bringing their gift in person.",
                )
            )
        if window >= 0 and 0 < window < 7:
            findings.append(
                _finding(
                    "shopping_window_tight", "medium", "timeline",
                    "Only %d day(s) to shop" % window,
                    "draw: %s, exchange: %s"
                    % (_fmt_date(ex.draw_date), _fmt_date(ex.exchange_date)),
                    "Under a week is tight for buying and posting a gift.",
                    "Move the exchange out by a few days if you can.",
                )
            )

    if ex.shopping_deadline and ex.exchange_date and ex.shopping_deadline > ex.exchange_date:
        findings.append(
            _finding(
                "shopping_after_exchange", "critical", "timeline",
                "The shopping deadline is after the exchange",
                "shopping: %s, exchange: %s"
                % (_fmt_date(ex.shopping_deadline), _fmt_date(ex.exchange_date)),
                "Gifts bought after the exchange arrive after the party.",
                "Move the shopping deadline before the exchange date.",
            )
        )
    if ex.draw_date and ex.shopping_deadline:
        shop_days = (ex.shopping_deadline - ex.draw_date).days
        if 0 <= shop_days < 7:
            findings.append(
                _finding(
                    "short_shopping_deadline", "medium", "timeline",
                    "Only %d day(s) between the draw and the shopping deadline" % shop_days,
                    "draw: %s, shopping: %s"
                    % (_fmt_date(ex.draw_date), _fmt_date(ex.shopping_deadline)),
                    "That is not enough time to order anything that has to be shipped.",
                    "Give people at least a week, or set a shipping deadline instead of a "
                    "shopping deadline.",
                )
            )

    if ex.exchange_date and ex.exchange_date < today:
        findings.append(
            _finding(
                "exchange_in_past", "critical", "timeline",
                "The exchange date has already passed",
                "exchange: %s, today: %s" % (_fmt_date(ex.exchange_date), today.isoformat()),
                "The whole plan is in the past, so every date-based check below is meaningless.",
                "Roll the dates forward to next year, or close the exchange and archive it.",
            )
        )
    if ex.draw_date and ex.draw_date < today:
        findings.append(
            _finding(
                "draw_in_past", "high", "timeline",
                "The draw date has already passed",
                "draw: %s, today: %s" % (_fmt_date(ex.draw_date), today.isoformat()),
                "Either the draw already happened and was never recorded, or the date needs "
                "moving.",
                "Record the draw that already happened, or move the draw date.",
            )
        )
    if ex.exchange_date and ex.shipping_days <= 0:
        findings.append(
            _finding(
                "no_shipping_buffer", "medium", "timeline",
                "No shipping buffer set",
                "shipping_days: 0",
                "If any gift is posted rather than handed over, the buffer is what keeps it "
                "arriving on time.",
                "Set the shipping buffer to the real delivery time you expect.",
            )
        )

    # --------------------------------------------------------------- budget
    if ex.budget is None:
        findings.append(
            _finding(
                "no_budget", "medium", "budget",
                "No budget set",
                "budget: not set",
                "Without a cap, people guess what to spend and the expensive gift sets the tone "
                "for everybody else.",
                "Set a per-person budget and say what it covers.",
            )
        )
    else:
        over_wishes: list[str] = []
        for p in ex.participants:
            for w in p.wishes:
                if w.price is not None and w.price > ex.budget:
                    over_wishes.append("%s wants %s (%.2f)" % (p.name, w.item, w.price))
        if over_wishes:
            findings.append(
                _finding(
                    "wish_over_budget", "medium", "budget",
                    "%d wishlist price(s) are above the budget" % len(over_wishes),
                    "; ".join(over_wishes[:5]),
                    "The person drawing them either breaks the cap or has to buy something the "
                    "recipient will not want.",
                    "Either raise the cap or add a cheaper first choice to the wishlist.",
                )
            )
        over_purchases: list[str] = []
        total_spend = 0.0
        for p in ex.participants:
            for gift, price in (p.purchased or {}).items():
                total_spend += float(price)
                if ex.budget is not None and float(price) > ex.budget:
                    over_purchases.append(
                        "%s bought %s for %.2f" % (p.name, gift, float(price))
                    )
        if over_purchases:
            findings.append(
                _finding(
                    "purchase_over_budget", "high", "budget",
                    "%d purchase(s) are over the budget" % len(over_purchases),
                    "; ".join(over_purchases[:5]),
                    "The spend has already broken the cap that everybody agreed to.",
                    "Swapping for something cheaper is easier now than explaining it later.",
                )
            )

    # ------------------------------------------------------------- fairness
    if ex.allow_reveal_early:
        findings.append(
            _finding(
                "reveal_early", "medium", "fairness",
                "The reveal is open to everyone now",
                "allow_reveal_early: on",
                "In a Secret Santa the whole point is that nobody knows the pairing until the "
                "gift is in hand.",
                "Turn early reveal off so participants see only their own code.",
            )
        )
    if ex.avoid_repeats and not history:
        findings.append(
            _finding(
                "no_history_to_compare", "low", "fairness",
                "There is no previous exchange to compare against",
                "circle: %s" % (ex.circle or "not set"),
                "The no-repeat rule needs a previous draw in the same circle to work against.",
                "Set the circle name so next year's exchange can avoid this year's pairings.",
            )
        )
    if assignment and history_set:
        repeats = [
            (g, r) for g, r in assignment.items() if pair_key(g, r) in history_set
        ]
        if repeats:
            findings.append(
                _finding(
                    "history_repeat_in_draw", "high", "fairness",
                    "%d pairing(s) repeat a previous exchange" % len(repeats),
                    "; ".join(
                        "%s -> %s" % (ex.name_of(a), ex.name_of(b)) for a, b in repeats
                    ),
                    "These two drew each other before.",
                    "Re-run the draw or drop the specific no-repeat rule for that pair.",
                )
            )

    # ------------------------------------------------------------- scoring
    axis_penalty: dict[str, float] = {key: 0.0 for key, _, _ in AXES}
    for f in findings:
        axis_penalty[f["axis"]] = axis_penalty.get(f["axis"], 0.0) + f["penalty"]

    axis_scores = {
        key: max(0.0, 100.0 - axis_penalty.get(key, 0.0)) for key, _, _ in AXES
    }

    caps: list[dict] = []

    def cap(axis: Optional[str], value: float, reason: str) -> None:
        if axis is not None:
            axis_scores[axis] = min(axis_scores[axis], value)
        caps.append({"axis": axis or "overall", "cap": value, "reason": reason})

    ids_set = set(ids)
    if not ids:
        cap(None, 10.0, "An exchange with no participants cannot be ready.")
    if len(ids) < 3:
        cap(None, 30.0, "Fewer than three participants cannot be a real draw.")
    if not ex.exchange_date:
        cap("timeline", 25.0, "No exchange date means no timeline to be ready for.")
        cap(None, 45.0, "No exchange date means no timeline to be ready for.")
    if ex.draw_date and ex.exchange_date and ex.draw_date > ex.exchange_date:
        cap("timeline", 20.0, "The draw happens after the exchange.")
        cap(None, 35.0, "The draw happens after the exchange.")
    if solve is not None and not solve.ok:
        cap("constraints", 25.0, "There is no valid draw under the current rules.")
        cap(None, 30.0, "There is no valid draw under the current rules.")
    if no_code:
        cap("fairness", 40.0, "Without access codes the pairing cannot stay private.")
        cap(None, 60.0, "Without access codes the pairing cannot stay private.")
    if any(f["id"] == "shipping_window_too_short" for f in findings):
        cap("timeline", 35.0, "There is not enough time to buy and ship the gift.")
        cap(None, 55.0, "There is not enough time to buy and ship the gift.")
    if any(f["id"] == "purchase_over_budget" for f in findings):
        cap("budget", 35.0, "The spend is already over the agreed cap.")
        cap(None, 55.0, "The spend is already over the agreed cap.")
    if any(f["id"] == "history_repeat_in_draw" for f in findings):
        cap("fairness", 45.0, "A pairing repeats a previous exchange.")
        cap(None, 60.0, "A pairing repeats a previous exchange.")
    if any(f["id"] == "self_assignment" for f in findings):
        cap(None, 20.0, "A self draw breaks the exchange.")

    overall = sum(axis_scores[key] * AXIS_WEIGHTS[key] for key, _, _ in AXES)
    overall = min(overall, min([c["cap"] for c in caps if c["axis"] == "overall"], default=100.0))
    overall = max(0.0, min(100.0, overall))

    verdict, verdict_label = _verdict_for(overall)

    axes_out = [
        {
            "key": key,
            "label": label,
            "weight": AXIS_WEIGHTS[key],
            "score": round(axis_scores[key], 1),
            "penalty": round(axis_penalty.get(key, 0.0), 1),
        }
        for key, label, _ in AXES
    ]

    findings.sort(key=lambda f: (SEVERITY_RANK[f["severity"]], -f["penalty"], f["id"]))
    fix_plan = [
        {
            "id": f["id"],
            "severity": f["severity"],
            "axis": f["axis"],
            "axis_label": AXIS_LABELS.get(f["axis"], f["axis"]),
            "title": f["title"],
            "fix": f["fix"],
            "gain": round(
                min(f["penalty"], max(0.0, 100.0 - axis_scores.get(f["axis"], 0.0))),
                1,
            ),
        }
        for f in findings
    ]

    total_spend = 0.0
    for p in ex.participants:
        for price in (p.purchased or {}).values():
            total_spend += float(price)

    summary = {
        "participants": len(ex.participants),
        "exclusions": len(ex.exclusions),
        "assigned": len(assignment),
        "budget": ex.budget,
        "spend": round(total_spend, 2),
        "days_to_exchange": (
            (ex.exchange_date - today).days if ex.exchange_date else None
        ),
        "shopping_window_days": (
            (ex.exchange_date - ex.draw_date).days
            if ex.exchange_date and ex.draw_date
            else None
        ),
        "critical": sum(1 for f in findings if f["severity"] == "critical"),
        "high": sum(1 for f in findings if f["severity"] == "high"),
        "medium": sum(1 for f in findings if f["severity"] == "medium"),
        "low": sum(1 for f in findings if f["severity"] == "low"),
        "caps": caps,
        "relaxations": (solve.relaxations if solve is not None else []),
    }

    return {
        "score": round(overall, 1),
        "verdict": verdict,
        "verdict_label": verdict_label,
        "axes": axes_out,
        "findings": findings,
        "fix_plan": fix_plan,
        "summary": summary,
        "generated_for": today.isoformat(),
    }
