#!/usr/bin/env python3
"""Read-only TTN Join Server audit for DevNonce journal migration.

The legacy firmware selected DevNonce from ``micros() & 0xffff``. The new
firmware journals a monotonic counter in reserved flash, so an erased journal
must be seeded above every nonce already accepted for each regional identity.

This tool deliberately prints only counts and extrema. It never prints API
keys, root keys, session keys, EUIs, or the complete used-nonce set.
"""

from __future__ import annotations

import json

from ttn_inventory import get_json, load_values


TARGETS = (
    ("na", "nam1.cloud.thethings.network", "TTN_NA_API_KEY",
     "stratolink", "stratolink-2"),
    ("eu", "eu1.cloud.thethings.network", "TTN_EU_API_KEY",
     "eu-stratolink", "stratolink-2-eu"),
    ("as", "eu1.cloud.thethings.network", "TTN_AS_API_KEY",
     "as-stratolink", "stratolink-2-as"),
)


def as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            return None
    return None


def main() -> None:
    keys = load_values()
    rows: list[dict[str, object]] = []
    global_max = -1
    used_union: set[int] = set()
    last_values: list[int] = []
    complete = True

    for region, host, key_name, app_id, device_id in TARGETS:
        api_key = keys.get(key_name, "")
        if not api_key:
            rows.append({"region": region, "status": "missing_api_key"})
            complete = False
            continue

        status, device = get_json(
            host,
            f"/js/applications/{app_id}/devices/{device_id}"
            "?field_mask=last_dev_nonce,used_dev_nonces,resets_join_nonces",
            api_key,
        )
        if status != 200:
            rows.append({
                "region": region,
                "status": status,
                "error": device.get("message", "Join Server read failed"),
            })
            complete = False
            continue

        raw_used = device.get("used_dev_nonces", [])
        used = sorted({
            parsed
            for value in raw_used
            if (parsed := as_int(value)) is not None and 0 <= parsed <= 0xFFFF
        })
        last = as_int(device.get("last_dev_nonce"))
        maxima = used + ([last] if last is not None else [])
        max_seen = max(maxima, default=-1)
        global_max = max(global_max, max_seen)
        used_union.update(used)
        if last is not None:
            last_values.append(last)
        rows.append({
            "region": region,
            "status": status,
            "used_count": len(used),
            "min_used": min(used) if used else None,
            "max_used": max(used) if used else None,
            "last_dev_nonce": last,
            "zero_used": 0 in used or last == 0,
            "resets_join_nonces": bool(device.get("resets_join_nonces", False)),
        })

    # A non-null last_dev_nonce means a LoRaWAN version that requires a
    # strictly increasing value; used_dev_nonces is the LoRaWAN 1.0.3-style
    # set. The current three registrations return only the latter.
    monotonic_floor = max(last_values, default=-1)
    current_seed = 0
    current_seed_safe = (
        complete and current_seed > monotonic_floor and current_seed not in used_union
    )
    next_legacy_collision = min(
        (value for value in used_union if value >= current_seed),
        default=0x10000,
    )
    collision_free_from_current = (
        next_legacy_collision - current_seed if current_seed_safe else 0
    )

    # Also report the longest common clear run for diagnostics. Starting at
    # zero is preferable here because it maximizes total journal life; the
    # longest-run calculation is useful if a future registration has used 0.
    run_start = monotonic_floor + 1
    best_start: int | None = None
    best_len = 0
    for blocked in sorted(used_union):
        if blocked < run_start:
            continue
        length = blocked - run_start
        if length > best_len:
            best_start, best_len = run_start, length
        run_start = blocked + 1
    if 0x10000 - run_start > best_len:
        best_start, best_len = run_start, 0x10000 - run_start

    print(json.dumps({
        "targets": rows,
        "global_max_seen": global_max if global_max >= 0 else None,
        "current_blank_journal_seed": current_seed,
        "current_seed_safe": current_seed_safe,
        "collision_free_joins_from_current_seed": collision_free_from_current,
        "longest_common_unused_run_start": best_start if complete else None,
        "longest_common_unused_run_length": best_len if complete else None,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
