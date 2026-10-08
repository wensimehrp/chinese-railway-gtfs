"""Crawl one shard of the train roster.

Used by .github/workflows/update.yml. Reads ``roster.json`` (produced by
``discover.py``) and crawls this shard's slice of it: railgo-parser's exporters
need a local MongoDB, so this starts one, then runs the normal ``crawl``
command.

Stations are skipped entirely. We only need each train's run days and stop
times, and every timetable entry already carries the station name and
telecode. The only thing that needs station rows is the station->train index
(``updatePassTrain``), so that is disabled and the station phase never runs.

    python shard.py <shard> <shards> <max-per-shard> <workers>

where ``<max-per-shard>`` is 0 for "no limit" and ``<workers>`` is the number
of trains crawled concurrently (railgo's default is 20).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

MONGO_URI = "mongodb://127.0.0.1:27017"
MONGO_TIMEOUT = 30  # seconds to wait for mongod to become reachable
ROSTER = "roster.json"


def wait_for_mongo(timeout: float = MONGO_TIMEOUT) -> None:
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


def main() -> None:
    shard, shards, limit, workers = map(int, sys.argv[1:5])

    from railgo.parser import pipe
    from railgo.parser.models.train import TrainModel
    from railgo.parser.parse import train

    # We only need trains (stop times + run days). The station->train index is
    # the only thing that requires station rows, so drop it and skip the
    # station phase entirely.
    train.updatePassTrain = lambda *args, **kwargs: None
    pipe.init_stations = lambda: None

    # railgo defaults to ThreadPoolExecutor(20) -- up to 20 trains at once, so
    # ~20 concurrent requests to 12306, which is what trips its rate limiting.
    # Fewer workers = a gentler request rate.
    pipe.PIPE_POOL = ThreadPoolExecutor(workers)

    with open(ROSTER, encoding="utf-8") as handle:
        roster = json.load(handle)

    def shard_trains():
        taken = 0
        for index, entry in enumerate(roster):
            if index % shards != shard:
                continue
            inst = TrainModel()
            inst.number = entry["number"]
            inst.code = entry["code"]
            inst._dataBeginDay = entry["dataBeginDay"]
            yield inst
            taken += 1
            if limit and taken >= limit:
                return

    # launchMainPipe() reads getTrainList() from railgo.parser.pipe.
    pipe.getTrainList = shard_trains

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
