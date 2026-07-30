# 中国铁路时刻表 GTFS | China Railway Timetable GTFS

本仓库发布的 GTFS 仅覆盖中国国家铁路公司的铁路、车次、车站，且仅包括线路走向、
车站名称与坐标、列车时刻。不包含如无障碍设施、车票费用等其他信息。GTFS 格式的
详细信息请参见 <https://gtfs.org/>。

The GTFS feed published by this repository covers stations, routes, and
trips from China State Railway Group Co., Ltd.. The feed covers only
timetables, railway lines' station list, station coordinates, and
train timetables. Other information, such as accessibility and fare info,
are not included. Please refer to <https://gtfs.org/> for more information
on the format.

## 数据来源 | Data Source

GTFS 数据每周更新一次。可以在 Releases 中下载数据。车站坐标来自
[OpenStreetMap](https://openstreetmap.org)。时刻表与线路数据来自一铁路平台。
考虑到相关影响，暂不公开获取数据的方法。

The GTFS data updates weekly. You can retrieve the data through releases. 
Station coordinate data are from [OpenStreetMap](https://openstreetmap.org)
Timetable and route data are from a rail service. Due various
considerations, the procedure used to fetch the data will not be published.

## 约定 | Conventions

车站坐标遵循 GTFS 格式采用 WGS84 格式。导入车站坐标时请注意坐标系。

中国铁路跨线车较多。虽然 GTFS 标准中规定每一个 trip（车次）必须有路线 ID，考虑到
跨线车数量庞大，本仓库发布的 GTFS 中，车次的路线 ID 固定为车次种别，如“高速”、
“动车组”、“新空调快速”等。GTFS 文件中保留线路车站列表，在文件中另行生成
`<线路名> (全线)`车次，车次的停站列表对应线路车站列表。如杭深线对应的线路车次是
`杭深线 (全线)`。在导入数据时可以忽略这部分车次。

Station coordinates follow GTFS specifications and are in WGS84.
Please use the correct coordinate system when importing the data.

China Railway runs through services regularly. The GTFS standard
specification requires each trip to have a route ID. Considering
the amount of through trains in the CR system, the route ID of trips
in the GTFS files released by this repo will be the trip's service type
instead of route ID. Additionally, the list of stations on actual
railway lines are preserved via additional `<route name> (全线)`
trips with line station lists encoded as timetable entries.
For example, Hangzhou–Shenzhen line (杭深线) would correspond to
`杭深线 (全线)`. You may ignore those trips when importing the data.
