#!/usr/bin/env -S uv run

# railgo dependency is always resolved dynamically
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "railgo-parser @ git+https://github.com/RailGoApps/RailGo-Parser.git",
#     "regex>=2026.9.29",
# ]
# ///

import subprocess
from pathlib import Path

from railgo.parser.entry import launchMainPipe, resetWorks

mongod = subprocess.Popen("railgo-mongod")
Path("export").mkdir(parents=True, exist_ok=True)

try:
    resetWorks()
    launchMainPipe()
finally:
    mongod.terminate()
    mongod.wait()
