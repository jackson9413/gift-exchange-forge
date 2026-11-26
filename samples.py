"""Gift Exchange Forge - built-in sample exchanges.

Six scenarios that exercise the engine end to end. Dates are generated
relative to today so the samples stay meaningful whenever the tool is run.
"""

from __future__ import annotations

import datetime as _dt

from briefparse import parse_brief
from engine import Exchange

TODAY = _dt.date.today()


def _d(days: int) -> str:
    return (TODAY + _dt.timedelta(days=days)).isoformat()


FAMILY = """[Exchange]
name: Alvarez Family Christmas
budget: 80
draw: {draw}
shopping: {shopping}
exchange: {exchange}
shipping: 5
circle: alvarez-family
avoid_repeats: yes

[Participants]
Rosa Alvarez | rosa@example.com | Alvarez
Miguel Alvarez | miguel@example.com | Alvarez
Elena Alvarez | elena@example.com | Alvarez
Sofia Alvarez | sofia@example.com | Alvarez
Wei Chen | wei@example.com | Chen
Lan Chen | lan@example.com | Chen
Chidi Okafor | chidi@example.com | Okafor
Nia Okafor | nia@example.com | Okafor

[Exclude]
Rosa Alvarez | Elena Alvarez
Chidi Okafor | Nia Okafor

[Wishlist]
Rosa Alvarez | Cast iron pan | 48.00 | grey
Miguel Alvarez | Cordless drill | 62.00 | 18V
Elena Alvarez | Cash for a spa day | 70.00 | any Saturday
Sofia Alvarez | Skateboard | 65.00 | size M
Wei Chen | Wireless earbuds | 79.00 | black
Lan Chen | Wool blanket | 55.00 | neutral
Chidi Okafor | Football | 45.00 | size M
Nia Okafor | Cookbook | 28.00 | anything savoury
"""

OFFICE = """[Exchange]
name: Office Secret Santa 2026
budget: 40
draw: {draw}
shopping: {shopping}
exchange: {exchange}
shipping: 6
circle: northwind-office
avoid_repeats: yes

[Participants]
Dana Fields | dana@northwind.example | |
Sam Ortiz | sam@northwind.example | |
Priya Nair | priya@northwind.example | |
Tom Berger | tom@northwind.example | |
Ines Costa | ines@northwind.example | |
Leo Marsh | leo@northwind.example | |
Ruth Kim | ruth@northwind.example | |
Owen Price | owen@northwind.example | |
Maya Stone | maya@northwind.example | |
Bo Tran | bo@northwind.example | |

[Exclude]
Dana Fields | Sam Ortiz
Priya Nair | Tom Berger
Ines Costa | Leo Marsh

[Wishlist]
Dana Fields | Socks and a card | 18.00 |
Sam Ortiz | Coffee beans | 22.00 | dark roast
Priya Nair | Desk plant | 20.00 | low light
Tom Berger | Puzzle | 25.00 | 1000 pieces
Ines Costa | Chocolate | 15.00 |
Leo Marsh | Book | 30.00 | science fiction
Ruth Kim | Candle | 24.00 | unscented
Owen Price | Tote bag | 26.00 |
Maya Stone | Tea set | 38.00 |
Bo Tran | Board game | 35.00 | party game
"""

TIGHT = """[Exchange]
name: Late Deadline Exchange
budget: 35
draw: {draw}
shopping: {shopping}
exchange: {exchange}
shipping: 7
circle: latecomers

[Participants]
Nadia Brooks | nadia@example.com | |
Victor Hahn | victor@example.com | |
Iris Lund | iris@example.com | |
Paul Vo | paul@example.com | |

[Wishlist]
Nadia Brooks | Bath oils | 22.00 |
Victor Hahn | Mug | 14.00 | blue
Iris Lund | Scarf | 30.00 | wool
Paul Vo | Puzzle book | 19.00 |
"""

IMPOSSIBLE = """[Exchange]
name: Two Households
budget: 40
draw: {draw}
shopping: {shopping}
exchange: {exchange}
shipping: 5
circle: kim-patel

[Participants]
Min Kim | min@example.com | Kim
Jun Kim | jun@example.com | Kim
Sol Kim | sol@example.com | Kim
Rae Kim | rae@example.com | Kim
Asha Patel | asha@example.com | Patel
Dev Patel | dev@example.com | Patel
"""

MISSING = """[Exchange]
name: Half Set Up Exchange
notes: organiser still collecting details

[Participants]
Alex Doyle | | |
Robin Shaw | | |
Kim Tran | | |
Lee Park | | |
"""

REPEAT = """[Exchange]
name: The Triad Circle
budget: 30
draw: {draw}
shopping: {shopping}
exchange: {exchange}
shipping: 4
circle: triad

[Participants]
Ana Ruiz | ana@example.com | |
Ben Fox | ben@example.com | |
Cleo Hart | cleo@example.com | |
Dana Vale | dana@example.com | |

[Exclude]
Ana Ruiz | Ben Fox
Ana Ruiz | Cleo Hart
Cleo Hart | Dana Vale
Ben Fox | Dana Vale

[Wishlist]
Ana Ruiz | Candles | 18.00 | unscented
Ben Fox | Game | 28.00 | co-op
Cleo Hart | Tea | 22.00 | loose leaf
Dana Vale | Puzzle | 25.00 |
"""

# id, title, summary, expected verdict, draw offset, shopping offset, exchange offset
SAMPLE_SPECS = [
    (
        "family_christmas",
        "Alvarez family Christmas",
        "8 people, 3 households, an 80 dollar cap and a comfortable timeline. The control case.",
        "ready_to_draw",
        7, 18, 30,
    ),
    (
        "office_polite",
        "Office Secret Santa",
        "10 coworkers with three mutual exclusions and a 40 dollar cap.",
        "ready_to_draw",
        7, 18, 30,
    ),
    (
        "tight_shipping",
        "Late deadline exchange",
        "Draw and exchange four days apart against a seven day shipping buffer.",
        "needs_work",
        1, 3, 5,
    ),
    (
        "impossible_households",
        "Two households",
        "A household of four and a household of two - the draw cannot be satisfied.",
        "not_ready",
        7, 18, 30,
    ),
    (
        "missing_setup",
        "Half set up exchange",
        "No emails, no access codes, no wishes, no budget and no dates.",
        "needs_work",
        7, 18, 30,
    ),
    (
        "repeat_year",
        "Triad circle repeating last year",
        "Four friends whose only valid pairing repeats last year's draw.",
        "not_ready",
        7, 18, 30,
    ),
]

_BRIEFS = {
    "family_christmas": FAMILY,
    "office_polite": OFFICE,
    "tight_shipping": TIGHT,
    "impossible_households": IMPOSSIBLE,
    "missing_setup": MISSING,
    "repeat_year": REPEAT,
}


def _spec(sample_id: str):
    for spec in SAMPLE_SPECS:
        if spec[0] == sample_id:
            return spec
    raise KeyError("unknown sample: %s" % sample_id)


def _render(sample_id: str) -> str:
    spec = _spec(sample_id)
    return _BRIEFS[sample_id].format(
        draw=_d(spec[4]), shopping=_d(spec[5]), exchange=_d(spec[6])
    )


def sample_briefs() -> list[dict]:
    """Every sample with its brief text, ready to paste into the app."""
    out = []
    for spec in SAMPLE_SPECS:
        out.append(
            {
                "id": spec[0],
                "title": spec[1],
                "summary": spec[2],
                "expect": spec[3],
                "brief": _render(spec[0]),
            }
        )
    return out


def build_sample(sample_id: str) -> tuple[Exchange, list[str], list[tuple[str, str]]]:
    """Build a sample exchange. Returns (exchange, warnings, history_pairs)."""
    _spec(sample_id)
    ex, warnings = parse_brief(_render(sample_id), exchange_id=sample_id)

    history: list[tuple[str, str]] = []
    if sample_id == "missing_setup":
        for p in ex.participants:
            p.access_code = ""
        ex.exclusions.append(("nobody", "ghost"))
    if sample_id == "repeat_year":
        # Last year Ana drew Dana; the only valid pairing this year repeats it.
        history = [("ana-ruiz", "dana-vale")]
    return ex, warnings, history


def sample_ids() -> list[str]:
    return [spec[0] for spec in SAMPLE_SPECS]
