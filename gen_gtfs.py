#!/usr/bin/env -S uv run

# /// script
# requires-python = ">=3.14"
# dependencies = [
#   "pygcj",
#   "tqdm",
# ]
# ///

"""Build a GTFS feed from railgo's SQLite export plus station coordinates.

Reads (from the working directory):
  railgo.sqlite     railgo's MongoSQLiteExporter output (tables ``trains`` and
                    ``stations``). List fields (timetable, rundays, route) are
                    stored as JSON strings.
  coordinates.csv   ``station_name,lon,lat`` (WGS84), sourced from OpenStreetMap.

Writes (into export/):
  export/output_gtfs.zip   the GTFS feed: agency, stops, routes, trips,
                    stop_times, calendar_dates, shapes, feed_info,
                    translations (pinyin station names).
  export/missing_stations.txt / extra_stations.txt / duplicated_stations.txt
                    coordinate gaps, consumed by the coordinate-report issue.

Conventions (see README):
  * ``route_id`` is the train's number (its ``trip_short_name``).
  * Stop times roll past 24:00:00 for stops on the following days.
  * Run days are encoded in calendar_dates.txt (``exception_type=1``); there is
    no calendar.txt, so a service runs exactly on the listed dates.
"""

from __future__ import annotations

import csv
import itertools
import json
import os
import sqlite3
import sys
import tempfile
import time
import zipfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from pygcj.pygcj import GCJProj
from tqdm import tqdm

gcj_proj = GCJProj()


DB_PATH = Path("railgo.sqlite")
COORD_PATH = Path("coordinates.csv")
ZIP_PATH = Path("export/output_gtfs.zip")

AGENCY_ID = "CR"
AGENCY_NAME = "中国国家铁路集团有限公司"
AGENCY_URL = "https://www.12306.cn"
AGENCY_TIMEZONE = "Asia/Shanghai"
ENCODING = "utf-8"
RAIL = 2  # GTFS route_type for rail

# Language tag for the pinyin transliteration used in translations.txt.
PINYIN_LANG = "zh-Latn-pinyin"
# Every station name is translated into these languages; the pinyin is reused
# for English, since a Chinese station's English name is its pinyin.
STOP_NAME_LANGS = (PINYIN_LANG, "en")


def debug(message: str) -> None:
    """Progress output for CI logs; on stderr so stdout stays the result."""
    print(f"[gen_gtfs] {message}", file=sys.stderr)


def _loads(value) -> list:
    """Parse a JSON column, tolerating null or malformed values."""
    if not value:
        return []
    try:
        return json.loads(value)
    except ValueError:
        return []


def load_coordinates(path: Path):
    """Return (coords, duplicates): first ``name -> (lon, lat)`` and clashes."""
    values: dict[str, list[tuple[float, float]]] = defaultdict(list)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("station_name") or "").strip()
            if not name or row.get("lon") is None or row.get("lat") is None:
                continue
            try:
                values[name].append((float(row["lon"]), float(row["lat"])))
            except ValueError:
                continue
    coords = {name: points[0] for name, points in values.items()}
    duplicates = {name: points for name, points in values.items() if len(points) > 1}
    debug(f"coordinates: {len(coords)} station(s) from {path.name}")
    if duplicates:
        debug(f"coordinates: {len(duplicates)} duplicated station name(s)")
    return coords, duplicates


def read_trains(conn: sqlite3.Connection) -> list[dict]:
    """Load every train that can form a trip (>=2 stops and a run-day)."""
    trains = []
    skipped = 0
    total = conn.execute("select count(*) from trains").fetchone()[0]
    rows = conn.execute(
        "select code, number, type, timetable, rundays, route from trains"
    )
    rows = conn.execute("select code, number, timetable, rundays, route from trains")
    for row in tqdm(rows, total=total, desc="reading trains", unit="train"):
        timetable = _loads(row["timetable"])
        rundays = _loads(row["rundays"])
        if len(timetable) < 2 or not rundays:
            skipped += 1
            continue
        trains.append(
            {
                "code": row["code"],
                "number": row["number"],
                "route_id": row["number"],
                "timetable": timetable,
                "rundays": rundays,
                "route_text": row["route"] or "",
            }
        )
    debug(f"trains: {len(trains)} usable, {skipped} skipped (no run-days or <2 stops)")
    return trains


def collect_stop_names(trains: list[dict]) -> dict[str, str]:
    """``telecode -> station name`` for every stop the feed references."""
    names: dict[str, str] = {}
    for train in trains:
        for stop in train["timetable"]:
            names.setdefault(stop["stationTelecode"], stop["station"])
    return names


def collect_stop_pinyin(conn: sqlite3.Connection) -> dict[str, str]:
    """``telecode -> pinyin`` for stations that carry one."""
    return {
        telecode: pinyin
        for telecode, pinyin in conn.execute("select telecode, pinyin from stations")
        if pinyin
    }


def _interpolate(series: list):
    """Fill ``None`` coordinates from the neighbouring known stops in a trip."""
    known = [i for i, value in enumerate(series) if value is not None]
    if not known:
        return series
    result = list(series)
    first, last = known[0], known[-1]
    for i in range(first):
        result[i] = series[first]
    for i in range(last + 1, len(series)):
        result[i] = series[last]
    for a, b in itertools.pairwise(known):
        if b - a <= 1:
            continue
        lon1, lat1 = series[a]
        lon2, lat2 = series[b]
        for step in range(1, b - a):
            t = step / (b - a)
            result[a + step] = (lon1 + (lon2 - lon1) * t, lat1 + (lat2 - lat1) * t)
    return result


def resolve_coordinates(stop_names, coords, trains):
    """``telecode -> (lon, lat)``; interpolate gaps so the feed stays importable."""
    stop_coord = {telecode: coords.get(name) for telecode, name in stop_names.items()}
    for train in trains:
        telecodes = [stop["stationTelecode"] for stop in train["timetable"]]
        filled = _interpolate([stop_coord.get(tc) for tc in telecodes])
        for telecode, value in zip(telecodes, filled):
            if stop_coord.get(telecode) is None and value is not None:
                stop_coord[telecode] = value
    return stop_coord


def gtfs_time(value, day) -> str:
    """``("07:25", 1)`` -> ``"31:25:00"``, so next-day stops stay ordered."""
    parts = str(value or "").split(":")
    hour = int(parts[0]) if parts[0].isdigit() else 0
    minute = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return f"{hour + 24 * int(day or 0):02d}:{minute:02d}:00"


def write_csv(path: Path, header: list[str], rows) -> None:
    with path.open("w", encoding=ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_report(path: Path, lines: list[str]) -> None:
    path.write_text("".join(f"{line}\n" for line in lines), encoding=ENCODING)


def _convert_shape(item):
    """Convert one shape's GCJ-02 points to WGS84 (runs in a worker process)."""
    shape_id, points = item
    return shape_id, [gcj_proj.gcj_to_wgs(point[1], point[0]) for point in points]


def write_shapes(path: Path, shape_points: list[tuple[str, list]]) -> None:
    """Write shapes.txt, converting GCJ-02 -> WGS84 across all CPU cores.

    The conversion is pure-Python CPU work, so it is spread over processes;
    threads would just fight the GIL.
    """
    points = sum(len(shape) for _, shape in shape_points)
    debug(f"shapes: converting {points} point(s) on {os.cpu_count() or 1} core(s)")
    with path.open("w", encoding=ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"]
        )
        if not shape_points:
            return
        with ProcessPoolExecutor() as pool:
            results = pool.map(_convert_shape, shape_points, chunksize=8)
            for shape_id, converted in tqdm(
                results, total=len(shape_points), desc="converting shapes", unit="shape"
            ):
                for seq, (lat, lon) in enumerate(converted, start=1):
                    writer.writerow([shape_id, lat, lon, seq])


def build(
    chosen_dir: Path, trains, stop_names, stop_coord, coords, stop_pinyin
) -> dict:
    """Write the GTFS text files into ``chosen_dir``; return row counts."""
    counts = {}

    write_csv(
        chosen_dir / "agency.txt",
        ["agency_id", "agency_name", "agency_url", "agency_timezone"],
        [[AGENCY_ID, AGENCY_NAME, AGENCY_URL, AGENCY_TIMEZONE]],
    )

    missing = sorted({name for name in stop_names.values() if name not in coords})
    stop_rows = []
    for telecode, name in stop_names.items():
        coord = stop_coord.get(telecode)
        stop_rows.append(
            [
                telecode,
                name,
                f"{coord[1]:.6f}" if coord else "",
                f"{coord[0]:.6f}" if coord else "",
                0,
            ]
        )
    stop_rows.sort()
    write_csv(
        chosen_dir / "stops.txt",
        ["stop_id", "stop_name", "stop_lat", "stop_lon", "location_type"],
        stop_rows,
    )

    route_ids = sorted({train["route_id"] for train in trains})
    write_csv(
        chosen_dir / "routes.txt",
        ["route_id", "agency_id", "route_short_name", "route_type"],
        [[route_id, AGENCY_ID, route_id, RAIL] for route_id in route_ids],
    )
    write_csv(
        chosen_dir / "translations.txt",
        ["table_name", "field_name", "language", "translation", "record_id"],
        [
            ["stops", "stop_name", language, stop_pinyin[stop_id], stop_id]
            for stop_id in stop_names
            if stop_id in stop_pinyin
            for language in STOP_NAME_LANGS
        ],
    )

    service_ids: dict[tuple, str] = {}
    calendar_rows = []
    dates = set()
    shape_ids: dict[str, str] = {}
    shape_points: list[tuple[str, list]] = []

    with (
        (chosen_dir / "trips.txt").open("w", encoding=ENCODING, newline="") as f_trips,
        (chosen_dir / "stop_times.txt").open(
            "w", encoding=ENCODING, newline=""
        ) as f_times,
    ):
        trips = csv.writer(f_trips)
        times = csv.writer(f_times)
        trips.writerow(
            [
                "route_id",
                "service_id",
                "trip_id",
                "trip_short_name",
                "trip_headsign",
                "shape_id",
            ]
        )
        times.writerow(
            ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]
        )

        for train in tqdm(trains, desc="building feed", unit="train"):
            key = tuple(sorted(train["rundays"]))
            service_id = service_ids.get(key)
            if service_id is None:
                service_id = f"S{len(service_ids) + 1}"
                service_ids[key] = service_id
                dates.update(key)
                for day in key:
                    calendar_rows.append([service_id, day, 1])

            shape_id = ""
            text = train["route_text"]
            if text and text not in ("[]", ""):
                shape_id = shape_ids.get(text, "")
                if not shape_id:
                    shape_id = f"shape-{len(shape_ids) + 1}"
                    shape_ids[text] = shape_id
                    shape_points.append((shape_id, json.loads(text)))

            trips.writerow(
                [
                    train["route_id"],
                    service_id,
                    train["code"],
                    train["number"],
                    train["timetable"][-1]["station"],
                    shape_id,
                ]
            )
            for seq, stop in enumerate(train["timetable"], start=1):
                day = stop.get("day", 0)
                times.writerow(
                    [
                        train["code"],
                        gtfs_time(stop.get("arrive"), day),
                        gtfs_time(stop.get("depart"), day),
                        stop["stationTelecode"],
                        seq,
                    ]
                )

    write_shapes(chosen_dir / "shapes.txt", shape_points)

    calendar_rows.sort()
    write_csv(
        chosen_dir / "calendar_dates.txt",
        ["service_id", "date", "exception_type"],
        calendar_rows,
    )

    start = min(dates) if dates else datetime.now(UTC).strftime("%Y%m%d")
    end = max(dates) if dates else start
    write_csv(
        chosen_dir / "feed_info.txt",
        [
            "feed_publisher_name",
            "feed_publisher_url",
            "feed_lang",
            "feed_start_date",
            "feed_end_date",
            "feed_version",
        ],
        [
            [
                AGENCY_NAME,
                AGENCY_URL,
                "zh",
                start,
                end,
                datetime.now(UTC).strftime("%Y%m%d"),
            ]
        ],
    )

    counts.update(
        stops=len(stop_rows),
        routes=len(route_ids),
        trips=len(trains),
        services=len(service_ids),
        shapes=len(shape_ids),
    )
    return {"counts": counts, "dates": dates, "missing": missing}


def main() -> None:
    started = time.perf_counter()
    debug(f"reading {DB_PATH} and {COORD_PATH}")

    coords, duplicates = load_coordinates(COORD_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        trains = read_trains(conn)
        stop_names = collect_stop_names(trains)
        stop_pinyin = collect_stop_pinyin(conn)
    finally:
        conn.close()

    stop_coord = resolve_coordinates(stop_names, coords, trains)
    used_names = set(stop_names.values())
    debug(f"stops: {len(stop_names)} referenced by {len(trains)} train(s)")

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        result = build(out, trains, stop_names, stop_coord, coords, stop_pinyin)

        ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(out.glob("*.txt")):
                archive.write(path, arcname=path.name)
        debug(f"wrote {ZIP_PATH} ({ZIP_PATH.stat().st_size / 1_048_576:.1f} MiB)")

    write_report(
        Path("export/missing_stations.txt"),
        sorted({name for name in result["missing"]}),
    )
    write_report(
        Path("export/extra_stations.txt"),
        sorted(name for name in coords if name not in used_names),
    )
    write_report(Path("export/duplicated_stations.txt"), sorted(duplicates))
    debug("wrote coordinate reports to export/")

    counts = result["counts"]
    print(
        "GTFS written to {zip}: {trips} trips, {stops} stops, {routes} routes, "
        "{services} services, {shapes} shapes".format(zip=ZIP_PATH, **counts)
    )
    print(
        f"coordinate report: {len(result['missing'])} missing, "
        f"{len(duplicates)} duplicated, "
        f"{sum(1 for name in coords if name not in used_names)} unused rows"
    )
    debug(f"done in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
