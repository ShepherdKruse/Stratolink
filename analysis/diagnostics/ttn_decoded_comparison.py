"""Compare JSON-decoded telemetry, never relax transmitted numeric fields.

Only top-level derived velocity floats receive four binary64 ULPs of tolerance.
Integer representations remain exact-only; matching no-fix nulls are exact-only.
This compares against the local formatter's schema, not an independent validator
of every possible telemetry schema. Invalid JSON values and velocity types fail.
"""

import math
import struct

DERIVED_FIELDS = ("velocity_x", "velocity_y")
MAX_DERIVED_ULPS = 4


def _exact_json(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return (all(type(key) is str for key in left) and left.keys() == right.keys()
                and all(_exact_json(left[key], right[key]) for key in left))
    if type(left) is list:
        return len(left) == len(right) and all(_exact_json(a, b) for a, b in zip(left, right))
    if type(left) is float:
        return math.isfinite(left) and math.isfinite(right) and left == right
    return type(left) in (str, int, bool, type(None)) and left == right


def _float_rank(value):
    bits = struct.unpack(">Q", struct.pack(">d", value))[0]
    magnitude = bits & 0x7fffffffffffffff
    # Coalesce signed zero; adjacent subnormals on either side are two steps.
    return -magnitude if bits >> 63 else magnitude


def compare_decoded_payloads(local, server):
    result = {"exact_parity": False, "bounded_derived_agreement": False,
              "derived_ulp_distance": {}}
    if (type(local) is not dict or type(server) is not dict or
            local.keys() != server.keys() or
            not all(field in local for field in DERIVED_FIELDS) or
            not all(type(key) is str for key in local)):
        return result
    bounded = True
    for field in DERIVED_FIELDS:
        left, right = local[field], server[field]
        if left is None and right is None and local.get("gps_valid") is False and server.get("gps_valid") is False:
            result["derived_ulp_distance"][field] = None
        elif type(left) is float and type(right) is float and math.isfinite(left) and math.isfinite(right):
            distance = abs(_float_rank(left) - _float_rank(right))
            result["derived_ulp_distance"][field] = distance
            bounded = bounded and distance <= MAX_DERIVED_ULPS
        elif type(left) is int and type(right) is int and left == right:
            result["derived_ulp_distance"][field] = 0
        else:
            return result
    other_exact = all(_exact_json(local[key], server[key]) for key in local if key not in DERIVED_FIELDS)
    result["exact_parity"] = other_exact and all(_exact_json(local[key], server[key]) for key in DERIVED_FIELDS)
    result["bounded_derived_agreement"] = other_exact and bounded
    return result
