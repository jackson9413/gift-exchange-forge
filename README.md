# Gift Exchange Forge

A local-first workbench for running a Secret Santa style gift exchange.

Paste a brief (or build the roster by hand), run a constraint-checked draw, get a
0-100 readiness score that says what is still broken, and hand each participant a
six character code that reveals only their own pairing.

No API keys. No network calls. No LLM. Standard library engine, Flask for the
web app, vanilla JS for the front end.

## Why it exists

Secret Santa fails in the same three places every year:

1. **The draw is impossible.** Six people in two households of four and two cannot
   be paired without somebody drawing their partner. The usual fix is a group chat
   and a lot of guessing.
2. **Nobody repeats a pair, so nobody remembers who they drew last year.**
3. **The reveal leaks.** One person sees the whole list, or the whole list gets
   posted, and the surprise is gone.

Gift Exchange Forge solves the pairing properly (bipartite matching with real
diagnostics), scores the exchange for the things that quietly break it (dates,
shipping buffer, budget, wishlists, privacy), and keeps each participant's
pairing private behind their own access code.

## What it does

- **Paste a brief** - a plain text brief with `[Exchange]`, `[Participants]`,
  `[Exclude]` and `[Wishlist]` sections becomes a full exchange in one step.
  Unknown lines become warnings, not crashes.
- **Constraint-checked draw** - everyone gives to exactly one person and receives
  exactly one gift. Nobody draws themselves, nobody draws a household member,
  nobody draws someone they excluded, and no pairing repeats a previous exchange
  in the same circle.
- **Honest failure** - when no valid draw exists the engine says why: which
  people have no candidates at all, which closed group cannot draw out (a Hall
  violation), and the smallest change that makes the draw possible
  ("drop the no-repeat rule between Ana and Dana", "remove the exclusion
  between X and Y", "allow same-household draws").
- **0-100 readiness score** across five axes (setup completeness, constraint
  integrity, timeline feasibility, budget coherence, privacy and fairness) with
  structural caps, so an exchange cannot score well while the part that breaks
  the draw is missing.
- **Every finding carries its evidence**, why it matters, and a concrete fix,
  plus a prioritised fix plan ordered by severity.
- **Privacy by access code** - a six character code per participant shows that
  person their pairing, the dates and the recipient's wishlist, and nothing else.
- **Wishlists and spend tracking** - record what each person wants and what was
  bought, then see spend against the cap.
- **Exports** - Markdown plan, CSV roster, ICS calendar (draw, shopping deadline
  and exchange date, with reminders), JSON bundle and a printable participant
  cheat sheet.
- **Run log** - log each exchange with a 1-5 star rating and notes.

## Run it

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python3 app.py

Then open <http://127.0.0.1:5001>.

The SQLite database is created at `data/gift_exchange.db` on first run. Point
`GIFT_EXCHANGE_DB` somewhere else to keep it out of the way.

## Command line

    python3 cli.py --brief brief.txt --format md
    python3 cli.py --sample family_christmas --format json
    python3 cli.py --sample impossible_households --draw

Exit codes: `0` success, `1` findings (or no valid draw), `2` usage or parse error.
`--fail-under 90` turns the readiness score into a CI gate.

## Brief format

    [Exchange]
    name: Alvarez Family Christmas
    budget: 80
    draw: 2026-12-01
    shopping: 2026-12-15
    exchange: 2026-12-24
    shipping: 5
    circle: alvarez-family
    avoid_repeats: yes
    no_same_household: yes

    [Participants]
    Rosa Alvarez | rosa@example.com | Alvarez
    Miguel Alvarez | miguel@example.com | Alvarez
    Wei Chen | wei@example.com | Chen

    [Exclude]
    Rosa Alvarez | Elena Alvarez

    [Wishlist]
    Sofia Alvarez | Skateboard | 65.00 | size M

Participant lines are `name | email | household | group`. Wishlist lines are
`name | item | price | note`. The circle name is what links this year's exchange
to last year's pairings.

## Built-in samples

| id | scenario | expected verdict |
| --- | --- | --- |
| family_christmas | 8 people, 3 households, comfortable timeline | ready_to_draw |
| office_polite | 10 coworkers, three exclusions, 40 dollar cap | ready_to_draw |
| tight_shipping | draw and exchange four days apart, seven day shipping buffer | needs_work |
| impossible_households | household of four and household of two | not_ready |
| missing_setup | no emails, codes, wishes, budget or dates | needs_work |
| repeat_year | the only valid pairing repeats last year's draw | not_ready |

## Tests

    python3 -m unittest discover -s tests

67 tests: engine (parser, solver, rules, exporters, samples), API (Flask test
client) and a front end contract test that keeps the markup and the script in
agreement.

## Layout

    app.py          Flask app and REST API
    engine.py       data model and the constraint solver
    rules.py        review rules, scoring and structural caps
    briefparse.py   brief text parser
    exporters.py    Markdown, CSV, ICS and JSON exporters
    storage.py      SQLite storage
    samples.py      six built-in scenarios
    cli.py          command line interface
    static/         vanilla JS front end
    tests/          engine, API and front end tests

## Privacy

Everything stays on your machine. The database is a local SQLite file, there are
no outbound requests, and no data is sent anywhere. Access codes are six
characters from an unambiguous alphabet (no I, O, 0 or 1).

## License

MIT
