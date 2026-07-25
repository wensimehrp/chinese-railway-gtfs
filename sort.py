#!/usr/bin/env -S uv run
with open("out.csv", "r", encoding="utf-8") as f:
    data = f.readlines()[1:]
data.sort()
with open("out.csv", "w", encoding="utf-8") as f:
    _ = f.write("station_name,lon,lat,id\n")
    f.writelines(data)
