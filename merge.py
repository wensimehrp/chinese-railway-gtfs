"""Merge the per-shard SQLite files into one database, then post-process it.

The ``crawl`` job in .github/workflows/update.yml runs in shards, each of which
uploads its own ``export/railgo.sqlite``. This collects those files into a single
database (trains are unique by ``code``) and then runs the ``postprocess`` step,
so the workflow can publish one SQLite file and one decoded ``data/railgo.json``.

    python merge.py <out.sqlite> <glob>...

The ``<glob>`` arguments are expanded here rather than by the shell, so callers
can quote them. Rows pulled from every match are inserted into ``<out.sqlite>``,
ignoring duplicates, so the result is the same regardless of shard order.
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

from sqlalchemy import MetaData, create_engine, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from chinese_railway_gtfs import postprocess

# Mirrors railgo's ``MongoSQLiteExporter`` schema.
TABLES = ("trains", "stations")
PRIMARY_KEY = {"trains": "code", "stations": "telecode"}


def resolve(patterns: list[str]) -> list[Path]:
    """Expand the given globs into a sorted, de-duplicated list of files."""
    paths = sorted({Path(path) for pattern in patterns for path in glob.glob(pattern)})
    if not paths:
        raise SystemExit(f"no SQLite files matched {patterns}")
    return paths


def merge(out_path: Path, inputs: list[Path]) -> tuple[int, int]:
    """Insert every row from ``inputs`` into ``out_path``; return row counts."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # The exporter owns the schema, so reflect it from a shard instead of
    # redeclaring it here, then reuse it to create and populate the output.
    source_engine = create_engine(f"sqlite:///{inputs[0]}")
    try:
        metadata = MetaData()
        metadata.reflect(bind=source_engine, only=TABLES)
    finally:
        source_engine.dispose()

    out_engine = create_engine(f"sqlite:///{out_path}")
    try:
        metadata.create_all(out_engine)

        with out_engine.begin() as connection:
            for name in TABLES:
                table = metadata.tables[name]
                connection.execute(table.delete())

                for path in inputs:
                    shard = create_engine(f"sqlite:///{path}")
                    try:
                        with shard.connect() as shard_connection:
                            rows = [
                                dict(row)
                                for row in shard_connection.execute(
                                    select(table)
                                ).mappings()
                            ]
                    finally:
                        shard.dispose()
                    if rows:
                        connection.execute(
                            sqlite_insert(table).on_conflict_do_nothing(
                                index_elements=[PRIMARY_KEY[name]]
                            ),
                            rows,
                        )

        with out_engine.connect() as connection:
            counts = [
                connection.execute(
                    select(func.count()).select_from(metadata.tables[name])
                ).scalar_one()
                for name in TABLES
            ]
        return counts[0], counts[1]
    finally:
        out_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="merge shard databases")
    parser.add_argument("out", type=Path, help="output SQLite path")
    parser.add_argument(
        "inputs", nargs="+", help="shard SQLite paths (globs are expanded)"
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=postprocess.OUT_DEFAULT,
        help="decoded JSON output path",
    )
    args = parser.parse_args()

    inputs = resolve(args.inputs)
    print(f"merging {len(inputs)} shard databases")
    trains, stations = merge(args.out, inputs)
    print(f"merged: {trains} trains, {stations} stations")

    postprocess.run(argparse.Namespace(db=args.out, out=args.json))


if __name__ == "__main__":
    main()
