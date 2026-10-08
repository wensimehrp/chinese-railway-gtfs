"""Build a China Railway GTFS feed from railgo-parser data."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="chinese-railway-gtfs",
        description="Crawl China Railway data with railgo-parser and post-process it.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    from .crawl import add_parser as add_crawl
    from .postprocess import add_parser as add_postprocess

    add_crawl(subparsers)
    add_postprocess(subparsers)

    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
