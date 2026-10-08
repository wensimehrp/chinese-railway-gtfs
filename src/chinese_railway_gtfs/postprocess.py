"""Decode the SQLite file written by railgo's exporter into JSON.

``MongoSQLiteExporter.export()`` stores the list-valued fields
(``timetable``, ``rundays``, ``trainList``, ...) as JSON strings. This step
expands them back into plain lists once, so everything downstream works with
normal dicts instead of raw rows. This is the hook for the GTFS build:
``stop_times``, ``trips`` and ``routes`` will be derived from these
``trains`` / ``stations`` lists.

The schema is owned by railgo's exporter, so it is reflected from the database
rather than redeclared here; queries go through SQLAlchemy Core.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, select

from .crawl import DB_DEFAULT

OUT_DEFAULT = Path("data/railgo.json")

TRAIN_JSON = ("numberFull", "diagram", "timetable", "rundays", "route")
STATION_JSON = (
    "telecodeAlias",
    "tmismAlias",
    "sameCityStations",
    "lines",
    "type",
    "trainList",
)
# The model calls it ``sameCityStationList``; the SQLite column is
# ``sameCityStations``.
STATION_RENAME = {"sameCityStations": "sameCityStationList"}


def _loads(value: Any) -> list:
    return json.loads(value) if value is not None else []


def _decode_train(row: Any) -> dict[str, Any]:
    train = dict(row)
    for key in TRAIN_JSON:
        train[key] = _loads(train[key])
    train["spend"] = int(train["spend"] or 0)
    train["isFuxing"] = bool(train["isFuxing"])
    return train


def _decode_station(row: Any) -> dict[str, Any]:
    station = dict(row)
    for key in STATION_JSON:
        station[key] = _loads(station[key])
    for column, key in STATION_RENAME.items():
        station[key] = station.pop(column)
    return station


def read_database(location: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Reflect the exporter's tables and return decoded ``(trains, stations)``."""
    engine = create_engine(f"sqlite:///{location}")
    try:
        metadata = MetaData()
        metadata.reflect(bind=engine, only=("trains", "stations"))
        trains_table: Table = metadata.tables["trains"]
        stations_table: Table = metadata.tables["stations"]
        with engine.connect() as connection:
            trains = [
                _decode_train(row)
                for row in connection.execute(select(trains_table)).mappings()
            ]
            stations = [
                _decode_station(row)
                for row in connection.execute(select(stations_table)).mappings()
            ]
    finally:
        engine.dispose()
    return trains, stations


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("postprocess", help="decode the SQLite file")
    parser.add_argument("--db", type=Path, default=DB_DEFAULT, help="input SQLite path")
    parser.add_argument(
        "--out", type=Path, default=OUT_DEFAULT, help="output JSON path"
    )
    parser.set_defaults(run=run)
    return parser


def run(args: argparse.Namespace) -> None:
    if not args.db.exists():
        raise SystemExit(f"no SQLite file at {args.db}; run `crawl` first")

    trains, stations = read_database(args.db)

    index_trains: dict[str, int] = {}
    for i, train in enumerate(trains):
        for number in train.get("numberFull") or []:
            index_trains[number] = i
    index_stations = {station["telecode"]: i for i, station in enumerate(stations)}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "trains": trains,
                "stations": stations,
                "_index_trains": index_trains,
                "_index_stations": index_stations,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    stops = sum(len(train.get("timetable") or []) for train in trains)
    print(f"trains:   {len(trains)} ({stops} timetable stops)")
    print(f"stations: {len(stations)}")
    print(f"wrote {args.out}")
