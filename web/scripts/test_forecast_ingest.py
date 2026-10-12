"""Exercise the worker's real orchestration without NOAA, credentials, or GRIB.

The ingest modules import numpy + pygrib, which the web CI image lacks, so the
functions under test are lifted out of gfs_ingest.py by AST and executed against
stub collaborators — the same code the runner executes, minus the I/O."""
import ast
import contextlib
import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import tempfile
import types
import unittest

SRC = Path(__file__).with_name("gfs_ingest.py")
INGEST = SRC
TREE = ast.parse(SRC.read_text())


def lift(names, namespace):
    """Compile the named top-level functions of gfs_ingest.py into `namespace`."""
    body = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in names]
    missing = set(names) - {n.name for n in body}
    assert not missing, f"gfs_ingest.py no longer defines {missing}"
    exec(compile(ast.Module(body=body, type_ignores=[]), str(SRC), "exec"), namespace)
    return namespace


def extract(names):
    """Load just the named top-level functions / constants of gfs_ingest.py (it
    imports pygrib + numpy at module level, which the test runner lacks)."""
    tree = ast.parse(INGEST.read_text())
    body = [
        node for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name in names)
        or (isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id in names for t in node.targets))
    ]
    namespace = {"os": os}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(INGEST), "exec"), namespace)
    return namespace


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def base_namespace(**extra):
    """Real stdlib + the pure helpers the lifted code leans on."""
    ns = {
        "json": json, "os": os, "re": __import__("re"), "time": __import__("time"),
        "datetime": datetime, "timedelta": timedelta, "timezone": timezone,
        "RECON_STEP_H": 3, "HORIZON_H": 24, "MAX_GAP_H": 72, "FC_TUBE": True,
        "PLAN_MAX_AGE_H": 12, "PLAN_PATH": "/nonexistent/plan.json",
        "MANIFEST_PATH": "/nonexistent/manifest.json",
    }
    lift(["tparse", "floor_step"], ns)
    ns.update(extra)
    return ns


class PlanTests(unittest.TestCase):
    """planned_devices / load_plan: the activity gate's consumer side."""

    def plan(self, devices, age_h=0.0):
        return {
            "version": 1,
            "generated_at": iso(datetime.now(timezone.utc) - timedelta(hours=age_h)),
            "devices": devices,
        }

    def ns(self, plan=None, path=None):
        ns = base_namespace(active_devices=lambda: [("fleet-a", "2026-01-01T00:00:00Z")])
        if path:
            ns["PLAN_PATH"] = path
        lift(["load_plan", "planned_devices"], ns)
        return ns

    def test_build_devices_come_from_the_plan_and_skips_are_logged(self):
        ns = self.ns()
        plan = self.plan([
            {"device_id": "live", "action": "build", "launched_at": "2026-10-01T00:00:00Z", "reason": "active"},
            {"device_id": "dark", "action": "skip", "reason": "frozen: final dead-reckon already stored"},
        ])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            devices = ns["planned_devices"](None, plan)
        self.assertEqual(devices, [("live", "2026-10-01T00:00:00Z")])
        self.assertIn("dark: skipped by plan — frozen", out.getvalue())

    def test_requested_device_that_the_plan_skipped_stays_skipped(self):
        ns = self.ns()
        plan = self.plan([{"device_id": "dark", "action": "skip", "reason": "frozen"},
                          {"device_id": "live", "action": "build"}])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ns["planned_devices"]("dark", plan), [])
            self.assertEqual(ns["planned_devices"]("live", plan), [("live", None)])
            self.assertEqual(ns["planned_devices"]("unknown", plan), [])

    def test_without_a_plan_the_legacy_fleet_query_is_used(self):
        ns = self.ns()  # PLAN_PATH points nowhere
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ns["planned_devices"](None), [("fleet-a", "2026-01-01T00:00:00Z")])
            self.assertEqual(ns["planned_devices"]("one"), [("one", None)])

    def test_stale_or_malformed_plan_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "plan.json")
            ns = self.ns(path=path)
            with open(path, "w") as f:
                json.dump(self.plan([{"device_id": "x", "action": "build"}], age_h=36), f)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertIsNone(ns["load_plan"]())
            self.assertIn("stale", out.getvalue())
            with open(path, "w") as f:
                f.write("{not json")
            self.assertIsNone(ns["load_plan"]())
            with open(path, "w") as f:
                json.dump(self.plan([{"device_id": "x", "action": "build"}]), f)
            self.assertEqual(ns["load_plan"]()["devices"][0]["device_id"], "x")


class MainTests(unittest.TestCase):
    """gfs_ingest.main with stubbed collaborators."""

    def worker(self, build_cube, devices, latest_cycle=None):
        calls = {"manifest": []}
        ns = base_namespace(
            sys=types.SimpleNamespace(argv=["gfs_ingest.py"]),
            planned_devices=lambda only=None: devices,
            latest_cycle=latest_cycle or (lambda: types.SimpleNamespace(isoformat=lambda: "test-cycle")),
            mission_track=lambda *_: [{"lat": 0, "lon": 0, "t": "2026-10-01T00:00:00Z"}],
            float_pressure=lambda _: 250,
            build_cube=build_cube,
            cubes_written=lambda device, since: {"fc": True, "recon": True},
            manifest_source_begin=lambda source, **meta: calls["manifest"].append(("begin", source)),
            manifest_device=lambda source, device, **f: calls["manifest"].append(("device", device, f)),
            manifest_source_end=lambda source: calls["manifest"].append(("end", source)),
        )
        lift(["main"], ns)
        return ns["main"], calls

    def test_ingest_error_fails_job_after_processing_other_devices(self):
        attempted = []

        def build(device, *_):
            attempted.append(device)
            if device == "one":
                raise RuntimeError("simulated NOAA outage")

        main, calls = self.worker(build, [("one", None), ("two", None)])
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            main()
        self.assertEqual(attempted, ["one", "two"])
        errors = [c for c in calls["manifest"] if c[0] == "device" and "error" in c[2]]
        self.assertEqual([c[1] for c in errors], ["one"])
        self.assertEqual(calls["manifest"][-1], ("end", "gfs"))

    def test_empty_fleet_does_not_download_weather(self):
        def build(*_):
            self.fail("No weather work expected")

        def no_cycle():
            self.fail("No NOAA request expected")

        main, calls = self.worker(build, [], latest_cycle=no_cycle)
        with contextlib.redirect_stdout(io.StringIO()):
            main()
        self.assertEqual(calls["manifest"], [("begin", "gfs"), ("end", "gfs")])

    def test_frozen_device_in_the_plan_triggers_zero_downloads(self):
        """A GPS-dark balloon the plan marked skip never reaches NOAA, even when
        requested by name (the skip is logged by planned_devices)."""
        ns = base_namespace(
            sys=types.SimpleNamespace(argv=["gfs_ingest.py", "stratolink-2"]),
            latest_cycle=lambda: self.fail("No NOAA request expected"),
            http_get=lambda *a, **k: self.fail("No download expected"),
            active_devices=lambda: self.fail("No fleet query expected with a plan"),
            mission_track=lambda *_: self.fail("No telemetry query expected"),
            float_pressure=lambda _: self.fail("unexpected"),
            build_cube=lambda *_: self.fail("No cube build expected"),
            manifest_source_begin=lambda *a, **k: None, manifest_device=lambda *a, **k: None,
            manifest_source_end=lambda *a, **k: None,
        )
        plan = {"version": 1, "generated_at": iso(datetime.now(timezone.utc)), "devices": [
            {"device_id": "stratolink-2", "action": "skip",
             "reason": "frozen: last fix 71.0 d ago (> cap 14.0 d + 24.0 h); stored forecast is final"}]}
        ns["load_plan"] = lambda path=None: plan
        lift(["planned_devices", "main"], ns)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ns["main"]()
        self.assertIn("stratolink-2: skipped by plan — frozen", out.getvalue())
        self.assertIn("no devices to build", out.getvalue())


class CubeSpanTests(unittest.TestCase):
    """Reconstruction span, single-fix skip, tube-before-recon field reuse."""

    def build_cube_harness(self, recon_tube=False):
        events = []
        ns = base_namespace(
            RECON_TUBE=recon_tube,
            build_tube_recon=lambda device, fixes, target_p, latest, now: events.append(("recon_tube", device)),
            bracket_levels=lambda p: (250, 300, 0.5),
            clear_field_cache=lambda keep=(): events.append(("clear", sorted(keep))),
            build_tube_fc=lambda device, fixes, last_fix, gap_h, target_p, latest, now: events.append(("tube", device)),
            bounds_for_forecast=lambda fixes, hours, pad_cap=32: {"latMin": 0, "latMax": 1, "lonMin": 0, "lonMax": 1},
            choose_grid_step=lambda b: 0.5,
            pick_source=lambda t, latest: ("cyc", t.hour),
            sample_grids=lambda bounds, step, start, end, step_h, p, latest, now, tag="": (
                events.append(("recon", start, end, step_h)) or ({"grids": []}, 1, 1)),
            write_cube=lambda device, suffix, cube, nlat, nlon, tag: events.append(("write", suffix)),
        )
        lift(["fields_for", "build_cube"], ns)
        return ns["build_cube"], events

    def test_single_fix_builds_only_the_forecast_tube(self):
        build_cube, events = self.build_cube_harness()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            build_cube("solo", [{"lat": 1, "lon": 2, "t": "2026-10-01T00:00:00Z"}], 280.0, None)
        self.assertEqual([e[0] for e in events], ["clear", "tube"])   # no recon sampled, nothing written
        self.assertIn("recon: skipped (1 fix", out.getvalue())

    def test_tube_is_built_first_and_recon_ends_two_steps_after_the_last_fix(self):
        build_cube, events = self.build_cube_harness(recon_tube=False)   # legacy static box
        fixes = [{"lat": 1, "lon": 2, "t": "2026-10-01T00:10:00Z"},
                 {"lat": 1.5, "lon": 2.5, "t": "2026-10-02T13:40:00Z"}]
        with contextlib.redirect_stdout(io.StringIO()):
            build_cube("pair", fixes, 280.0, None)
        kinds = [e[0] for e in events]
        self.assertEqual(kinds, ["clear", "tube", "clear", "recon", "write", "clear"])
        _, start, end, step_h = events[3]
        # floor(first fix) − 3 h … floor(last fix) + 6 h — not now + horizon: a
        # balloon dark for weeks adds no grids.
        self.assertEqual((start, end, step_h), (datetime(2026, 9, 30, 21, tzinfo=timezone.utc),
                                                datetime(2026, 10, 2, 18, tzinfo=timezone.utc), 3))
        self.assertLess(end, datetime.now(timezone.utc))
        # The clear between tube and recon keeps exactly the recon's own fields.
        kept = events[2][1]
        self.assertEqual(kept, sorted({("cyc", h) for h in range(0, 24, 3)}))
        self.assertEqual(events[4], ("write", ""))

    def test_recon_tube_is_the_default_and_keeps_the_forecast_tubes_fields_warm(self):
        build_cube, events = self.build_cube_harness(recon_tube=True)
        fixes = [{"lat": 1, "lon": 2, "t": "2026-10-01T00:10:00Z"},
                 {"lat": 1.5, "lon": 2.5, "t": "2026-10-02T13:40:00Z"}]
        with contextlib.redirect_stdout(io.StringIO()):
            build_cube("pair", fixes, 280.0, None)
        self.assertEqual([e[0] for e in events], ["clear", "tube", "clear", "recon_tube", "clear"])
        # The clear before the tube recon keeps the recon span's own fields (floor(first) − 3 h … floor(last) + 6 h).
        self.assertEqual(events[2][1], sorted({("cyc", h) for h in range(0, 24, 3)}))

    def test_skip_recon_env_builds_only_the_forecast_tube(self):
        build_cube, events = self.build_cube_harness(recon_tube=True)
        fixes = [{"lat": 1, "lon": 2, "t": "2026-10-01T00:10:00Z"}, {"lat": 1.5, "lon": 2.5, "t": "2026-10-02T13:40:00Z"}]
        os.environ["SKIP_RECON"] = "1"
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                build_cube("pair", fixes, 280.0, None)
        finally:
            del os.environ["SKIP_RECON"]
        self.assertEqual([e[0] for e in events], ["clear", "tube"])
        self.assertIn("SKIP_RECON=1", out.getvalue())

    def test_cubes_written_reports_only_this_runs_files(self):
        with tempfile.TemporaryDirectory() as d:
            ns = base_namespace(OUTDIR=d)
            lift(["cubes_written"], ns)
            t0 = __import__("time").time()
            self.assertEqual(ns["cubes_written"]("dev", t0), {"fc": False, "recon": False})
            Path(d, "dev-fc.slwc").write_bytes(b"x")
            self.assertEqual(ns["cubes_written"]("dev", t0), {"fc": True, "recon": False})
            Path(d, "dev.slwc").write_bytes(b"x")
            os.utime(Path(d, "dev.slwc"), (t0 - 3600, t0 - 3600))      # stale file from an earlier run
            self.assertEqual(ns["cubes_written"]("dev", t0), {"fc": True, "recon": False})

    def test_clear_field_cache_keeps_only_the_named_fields(self):
        ns = base_namespace(_uv_cache={("c1", 0, 250): "a", ("c1", 3, 250): "b"},
                            _uv_p_cache={("c1", 0, 280.0): "ab", ("c2", 6, 280.0): "cd"})
        lift(["clear_field_cache"], ns)
        ns["clear_field_cache"](keep={("c1", 0)})
        self.assertEqual(list(ns["_uv_cache"]), [("c1", 0, 250)])
        self.assertEqual(list(ns["_uv_p_cache"]), [("c1", 0, 280.0)])
        ns["clear_field_cache"]()
        self.assertEqual((ns["_uv_cache"], ns["_uv_p_cache"]), ({}, {}))


class ManifestTests(unittest.TestCase):
    def test_manifest_is_written_incrementally_per_source_and_device(self):
        with tempfile.TemporaryDirectory() as d:
            ns = base_namespace(MANIFEST_PATH=os.path.join(d, "nested", "manifest.json"))
            lift(["_manifest_read", "_manifest_write", "_now_iso",
                  "manifest_source_begin", "manifest_device", "manifest_source_end"], ns)
            ns["manifest_source_begin"]("gefs", members_expected=31)
            ns["manifest_device"]("gefs", "dev", built=1, expected=31)
            ns["manifest_device"]("gefs", "dev", built=2, expected=31)
            m = json.loads(Path(ns["MANIFEST_PATH"]).read_text())
            self.assertEqual(m["sources"]["gefs"]["devices"]["dev"], {"built": 2, "expected": 31})
            self.assertEqual(m["sources"]["gefs"]["members_expected"], 31)
            self.assertNotIn("finished_at", m["sources"]["gefs"])   # killed mid-way ⇒ visible
            ns["manifest_source_end"]("gefs")
            m = json.loads(Path(ns["MANIFEST_PATH"]).read_text())
            self.assertIn("finished_at", m["sources"]["gefs"])
            self.assertGreaterEqual(m["sources"]["gefs"]["seconds"], 0)
            # A new run of the same source resets it; other sources are untouched.
            ns["manifest_source_begin"]("aigefs", members_expected=31)
            ns["manifest_source_begin"]("gefs", members_expected=4)
            m = json.loads(Path(ns["MANIFEST_PATH"]).read_text())
            self.assertEqual(m["sources"]["gefs"]["devices"], {})
            self.assertEqual(m["sources"]["aigefs"]["members_expected"], 31)


class ReconTubeGeometryTests(unittest.TestCase):
    """The per-slice geometry of the reconstruction tube (pure helpers)."""

    @classmethod
    def setUpClass(cls):
        cls.g = extract({
            "RECON_HALF_BASE_DEG", "RECON_HALF_PER_H", "RECON_HALF_MIN_DEG", "RECON_HALF_MAX_DEG",
            "recon_half_deg", "gap_hours_at", "unwrap_lons",
        })

    def test_half_width_grows_with_gap_length_within_clamps(self):
        half = self.g["recon_half_deg"]
        self.assertEqual(half(0), 9)                 # floor: short gaps
        self.assertEqual(half(60), 9)                # 6 + 3 = the floor exactly
        self.assertAlmostEqual(half(100), 11)
        self.assertAlmostEqual(half(200), 16)
        self.assertEqual(half(280), 20)              # cap
        self.assertEqual(half(10_000), 20)

    def test_gap_hours_at_uses_the_longest_gap_a_slice_can_be_read_by(self):
        h = 3_600_000
        fixes = [(0, 0, 0), (10 * h, 0, 0), (12 * h, 0, 0), (50 * h, 0, 0)]   # gaps 10 h, 2 h, 38 h
        gap_at = self.g["gap_hours_at"]
        self.assertEqual(gap_at(fixes, 5 * h, 3 * h), 10)
        # A slice within one step of the next gap's start is read by that gap too.
        self.assertEqual(gap_at(fixes, 11 * h, 3 * h), 38)
        self.assertEqual(gap_at(fixes, 30 * h, 3 * h), 38)
        self.assertEqual(gap_at(fixes, 52 * h, 3 * h), 38)   # trailing slice still touches the last gap
        self.assertEqual(gap_at(fixes, -5 * h, 3 * h), 0)    # lead-in slice: no bridge reads it
        self.assertEqual(gap_at(fixes, 60 * h, 3 * h), 0)

    def test_unwrap_lons_is_continuous_and_anchored_at_the_last_fix(self):
        unwrap = self.g["unwrap_lons"]
        self.assertEqual(unwrap([]), [])
        self.assertEqual(unwrap([-122.4, -100.0, -4.5]), [-122.4, -100.0, -4.5])
        # Eastward across the dateline: no +360 jump, last value kept raw.
        self.assertEqual(unwrap([170.0, 178.0, -178.0, -170.0]), [-190.0, -182.0, -178.0, -170.0])


class MultiLevelWindFollowingTubeTests(unittest.TestCase):
    """The multi-level reconstruction cube: which levels it stores, and long-gap
    slice boxes sized by a pilot cloud along the forward/backward wind paths."""

    @classmethod
    def setUpClass(cls):
        import math
        cls.g = extract({
            "GFS_LEVELS", "RECON_LEVEL_SET", "RECON_LEVELS_EACH_SIDE", "LONG_GAP_H", "LONG_GAP_JOIN_MARGIN_H",
            "LONG_GAP_MAX_SPREAD_DEG", "TUBE_SUBSTEP_H", "RECON_HALF_BASE_DEG", "RECON_HALF_PER_H", "RECON_HALF_MIN_DEG",
            "RECON_HALF_MAX_DEG", "RECON_PILOT_N", "RECON_PILOT_MARGIN_DEG", "PILOT_DIR_SIGMA_DEG", "PILOT_SPEED_SIGMA",
            "PILOT_TAU_H", "recon_levels", "integrate_positions", "interp_track", "recon_half_deg", "pilot_envelopes",
            "recon_slice_needs", "cover_boxes",
        })
        # integrate_positions only needs cos/radians from numpy.
        cls.g["np"] = types.SimpleNamespace(cos=math.cos, radians=math.radians)
        cls.g["math"] = math

    def test_recon_levels_bracket_the_float_plus_one_each_side(self):
        lv = self.g["recon_levels"]
        self.assertEqual(lv(280.8, 1), [200, 250, 300, 350])     # 350 hPa is in the 0.25° files
        self.assertEqual(lv(300, 1), [250, 300, 350])            # on a level: that level ± one
        self.assertEqual(lv(280.8, 2), [150, 200, 250, 300, 350, 400])
        self.assertEqual(lv(25, 1), [30, 50])                    # clamped at the top of the set
        self.assertEqual(lv(280.8, 0), [])                       # single-level cube
        self.assertIn(350, self.g["RECON_LEVEL_SET"])
        self.assertNotIn(350, self.g["GFS_LEVELS"])              # forecast/GEFS levels unchanged

    def test_pilot_cloud_starts_at_the_fix_and_spreads(self):
        import math
        wind = lambda lat, lon, t: (25.0, 0.0)
        h = 3_600_000
        env = self.g["pilot_envelopes"]([0, 12 * h, 48 * h], 0, 40.0, 0.0, wind, 1, n=200, seed=1)
        self.assertEqual(env[0], (40.0, 40.0, 0.0, 0.0))        # at the fix: a point
        w12 = env[12 * h][1] - env[12 * h][0]; w48 = env[48 * h][1] - env[48 * h][0]
        self.assertTrue(0 < w12 < w48 < 40, (w12, w48))          # it spreads (4,300 km downwind × a 12° heading spread)
        deg_per_h = 25 * 3600 / (111_320 * math.cos(math.radians(40)))
        mid = (env[48 * h][2] + env[48 * h][3]) / 2
        self.assertAlmostEqual(mid, 48 * deg_per_h, delta=6)     # downwind of the fix, around the nominal
        back = self.g["pilot_envelopes"]([-12 * h], 0, 40.0, 0.0, wind, -1, n=200, seed=1)
        self.assertLess(back[-12 * h][3], 0.5)                   # backward: upwind of the fix
        # Deterministic for a seed (cubes rebuild identically).
        self.assertEqual(env, self.g["pilot_envelopes"]([0, 12 * h, 48 * h], 0, 40.0, 0.0, wind, 1, n=200, seed=1))

    def test_long_gap_boxes_follow_the_wind_and_shrink_toward_the_fixes(self):
        import math
        h = 3_600_000
        # A 48 h gap under a uniform 25 m/s westerly that carries the balloon
        # ~1.05°/h east, with B at 45° (the wind's own end point is 50.6°).
        deg_per_h = 25 * 3600 / (111_320 * math.cos(math.radians(40)))
        fixes = [(0, 40.0, 0.0), (48 * h, 40.0, 45.0)]
        slices = [k * 3 * h for k in range(-1, 18)]
        wind = lambda lat, lon, t: (25.0, 0.0)
        needs = self.g["recon_slice_needs"](fixes, slices, 3 * h, wind)
        H = self.g["recon_half_deg"](48)
        box = lambda k: (min(x[0] for x in needs[k]), max(x[1] for x in needs[k]), min(x[2] for x in needs[k]), max(x[3] for x in needs[k]))
        k3, k24 = slices.index(3 * h), slices.index(24 * h)
        a, b, c, d = box(k3)
        self.assertTrue(c < 3 * deg_per_h < d and a < 40 < b)    # holds the forward wind path
        self.assertLess(b - a, 2 * H - 4)                         # and is much shorter than the old ±H box near the fix
        a, b, c, d = box(k24)
        self.assertTrue(c <= 45 - 24 * deg_per_h and d >= 24 * deg_per_h)   # around the midpoint: both clouds' paths
        self.assertLessEqual(b - a, 2 * H + 1e-9)                 # never larger than the old cap
        k45 = slices.index(45 * h)
        a, b, c, d = box(k45)
        self.assertTrue(c < 45 - 3 * deg_per_h < d)              # backward path near B

    def test_short_gaps_and_unconnectable_long_gaps_keep_the_chord(self):
        h = 3_600_000
        wind = lambda lat, lon, t: (25.0, 0.0)
        needs = self.g["recon_slice_needs"]([(0, 10.0, 0.0), (4 * h, 10.0, 2.0)], [0, 3 * h], 3 * h, wind)
        H = self.g["recon_half_deg"](4)
        self.assertEqual(needs[1], [(10.0 - H, 10.0 + H, 1.5 - H, 1.5 + H)])
        # A 48 h gap that does not move while the wind runs 50° east (a balloon on
        # the ground): forward and backward trajectories split > 30° → chord.
        needs = self.g["recon_slice_needs"]([(0, 40.0, 0.0), (48 * h, 40.0, 0.0)], [24 * h], 3 * h, wind)
        H = self.g["recon_half_deg"](48)
        self.assertEqual(needs[0], [(40.0 - H, 40.0 + H, -H, H)])

    def test_cover_boxes_take_the_union_and_snap_to_the_step(self):
        boxes = self.g["cover_boxes"]([[(30.0, 50.0, -10.0, 18.0)], [(1.0, 18.9, -9.1, 9.1), (5.0, 8.0, 0.0, 4.0)]], 0.25)
        self.assertEqual(boxes[0], (40.0, 4.0, 10.0, 14.0))
        self.assertEqual(boxes[1][2:], (9.0, 9.25))               # snapped UP to the 0.25° step


class DeviceAliasMirrorTests(unittest.TestCase):
    """The ingest must query the same canonical + alias telemetry ids as the
    compute (lib/devices/aliases.ts), or the tube is built from a partial track."""

    @classmethod
    def setUpClass(cls):
        cls.g = extract({"DEVICE_ID_ALIASES", "telemetry_device_ids", "device_id_filter"})

    def test_alias_map_matches_the_typescript_source(self):
        ts = (INGEST.parent.parent / "lib" / "devices" / "aliases.ts").read_text()
        block = re.search(r"DEVICE_ID_ALIASES[^{]*\{(.*?)\};", ts, re.S).group(1)
        ts_map = dict(re.findall(r"['\"]([^'\"]+)['\"]\s*:\s*['\"]([^'\"]+)['\"]", block))
        self.assertTrue(ts_map, "could not parse DEVICE_ID_ALIASES from aliases.ts")
        self.assertEqual(self.g["DEVICE_ID_ALIASES"], ts_map)

    def test_telemetry_ids_expand_canonical_and_alias(self):
        ids = self.g["telemetry_device_ids"]
        self.assertEqual(ids("stratolink-3"), ["stratolink-3", "stratolink-3-eu"])
        self.assertEqual(ids("stratolink-3-eu"), ["stratolink-3", "stratolink-3-eu"])
        self.assertEqual(ids("stratolink-2"), ["stratolink-2"])
        self.assertEqual(self.g["device_id_filter"]("stratolink-3"), "in.(stratolink-3,stratolink-3-eu)")


if __name__ == "__main__":
    unittest.main()
