"""Enumerate the full train roster once, into ``roster.json``.

The ``discover`` job in .github/workflows/update.yml runs this and publishes
``roster.json`` as an artifact; the crawl shards read that file instead of
each enumerating the roster themselves.

A request that fails (e.g. 12306 rate-limits the runner's IP) raises and fails
this job instead of leaving a silently-truncated roster behind.
"""

import json

from railgo.parser.parse import train

ROSTER = "roster.json"


def main() -> None:
    roster = [
        {"number": inst.number, "code": inst.code, "dataBeginDay": inst._dataBeginDay}
        for inst in train.getTrainList()
    ]

    with open(ROSTER, "w", encoding="utf-8") as handle:
        json.dump(roster, handle)
    print(f"roster: {len(roster)} trains")


if __name__ == "__main__":
    main()
