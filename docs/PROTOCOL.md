# Wire contract

All numbers are little-endian. Native Impeller header is `<IBHB`: u32 byte length
of the following 4 header bytes plus payload, u8 type=1 (table), u16 table ID,
u8 request ID=0. Lua VTables register field offsets and timestamp source.

| Table | Payload | Contents |
|---|---|---|
| 73 | `<q14d` | Optional reconstructed transport demo; schema in `replay.py` |
| 74 | `<q6d` | i64 timestamp_us; elapsed, SCLK, pressure, ATS local temp1, wind, wind_valid |
| 75 | `<q17d` | i64 timestamp_us; elapsed; display pose xyzw+xyz; raw S2/G pose xyzw+xyz; SCLK; original acquisition Unix seconds |
| 76 | `<q8d` | i64 timestamp_us; elapsed; interpolated display pose xyzw+xyz |
| 77 | `<q9d` | i64 timestamp_us; elapsed, draws, progress, density p05/p50/p95, ideal power p05/p50/p95 |
| 78 | `<q13dQQ` | i64 timestamp_us; 13 doubles: elapsed, current best pose xyzw+xyz, model-minus-display dx/dy/dz, 3-D distance, current best RMSE; u64 evaluated count and u64 winner ID |

Flight 59 uses tables 75, 76 and 78. Table 75 is archived navigation; table 76
is interpolation; table 78 is a calibrated model. Tables 74 and 77 remain for
the older Flight 1/MEDA and hover-sensitivity demo. Source time differences are preserved at any replay
speed. Storage epoch is rebased to replay start. No retransmission/loop mode is
implemented at application level: on disconnect the process fails visibly, and a
new invocation starts a new replay epoch. TCP guarantees ordered byte delivery;
`sendall` handles partial writes. Socket operations time out rather than waiting
forever. DB receipt must be verified separately from sender success.

The shared Lua `channel` function closes over the current fields/messages tables;
each table is sent before the next is built. Ports: host TCP 2250, host assets 2251,
Pi reverse SSH tunnel endpoint 12250. SSH alias and private keys are local machine
configuration, never stored in this repository.

`configure_scene.py` uses native message type 0 / ID bytes `[224,19]`
(`SetDbConfig`), with Postcard `recording=None` and a UTF-8 string-to-string metadata
map. It registers `sensor_cameras` and `schematic.active`. The replay also supplies
`time.start_timestamp` as Unix microseconds. No Python SDK is needed.

The native renderer writes `navcam.gray` as timestamped messages (type 3); its
name hashes to ID 34774. `export_navcam.py` reads committed append-log data,
validates payload length and offset prefix, and exports one 640×480 gray8 frame.
This reader is specific to the documented native append-log format and fails
visibly if the offset format changes.
