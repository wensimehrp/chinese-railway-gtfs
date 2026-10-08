"""Run the railgo-parser pipeline, reusing railgo's own SQLite exporter.

railgo ships two exporters, both backed by a local MongoDB:

* ``MongoJsonExporter``   -- MongoDB -> JSON
* ``MongoSQLiteExporter`` -- MongoDB -> SQLite (the default ``EXPORTER``)

There is no MongoDB-free exporter, so reusing them means running
``mongod`` on 127.0.0.1:27017. The stock pipeline clears the database at the
start of every run (``resetWorks()``), so it does not grow over time.

This command just drives the stock pipeline and points the default
``MongoSQLiteExporter`` at the requested SQLite file. That file is written by
``EXPORTER.export()`` at the end of ``launchMainPipe()``; feed it to
:mod:`chinese_railway_gtfs.postprocess` afterwards.

A full run issues a very large number of HTTP requests (hours), mostly in the
station stage, so there are two ways to keep it small:

* ``--stations N`` caps the (slow) station crawl. Trains then reference
  stations that were never crawled, so the train stage comes out sparse --
  use it to exercise the station stage only.
* ``--seed-stations`` skips the station crawl entirely and seeds the raw 12306
  station list (a single request) instead. That is enough for trains to
  resolve their stops, so it gives quick, meaningful timetables.
"""

from __future__ import annotations

import argparse
import itertools
from collections.abc import Callable, Iterator
from pathlib import Path

DB_DEFAULT = Path("export/railgo.sqlite")


def limited[T](
    gen_factory: Callable[[], Iterator[T]], count: int
) -> Callable[[], Iterator[T]]:
    return lambda: itertools.islice(gen_factory(), count)


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("crawl", help="run the railgo-parser pipeline")
    parser.add_argument(
        "--db", type=Path, default=DB_DEFAULT, help="output SQLite path"
    )
    parser.add_argument(
        "--stations", type=int, default=None, help="cap stations crawled"
    )
    parser.add_argument(
        "--seed-stations",
        action="store_true",
        help="skip the station crawl; seed the raw 12306 station list instead",
    )
    parser.add_argument("--trains", type=int, default=None, help="cap trains crawled")
    parser.set_defaults(run=run)
    return parser


def run(args: argparse.Namespace) -> None:
    from railgo import config
    from railgo.config import resetWorks
    from railgo.parser import pipe
    from railgo.parser.parse import station

    # The stock MongoSQLiteExporter; just redirect its output file.
    exporter = config.EXPORTER
    exporter.export_location = str(args.db)
    args.db.parent.mkdir(parents=True, exist_ok=True)

    if args.seed_stations and args.stations is not None:
        print("--seed-stations overrides --stations")
    elif args.stations is not None:
        print(f"limiting station stage to {args.stations} stations")
        pipe.stationTogether = limited(pipe.stationTogether, args.stations)
    if args.trains is not None:
        print(f"limiting train stage to {args.trains} trains")
        pipe.getTrainList = limited(pipe.getTrainList, args.trains)

    resetWorks()

    if args.seed_stations:
        seeded = 0
        for model in station.getKYFWList():
            exporter.exportStationInfo(model)
            seeded += 1
        print(f"seeded {seeded} stations from the 12306 list")
        pipe.init_stations = lambda: None

    pipe.launchMainPipe()
    print(f"wrote {args.db}")
