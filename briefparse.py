"""Gift Exchange Forge - brief parser.

Turns a pasted text brief into an Exchange. Tolerant by design: unknown lines
become warnings rather than exceptions, so a half-typed brief still loads.

Format:

    [Exchange]
    name: Holiday Secret Santa 2026
    budget: 50
    draw: 2026-12-01
    shopping: 2026-12-15
    exchange: 2026-12-24
    shipping: 5
    circle: family

    [Participants]
    Alice | alice@example.com | Smith | bookclub
    Bob   | bob@example.com   | Smith

    [Exclude]
    Alice | Bob

    [Wishlist]
    Alice | Hiking boots | 89.00 | size 10
"""

from __future__ import annotations

import datetime as _dt
import re

from engine import Exchange, Participant, Wish, _as_date, _as_float, make_access_code, slugify

SECTION_ALIASES = {
    "exchange": "exchange",
    "settings": "exchange",
    "participants": "participants",
    "people": "participants",
    "roster": "participants",
    "exclude": "exclude",
    "excludes": "exclude",
    "exclusions": "exclude",
    "no draw": "exclude",
    "wishlist": "wishlist",
    "wishes": "wishlist",
    "groups": "groups",
}

BOOL_TRUE = {"yes", "y", "true", "1", "on", "enabled"}
BOOL_FALSE = {"no", "n", "false", "0", "off", "disabled"}

EXCHANGE_KEYS = {
    "name": "name",
    "title": "name",
    "budget": "budget",
    "cap": "budget",
    "draw": "draw_date",
    "draw date": "draw_date",
    "shopping": "shopping_deadline",
    "shopping deadline": "shopping_deadline",
    "exchange": "exchange_date",
    "exchange date": "exchange_date",
    "shipping": "shipping_days",
    "shipping days": "shipping_days",
    "shipping buffer": "shipping_days",
    "circle": "circle",
    "notes": "notes",
    "note": "notes",
}


def _split(line: str) -> list[str]:
    return [part.strip() for part in line.split("|")]


def _as_bool(value: str):
    text = str(value).strip().lower()
    if text in BOOL_TRUE:
        return True
    if text in BOOL_FALSE:
        return False
    return None


def parse_brief(text: str, exchange_id: str = "brief") -> tuple[Exchange, list[str]]:
    """Parse a brief into (exchange, warnings)."""
    warnings: list[str] = []
    ex = Exchange(id=exchange_id, name="Secret Santa")
    by_name: dict[str, str] = {}
    taken: set[str] = set()
    section = "exchange"
    pending_exclusions: list[tuple[str, str]] = []
    pending_wishes: list[tuple[str, list[str]]] = []
    pending_groups: list[tuple[str, list[str]]] = []

    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        header = re.match(r"^\[(.+?)\]\s*$", line)
        if header:
            key = header.group(1).strip().lower()
            section = SECTION_ALIASES.get(key, key if key in SECTION_ALIASES else key)
            if section not in ("exchange", "participants", "exclude", "wishlist", "groups"):
                warnings.append("Unknown section '[%s]' was ignored." % header.group(1))
                section = "exchange"
            continue

        if section == "exchange":
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip().lower()
                value = value.strip()
                if key in EXCHANGE_KEYS:
                    field = EXCHANGE_KEYS[key]
                    if field == "name":
                        ex.name = value
                    elif field == "budget":
                        amount = _as_float(value)
                        if amount is None:
                            warnings.append("Budget '%s' is not a number." % value)
                        else:
                            ex.budget = amount
                    elif field == "shipping_days":
                        try:
                            ex.shipping_days = int(float(value))
                        except ValueError:
                            warnings.append("Shipping buffer '%s' is not a number." % value)
                    elif field in ("draw_date", "shopping_deadline", "exchange_date"):
                        parsed = _as_date(value)
                        if parsed is None:
                            warnings.append("%s '%s' is not a date I can read." % (field, value))
                        else:
                            setattr(ex, field, parsed)
                    elif field == "circle":
                        ex.circle = value
                    elif field == "notes":
                        ex.notes = value
                else:
                    lowered = key.replace("_", " ")
                    if lowered in ("avoid repeats", "avoid_repeats"):
                        flag = _as_bool(value)
                        if flag is None:
                            warnings.append("avoid_repeats '%s' is not yes/no." % value)
                        else:
                            ex.avoid_repeats = flag
                    elif lowered in ("no same household", "no_same_household", "household rule"):
                        flag = _as_bool(value)
                        if flag is None:
                            warnings.append("no_same_household '%s' is not yes/no." % value)
                        else:
                            ex.no_same_household = flag
                    elif lowered in ("no same group", "no_same_group", "group rule"):
                        flag = _as_bool(value)
                        if flag is None:
                            warnings.append("no_same_group '%s' is not yes/no." % value)
                        else:
                            ex.no_same_group = flag
                    elif lowered in ("reveal early", "allow reveal early", "allow_reveal_early"):
                        flag = _as_bool(value)
                        if flag is None:
                            warnings.append("allow_reveal_early '%s' is not yes/no." % value)
                        else:
                            ex.allow_reveal_early = flag
                    else:
                        warnings.append("Unknown setting '%s' was ignored." % key)
            else:
                warnings.append("Line '%s' in [Exchange] was ignored." % line)

        elif section == "participants":
            parts = _split(line)
            name = parts[0] if parts else ""
            if not name:
                continue
            email = parts[1] if len(parts) > 1 else ""
            household = parts[2] if len(parts) > 2 else ""
            group = parts[3] if len(parts) > 3 else ""
            pid = slugify(name, taken)
            taken.add(pid)
            groups = [group] if group else []
            participant = Participant(
                id=pid,
                name=name,
                email=email,
                household=household,
                groups=groups,
                access_code=make_access_code(pid + name),
            )
            ex.participants.append(participant)
            by_name[name.strip().lower()] = pid

        elif section == "exclude":
            parts = _split(line)
            if len(parts) < 2:
                warnings.append("Exclusion line '%s' needs two names." % line)
                continue
            pending_exclusions.append((parts[0], parts[1]))

        elif section == "wishlist":
            parts = _split(line)
            if len(parts) < 2:
                warnings.append("Wishlist line '%s' needs a name and an item." % line)
                continue
            price = _as_float(parts[2]) if len(parts) > 2 else None
            note = parts[3] if len(parts) > 3 else ""
            pending_wishes.append((parts[0], [parts[1], price, note]))

        elif section == "groups":
            parts = _split(line)
            if len(parts) < 2:
                warnings.append("Group line '%s' needs a name and a group." % line)
                continue
            pending_groups.append((parts[0], parts[1:]))

    # resolve exclusions
    for a, b in pending_exclusions:
        ida = by_name.get(a.strip().lower())
        idb = by_name.get(b.strip().lower())
        if not ida or not idb:
            missing = a if not ida else b
            warnings.append("Exclusion '%s' names somebody who is not on the list." % missing)
            continue
        ex.exclusions.append((ida, idb))

    # resolve groups
    for name, groups in pending_groups:
        pid = by_name.get(name.strip().lower())
        if not pid:
            warnings.append("Group line for '%s' names somebody who is not on the list." % name)
            continue
        pmap = ex.by_id()
        for g in groups:
            if g and g not in pmap[pid].groups:
                pmap[pid].groups.append(g)

    # resolve wishlists
    for name, payload in pending_wishes:
        pid = by_name.get(name.strip().lower())
        if not pid:
            warnings.append("Wishlist line for '%s' names somebody who is not on the list." % name)
            continue
        item, price, note = payload
        ex.by_id()[pid].wishes.append(Wish(item=item, price=price, note=note))

    # duplicate access codes
    codes: dict[str, int] = {}
    for p in ex.participants:
        codes[p.access_code] = codes.get(p.access_code, 0) + 1
    for p in ex.participants:
        if codes.get(p.access_code, 0) > 1:
            p.access_code = make_access_code(p.id + p.name + "x")

    if not ex.participants:
        warnings.append("No participants found - check the [Participants] section.")
    if ex.exchange_date and ex.draw_date and ex.draw_date > ex.exchange_date:
        warnings.append("The draw date is after the exchange date.")
    if ex.exchange_date and ex.exchange_date < _dt.date.today():
        warnings.append("The exchange date is in the past.")

    return ex, warnings
