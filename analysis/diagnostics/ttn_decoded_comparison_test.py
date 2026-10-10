#!/usr/bin/env python3
"""Strict decoded-payload comparison; only derived velocity gets ULP tolerance."""

from copy import deepcopy
import math
import unittest

from ttn_decoded_comparison import compare_decoded_payloads


def payload():
    return {"gps_valid": True, "boot_count": 97, "gps_satellites": 6,
            "gps_speed": 0.47, "gps_heading": 8.87, "lat": 0.0, "lon": 0.0,
            "velocity_x": 1.0, "velocity_y": 0.46438290636641255,
            "aux": {"velocity_y": 1.0, "samples": [1, False, None]}}


class ComparisonTest(unittest.TestCase):
    def test_actual_one_ulp_difference_is_agreement_not_exact_parity(self):
        local, server = payload(), payload()
        local["velocity_y"] = 0.4643829063664126
        result = compare_decoded_payloads(local, server)
        self.assertFalse(result["exact_parity"])
        self.assertTrue(result["bounded_derived_agreement"])
        self.assertEqual(result["derived_ulp_distance"], {"velocity_x": 0, "velocity_y": 1})

    def test_equal_valid_payload_is_exact(self):
        result = compare_decoded_payloads(payload(), deepcopy(payload()))
        self.assertTrue(result["exact_parity"])
        self.assertTrue(result["bounded_derived_agreement"])

    def test_four_ulp_inclusive_and_five_ulp_rejected_both_signs_and_fields(self):
        for field in ("velocity_x", "velocity_y"):
            for sign in (1, -1):
                for suffix, accepted in (("4", True), ("5", False)):
                    with self.subTest(field=field, sign=sign, ulps=suffix):
                        local, server = payload(), payload()
                        local[field] = sign * 1.0
                        server[field] = sign * float.fromhex("0x1.000000000000" + suffix + "p+0")
                        result = compare_decoded_payloads(local, server)
                        self.assertEqual(result["bounded_derived_agreement"], accepted)
                        self.assertFalse(result["exact_parity"])
                        self.assertEqual(result["derived_ulp_distance"][field], int(suffix))

    def test_subnormal_steps_cross_zero_without_relative_epsilon(self):
        local, server = payload(), payload()
        local["velocity_x"] = -float.fromhex("0x0.0000000000001p-1022")
        server["velocity_x"] = float.fromhex("0x0.0000000000003p-1022")
        result = compare_decoded_payloads(local, server)
        self.assertTrue(result["bounded_derived_agreement"])
        self.assertEqual(result["derived_ulp_distance"]["velocity_x"], 4)
        server["velocity_x"] = float.fromhex("0x0.0000000000004p-1022")
        self.assertFalse(compare_decoded_payloads(local, server)["bounded_derived_agreement"])

    def test_one_ulp_wire_or_nested_difference_is_never_tolerated(self):
        for field in ("lat", "lon", "gps_speed", "gps_heading"):
            local, server = payload(), payload()
            server[field] = math.nextafter(server[field], math.inf)
            self.assertFalse(compare_decoded_payloads(local, server)["bounded_derived_agreement"])
        local, server = payload(), payload()
        server["aux"]["velocity_y"] = math.nextafter(1.0, math.inf)
        self.assertFalse(compare_decoded_payloads(local, server)["bounded_derived_agreement"])

    def test_missing_extra_and_renamed_keys_fail(self):
        for field in ("velocity_x", "velocity_y", "gps_speed", "aux"):
            local, server = payload(), payload()
            del server[field]
            self.assertFalse(compare_decoded_payloads(local, server)["bounded_derived_agreement"])
        local, server = payload(), payload()
        server["extra"] = 0
        self.assertFalse(compare_decoded_payloads(local, server)["bounded_derived_agreement"])
        del local["velocity_x"]
        del server["velocity_x"]
        del server["extra"]
        self.assertFalse(compare_decoded_payloads(local, server)["bounded_derived_agreement"])

    def test_json_type_changes_do_not_compare_equal(self):
        for field, value in (("gps_valid", 1), ("boot_count", 97.0),
                             ("velocity_x", 1), ("gps_satellites", "6")):
            local, server = payload(), payload()
            server[field] = value
            self.assertFalse(compare_decoded_payloads(local, server)["bounded_derived_agreement"])
        local, server = payload(), payload()
        server["aux"]["samples"][1] = 0
        self.assertFalse(compare_decoded_payloads(local, server)["bounded_derived_agreement"])

    def test_invalid_derived_types_and_nonfinite_never_pass_even_if_equal(self):
        for value in (True, False, "1", [], {}, math.inf, -math.inf, math.nan):
            local, server = payload(), payload()
            local["velocity_x"] = server["velocity_x"] = value
            result = compare_decoded_payloads(local, server)
            self.assertFalse(result["exact_parity"])
            self.assertFalse(result["bounded_derived_agreement"])
        for value in (math.inf, -math.inf, math.nan):
            local, server = payload(), payload()
            local["aux"]["samples"][0] = server["aux"]["samples"][0] = value
            self.assertFalse(compare_decoded_payloads(local, server)["bounded_derived_agreement"])

    def test_non_object_schema_is_rejected(self):
        for value in (None, True, 1, [], "payload"):
            self.assertFalse(compare_decoded_payloads(value, value)["bounded_derived_agreement"])

    def test_no_fix_nulls_are_exact_only_and_numeric_null_mismatch_fails(self):
        local, server = payload(), payload()
        for item in (local, server):
            item.update(gps_valid=False, velocity_x=None, velocity_y=None)
        self.assertTrue(compare_decoded_payloads(local, server)["exact_parity"])
        server["velocity_y"] = 0.0
        self.assertFalse(compare_decoded_payloads(local, server)["bounded_derived_agreement"])

    def test_meaningful_derived_mismatch_is_rejected(self):
        local, server = payload(), payload()
        server["velocity_y"] += 0.000001
        self.assertFalse(compare_decoded_payloads(local, server)["bounded_derived_agreement"])


if __name__ == "__main__":
    unittest.main()
