# 中国铁路时刻表 GTFS | China Railway Timetable GTFS

本仓库发布的 GTFS 仅覆盖中国国家铁路公司的铁路、车次、车站，且仅包括线路走向、
车站名称与坐标、列车时刻。不包含如无障碍设施、车票费用等其他信息。GTFS 格式的
详细信息请参见 <https://gtfs.org/>。本仓库的 GTFS 数据以 CC BY 4.0 协议发布。
详情请见 [LICENSE](./LICENSE)。

The GTFS feed published by this repository covers stations, routes, and
trips from China State Railway Group Co., Ltd.. The feed covers only
timetables, railway lines' station list, station coordinates, and
train timetables. Other information, such as accessibility and fare info,
are not included. Please refer to <https://gtfs.org/> for more information
on the format. The GTFS data released by this repository is available under the
CC BY 4.0 license. Please refer to [LICENSE](./LICENSE) for more details.

## 数据来源 | Data Source

GTFS 数据每日更新一次。可以在 Releases 中下载数据。车站坐标来自
[OpenStreetMap](https://openstreetmap.org)。运行数据采用
[RailGo-Parser](https://github.com/RailGoApps/Railgo-Parser) 获取

The GTFS feed updates daily. You can download the feed from GitHub releases.
Station coordinate data are obtained from
[OpenStreetMap](https://openstreetmap.org). Timetable data are fetched using
[RailGo-Parser](https://github.com/RailGoApps/Railgo-Parser).

## 约定 | Conventions

车站坐标遵循 GTFS 格式，采用 WGS84，**不采用 GCJ-02**。
导入车站坐标时请注意坐标系。

中国铁路跨线车较多。虽然 GTFS 标准中规定每一个 trip（车次）必须有路线 ID，考虑到
跨线车数量庞大，本仓库发布的 GTFS 中，车次的路线 ID 固定为车次，如“G1”、
“1356”、“T3267”等。

Station coordinates follow GTFS specifications and uses WGS84 **instead of
GCJ-02.** Please use the correct coordinate system when importing the data.

China Railway runs through services regularly. The GTFS standard
specification requires each trip to have a route ID. Considering
the amount of through trains in the CR system, the route ID of trips
in the GTFS files released by this repo will be the trip's short name
instead of route ID, e.g. "G1", "1356", "T3267".
