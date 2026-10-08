"""Crawl one shard of the train roster.

Used by .github/workflows/update.yml. railgo-parser's exporters need a local
MongoDB, so this starts one, points railgo's train enumeration at this shard's
slice, and then runs the normal ``crawl`` command.

Stations are skipped entirely. We only need each train's run days and stop
times, and every timetable entry already carries the station name and
telecode. The only thing that needs station rows is the station->train index
(``updatePassTrain``), so that is disabled and the station phase never runs.

    python shard.py <shard> <shards> <max-per-shard>

where ``<max-per-shard>`` is 0 for "no limit".
"""

from __future__ import annotations

import subprocess
import sys
import time

MONGO_URI = "mongodb://127.0.0.1:27017"
MONGO_TIMEOUT_SECONDS = 30  # seconds to wait for mongod to become reachable


def wait_for_mongo(timeout: float = MONGO_TIMEOUT_SECONDS) -> None:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError

    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=500)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            client.admin.command("ping")
            return
        except PyMongoError:
            time.sleep(1)
    raise SystemExit(f"MongoDB not reachable at {MONGO_URI} after {timeout}s")


def shard_trains(train, shard: int, shards: int, limit: int):
    def generate():
        taken = 0
        for index, inst in enumerate(train.getTrainList()):
            if index % shards != shard:
                continue
            yield inst
            taken += 1
            if limit and taken >= limit:
                return

    return generate


def main() -> None:
    shard, shards, limit = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])

    from railgo.parser import pipe
    from railgo.parser.parse import train

    # We only need trains (stop times + run days). The station->train index is
    # the only thing that requires station rows, so drop it and skip the
    # station phase entirely.
    train.updatePassTrain = lambda *args, **kwargs: None
    pipe.init_stations = lambda: None

    # launchMainPipe() reads getTrainList() from railgo.parser.pipe.
    pipe.getTrainList = shard_trains(train, shard, shards, limit)

    mongod = subprocess.Popen(["railgo-mongod"])
    try:
        wait_for_mongo()

        sys.argv = ["chinese-railway-gtfs", "crawl"]
        from chinese_railway_gtfs import main as crawl

        crawl()
    finally:
        mongod.terminate()
        mongod.wait()


if __name__ == "__main__":
    main()
