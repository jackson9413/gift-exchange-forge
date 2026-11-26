"""Gift Exchange Forge - command line interface.

    python3 cli.py --brief brief.txt --format md
    python3 cli.py --sample family_christmas --format json
    python3 cli.py --brief brief.txt --draw

Exit codes: 0 ready, 1 findings above the threshold, 2 usage or parse error.
"""

from __future__ import annotations

import argparse
import json
import sys

import exporters
import samples
from briefparse import parse_brief
from engine import solve_assignment
from rules import review


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gift-exchange-forge",
        description="Plan a Secret Santa style gift exchange and score how ready it is.",
    )
    parser.add_argument("--brief", help="path to a brief file")
    parser.add_argument("--sample", help="load a built-in sample by id")
    parser.add_argument(
        "--format",
        default="md",
        choices=["md", "csv", "ics", "json", "sheet"],
        help="output format (default: md)",
    )
    parser.add_argument("--draw", action="store_true", help="also run the draw")
    parser.add_argument(
        "--fail-under",
        type=float,
        default=0.0,
        help="exit 1 when the readiness score is below this value",
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    warnings = []
    history = []
    if args.sample:
        try:
            ex, warnings, history = samples.build_sample(args.sample)
        except KeyError:
            sys.stderr.write("gift-exchange-forge: unknown sample '%s'\n" % args.sample)
            return 2
    elif args.brief:
        try:
            with open(args.brief, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError as exc:
            sys.stderr.write("gift-exchange-forge: cannot read brief: %s\n" % exc)
            return 2
        ex, warnings = parse_brief(text, exchange_id="cli")
    else:
        parser.print_help(sys.stderr)
        sys.stderr.write("gift-exchange-forge: need --brief or --sample\n")
        return 2

    solve = None
    assignment = {}
    if args.draw:
        solve = solve_assignment(ex, history_pairs=history, seed=7)
        if solve.ok:
            assignment = solve.assignment

    report = review(ex, assignment=assignment, solve=solve, history_pairs=history)

    if args.format == "json":
        print(exporters.to_json(ex, report, assignment, warnings))
    elif args.format == "csv":
        print(exporters.to_csv(ex, assignment))
    elif args.format == "ics":
        print(exporters.to_ics(ex, assignment))
    elif args.format == "sheet":
        print(exporters.to_participant_sheet(ex, assignment))
    else:
        print(exporters.to_markdown(ex, report, assignment, warnings))

    if solve is not None and not solve.ok:
        sys.stderr.write("gift-exchange-forge: no valid draw under the current rules\n")
        for note in solve.notes:
            sys.stderr.write("  - %s\n" % note)
        for fix in solve.relaxations:
            sys.stderr.write("  - %s\n" % fix)
        return 1

    if report["score"] < args.fail_under:
        sys.stderr.write(
            "gift-exchange-forge: score %.1f is below %.1f\n"
            % (report["score"], args.fail_under)
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
