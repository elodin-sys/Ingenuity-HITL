-- Matches <q14d in scripts/replay.py. Mission time is independent of replay speed.
local client = connect(os.getenv("INGENUITY_DB_ADDR") or "127.0.0.1:2250")
local fields = {}
local msgs = {}
local function channel(name, offset, count, units, labels, primitive)
    local shape = {}
    if count > 1 then shape = {count} end
    table.insert(fields, field(offset, count * 8,
        schema(primitive or "f64", shape, timestamp(table_slice(0, 8), component(name)))))
    table.insert(msgs, SetComponentMetadata({
        component_id = ComponentId(name), name = name,
        metadata = {units = units, element_names = labels or ""}
    }))
end
channel("ingenuity.mission_time", 8, 1, "s")
channel("ingenuity.world_pos", 16, 7, "quaternion,m", "q0,q1,q2,q3,x,y,z")
channel("ingenuity.vertical_speed", 72, 1, "m/s")
channel("environment.pressure", 80, 1, "Pa")
channel("environment.temperature", 88, 1, "K")
channel("environment.density", 96, 1, "kg/m^3")
channel("theory.ideal_hover_power", 104, 1, "W")
channel("ingenuity.source_kind", 112, 1, "0=measured,1=reconstructed")
table.insert(msgs, vtable_msg(73, fields))
client:send_msgs(msgs)
print("Ingenuity table 73 registered")
fields = {}
msgs = {}
channel("meda.elapsed", 8, 1, "s")
channel("meda.sclk", 16, 1, "s")
channel("meda.pressure", 24, 1, "Pa")
channel("meda.ats_local_temp1", 32, 1, "K")
channel("meda.horizontal_wind", 40, 1, "m/s")
channel("meda.wind_valid", 48, 1, "boolean")
table.insert(msgs, vtable_msg(74, fields))
client:send_msgs(msgs)
print("MEDA table 74 registered")
fields = {}
msgs = {}
channel("helicam.elapsed", 8, 1, "s", "Archive / s")
channel("helicam.world_pos", 16, 7, "S2 quaternion,m", "q0,q1,q2,q3,x,y,z")
channel("helicam.height", 64, 1, "m above G origin; S2 navigation estimate", "NASA S2 / m")
channel("helicam.raw_s2_in_g", 72, 7, "S2 quaternion,m", "qx,qy,qz,qw,x,y,z")
channel("helicam.sclk", 128, 1, "s")
channel("helicam.source_unix", 136, 1, "s since Unix epoch")
table.insert(msgs, vtable_msg(75, fields))
client:send_msgs(msgs)
print("HeliCam archive table 75 registered")
fields = {}
msgs = {}
channel("display.elapsed", 8, 1, "s; visualization interpolation")
channel("display.world_pos", 16, 7, "interpolated S2 quaternion,m", "q0,q1,q2,q3,x,y,z")
table.insert(msgs, vtable_msg(76, fields))
client:send_msgs(msgs)
print("Interpolated display table 76 registered; not measured telemetry")
fields = {}
msgs = {}
channel("mc.elapsed", 8, 1, "s")
channel("mc.draws", 16, 1, "completed model evaluations")
channel("mc.progress", 24, 1, "fraction")
channel("mc.density_p05", 32, 1, "kg/m^3; assumed priors")
channel("mc.density_p50", 40, 1, "kg/m^3; assumed priors")
channel("mc.density_p95", 48, 1, "kg/m^3; assumed priors")
channel("mc.power_p05", 56, 1, "W; ideal hover lower bound")
channel("mc.power_p50", 64, 1, "W; ideal hover lower bound")
channel("mc.power_p95", 72, 1, "W; ideal hover lower bound")
table.insert(msgs, vtable_msg(77, fields))
client:send_msgs(msgs)
print("Live Monte Carlo table 77 registered; model sensitivity only")
fields = {}
msgs = {}
channel("best.elapsed", 8, 1, "s since first archive sample")
channel("best.world_pos", 16, 7, "modeled position; identity attitude", "q0,q1,q2,q3,x,y,z")
channel("comparison.delta", 72, 3, "m; best model minus interpolated archive", "dx,dy,dz")
channel("comparison.error", 96, 1, "m; 3D distance from interpolated archive", "3D gap / m")
channel("comparison.rmse", 104, 1, "m; calibration RMSE at archived times", "MC RMSE / m")
channel("comparison.draws", 112, 1, "candidates evaluated during replay", "MC trials", "u64")
channel("comparison.winner", 120, 1, "best candidate ID so far", "MC winner", "u64")
table.insert(msgs, vtable_msg(78, fields))
client:send_msgs(msgs)
print("Trajectory comparison table 78 registered; conditional model calibration")
