"""Gift Exchange Forge - exporters.

Markdown plan, CSV roster, ICS calendar and JSON bundle. Standard library only.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import json

from engine import AXIS_LABELS, Exchange


def _fmt_date(d) -> str:
    return d.isoformat() if d else "not set"


def _money(value) -> str:
    if value is None:
        return "-"
    return ("%.2f" % float(value)).rstrip("0").rstrip(".")


def to_markdown(ex: Exchange, report: dict, assignment: dict, warnings=None) -> str:
    warnings = warnings or []
    out = io.StringIO()
    out.write("# %s\n\n" % ex.name)
    out.write(
        "**Verdict:** %s - %.1f / 100  \n" % (report["verdict_label"], report["score"])
    )
    out.write("**Participants:** %d  |  **Circle:** %s  |  **Generated:** %s\n\n" % (
        len(ex.participants),
        ex.circle or "not set",
        report.get("generated_for", _dt.date.today().isoformat()),
    ))

    out.write("## Score by axis\n\n")
    out.write("| Axis | Score | Weight |\n| --- | ---: | ---: |\n")
    for axis in report["axes"]:
        out.write(
            "| %s | %.1f | %d%% |\n"
            % (axis["label"], axis["score"], round(axis["weight"] * 100))
        )
    out.write("\n")

    if report.get("summary", {}).get("caps"):
        out.write("### Structural caps\n\n")
        for c in report["summary"]["caps"]:
            out.write("- **%s** (cap %s): %s\n" % (c["axis"], c["cap"], c["reason"]))
        out.write("\n")

    out.write("## Draw\n\n")
    if assignment:
        out.write("| Giver | Receives | Household of receiver |\n| --- | --- | --- |\n")
        for giver, receiver in assignment.items():
            out.write(
                "| %s | %s | %s |\n"
                % (ex.name_of(giver), ex.name_of(receiver), ex.household_of(receiver) or "-")
            )
    else:
        out.write("_No draw recorded yet._\n")
    out.write("\n")

    out.write("## Dates\n\n")
    out.write("- Draw: %s\n" % _fmt_date(ex.draw_date))
    out.write("- Shopping deadline: %s\n" % _fmt_date(ex.shopping_deadline))
    out.write("- Exchange: %s\n" % _fmt_date(ex.exchange_date))
    out.write("- Shipping buffer: %s day(s)\n" % ex.shipping_days)
    if ex.budget is not None:
        out.write("- Budget cap: $%s\n" % _money(ex.budget))
    out.write("\n")

    out.write("## Findings\n\n")
    if not report["findings"]:
        out.write("_Nothing to fix._\n\n")
    for f in report["findings"]:
        out.write("### [%s] %s\n\n" % (f["severity"].upper(), f["title"]))
        out.write("- **Evidence:** %s\n" % f["evidence"])
        out.write("- **Why it matters:** %s\n" % f["why"])
        out.write("- **Fix:** %s\n\n" % f["fix"])

    out.write("## Fix plan\n\n")
    if not report["fix_plan"]:
        out.write("_Nothing to fix._\n\n")
    for i, step in enumerate(report["fix_plan"], 1):
        out.write(
            "%d. **%s** (%s, %s) - %s\n"
            % (i, step["title"], step["severity"], step["axis_label"], step["fix"])
        )
    out.write("\n")

    if warnings:
        out.write("## Parser warnings\n\n")
        for w in warnings:
            out.write("- %s\n" % w)
        out.write("\n")

    if ex.notes:
        out.write("## Notes\n\n%s\n" % ex.notes)

    return out.getvalue()


def to_csv(ex: Exchange, assignment: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "giver",
            "giver_email",
            "receiver",
            "receiver_email",
            "budget_cap",
            "purchased_gift",
            "purchased_price",
            "draw_date",
            "exchange_date",
        ]
    )
    pmap = ex.by_id()
    for p in ex.participants:
        receiver = assignment.get(p.id, "")
        gift = ""
        price = ""
        for item, value in (p.purchased or {}).items():
            gift = item
            price = ("%.2f" % float(value))
        writer.writerow(
            [
                p.name,
                p.email,
                ex.name_of(receiver) if receiver else "",
                pmap[receiver].email if receiver in pmap else "",
                _money(ex.budget),
                gift,
                price,
                _fmt_date(ex.draw_date),
                _fmt_date(ex.exchange_date),
            ]
        )
    return buf.getvalue()


def _ics_event(uid, dtstart: _dt.date, summary: str, description: str, alarm_days=None) -> str:
    stamp = dtstart.strftime("%Y%m%d")
    end = (dtstart + _dt.timedelta(days=1)).strftime("%Y%m%d")
    lines = [
        "BEGIN:VEVENT",
        "UID:%s@gift-exchange-forge" % uid,
        "DTSTAMP:%sT120000Z" % dtstart.strftime("%Y%m%d"),
        "DTSTART;VALUE=DATE:%s" % stamp,
        "DTEND;VALUE=DATE:%s" % end,
        "SUMMARY:%s" % summary,
        "DESCRIPTION:%s" % description,
    ]
    if alarm_days:
        lines.append("BEGIN:VALARM")
        lines.append("ACTION:DISPLAY")
        lines.append("TRIGGER:-P%dD" % alarm_days)
        lines.append("DESCRIPTION:%s" % summary)
        lines.append("END:VALARM")
    lines.append("END:VEVENT")
    return "\n".join(lines)


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def to_ics(ex: Exchange, assignment: dict) -> str:
    events = []
    if ex.draw_date:
        events.append(
            _ics_event(
                "draw-%s" % ex.id,
                ex.draw_date,
                _escape("Secret Santa draw - %s" % ex.name),
                _escape(
                    "The draw for %s. Check your access code for who you are drawing."
                    % ex.name
                ),
                alarm_days=1,
            )
        )
    if ex.shopping_deadline:
        events.append(
            _ics_event(
                "shop-%s" % ex.id,
                ex.shopping_deadline,
                _escape("Shopping deadline - %s" % ex.name),
                _escape("Buy and ship the gift for %s by today." % ex.name),
                alarm_days=2,
            )
        )
    if ex.exchange_date:
        events.append(
            _ics_event(
                "exchange-%s" % ex.id,
                ex.exchange_date,
                _escape("Gift exchange - %s" % ex.name),
                _escape("Gifts for %s are exchanged today." % ex.name),
                alarm_days=1,
            )
        )
    header = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Gift Exchange Forge//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    footer = ["END:VCALENDAR"]
    return "\n".join(header + events + footer) + "\n"


def to_json(ex: Exchange, report: dict, assignment: dict, warnings=None) -> str:
    payload = {
        "exchange": ex.to_dict(),
        "assignment": [
            {
                "giver": ex.name_of(g),
                "giver_id": g,
                "receiver": ex.name_of(r),
                "receiver_id": r,
            }
            for g, r in assignment.items()
        ],
        "report": report,
        "warnings": list(warnings or []),
    }
    return json.dumps(payload, indent=2, default=str)


def to_participant_sheet(ex: Exchange, assignment: dict) -> str:
    """A per-person cheat sheet for the organiser."""
    out = io.StringIO()
    out.write("%s - participant sheet\n\n" % ex.name)
    pmap = ex.by_id()
    for p in ex.participants:
        receiver = assignment.get(p.id, "")
        out.write(
            "%s  (code %s) buys for %s\n"
            % (p.name, p.access_code or "none", ex.name_of(receiver) if receiver else "not drawn")
        )
        if receiver in pmap:
            wishes = pmap[receiver].wishes
            for w in wishes:
                price = "$%s" % _money(w.price) if w.price is not None else "no price"
                out.write("    - %s (%s)%s\n" % (w.item, price, (" - " + w.note) if w.note else ""))
    return out.getvalue()
