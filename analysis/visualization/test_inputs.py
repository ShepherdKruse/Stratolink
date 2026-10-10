"""Offline regression checks for telemetry plotting input boundaries."""
import csv
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SCRIPTS = ("signal_distances", "signal_analysis", "gateway_heatmap")
ROW = {
    "time": "2026-01-01T12:00:00Z", "device_id": "example-balloon",
    "lat": 40.0, "lon": -100.0, "altitude_m": 10000.0,
    "snr": 4.0, "rssi": -100.0, "pressure": 260.0, "gps_satellites": 8,
    "gateways": [{"lat": 40.0, "lon": -99.0, "snr": 4.0, "rssi": -100.0}],
}


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fetch(module):
    if module.__name__ == "gateway_heatmap":
        return module.fetch_balloon_track()
    return module.fetch_telemetry_with_gateways()


def csv_text(row):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    return stream.getvalue()


class InputTests(unittest.TestCase):
    def test_live_input_requires_url_and_key_before_request(self):
        for name in SCRIPTS:
            for config in ({}, {"SBKEY": "test-key"}, {"SUPABASE_URL": "https://example.test"}):
                with self.subTest(script=name, config=list(config)):
                    with patch.dict(os.environ, config, clear=True), patch("requests.get", side_effect=AssertionError("network must not run")):
                        module = load(name)
                        with self.assertRaisesRegex(SystemExit, "SUPABASE_URL.*SBKEY"):
                            fetch(module)

    def test_live_input_uses_configured_url_and_authentication(self):
        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return [ROW]

        def request(url, *, params, headers, timeout):
            self.assertEqual(url, "https://example.test/rest/v1/telemetry")
            self.assertEqual(headers["apikey"], "test-key")
            self.assertEqual(headers["Authorization"], "Bearer test-key")
            self.assertEqual(params["order"], "time.asc")
            self.assertEqual(params["limit"], "5000")
            self.assertIn(params["device_id"], ("eq.stratolink-3", "in.(stratolink-3,stratolink-3-eu)"))
            self.assertEqual(timeout, 30)
            return Response()

        config = {"SUPABASE_URL": "https://example.test/", "SUPABASE_SERVICE_ROLE_KEY": "test-key"}
        for name in SCRIPTS:
            with self.subTest(script=name), patch.dict(os.environ, config, clear=True), patch("requests.get", side_effect=request):
                self.assertEqual(fetch(load(name)).iloc[0]["lat"], 40.0)

    def test_csv_needs_no_credentials_and_preserves_gateway_measurements(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.csv"
            path.write_text(csv_text({**ROW, "gateways": json.dumps(ROW["gateways"])}))
            for name in SCRIPTS:
                with self.subTest(script=name), patch.dict(os.environ, {"TELEMETRY_CSV": str(path)}, clear=True), patch("requests.get", side_effect=AssertionError("CSV must not fetch")):
                    module = load(name)
                    frame = fetch(module)
                    self.assertEqual(len(frame), 1)
                    self.assertEqual(str(frame.iloc[0]["time"].tz), "UTC")
                    if name != "gateway_heatmap":
                        self.assertEqual(frame.iloc[0]["gateways"], ROW["gateways"])
                    if name == "signal_distances":
                        result = module.per_fix_max_distance_and_snr(frame).iloc[0]
                        self.assertAlmostEqual(result["max_dist_km"], 85.18, places=1)
                        self.assertEqual(result["max_snr_db"], 4.0)

    def test_csv_reports_missing_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.csv"
            path.write_text("time,lat,lon\n2026-01-01T12:00:00Z,40,-100\n")
            for name in SCRIPTS:
                with self.subTest(script=name), patch.dict(os.environ, {"TELEMETRY_CSV": str(path)}, clear=True), patch("requests.get", side_effect=AssertionError("CSV must not fetch")):
                    with self.assertRaisesRegex(SystemExit, "missing.*altitude_m"):
                        fetch(load(name))

    def test_signal_csv_rejects_gateway_objects_instead_of_arrays(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.csv"
            path.write_text(csv_text({**ROW, "gateways": '{"lat": 40}'}))
            for name in SCRIPTS[:2]:
                with self.subTest(script=name), patch.dict(os.environ, {"TELEMETRY_CSV": str(path)}, clear=True), patch("requests.get", side_effect=AssertionError("CSV must not fetch")):
                    with self.assertRaisesRegex(SystemExit, "gateways.*JSON array"):
                        fetch(load(name))

    def test_gateway_csv_bypasses_public_fetch_and_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gateways.csv"
            path.write_text("lat,lon,id\n40,-100,example-gateway\n")
            with patch.dict(os.environ, {"GATEWAYS_CSV": str(path)}, clear=True), patch("requests.get", side_effect=AssertionError("CSV must not fetch")):
                module = load("gateway_heatmap")
                result = module.fetch_ttn_gateways()
                self.assertEqual(result.to_dict("records"), [{"lat": 40, "lon": -100, "id": "example-gateway"}])

    def test_gateway_csv_reports_missing_longitude(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gateways.csv"
            path.write_text("lat,id\n40,example-gateway\n")
            with patch.dict(os.environ, {"GATEWAYS_CSV": str(path)}, clear=True), patch("requests.get", side_effect=AssertionError("CSV must not fetch")):
                with self.assertRaisesRegex(SystemExit, "missing.*lon"):
                    load("gateway_heatmap").fetch_ttn_gateways()


if __name__ == "__main__":
    unittest.main()
