# StratoLink-2 backend rollout

Status: prepared and locally verified; **not applied to production**.

The connected Supabase management integration was audited read-only on
2026-07-27. It lists one healthy but unrelated project and denies a direct
lookup of the StratoLink project behind the public Data API. No SQL, DDL,
migration, or function deployment was attempted. The redacted evidence is
`logs/stratolink2_supabase_management_access_20260727.json`. Do not apply these
migrations through the current connector: connect the correct project or use
an explicitly approved project-bound migration channel first.

TTN Network Server MAC scheduling is a separate production surface from the
webhook rollout. On 2026-07-27 a guarded, field-masked update explicitly set
`mac_settings.status_count_periodicity=0` and
`mac_settings.status_time_periodicity=0s` on the NA/EU/AS StratoLink-2 records,
then read back all three as disabled. This prevents repeated `DevStatusReq`
traffic that the compact flight stack authenticates but does not answer. Keep
those device-specific values through the webhook rollout. The active NA
session's already-sent request retired on the first post-change uplink without
a replacement; the following uplink contained no DevStatus, unanswered, or
downlink-schedule event and all three regional pending counts stayed zero.
Passing on-air evidence is
`logs/stratolink2_ttn_devstatus_postchange_phase2b_20260727.json`. Re-enable
only after a future image implements and qualifies `DevStatusAns`.

The read-only production contract probe is:

```sh
analysis/.venv/bin/python analysis/diagnostics/supabase_schema_probe.py
```

It refuses secret/service-role keys, uses only the configured publishable key,
selects zero rows, and names every common ingest, telemetry-v2, and CTT-age
column required by the hardened webhook. The 2026-07-27 recheck remains
fail-closed: `telemetry.ttn_device_id` is absent and both event tables return
PGRST205. Create-once evidence is
`logs/stratolink2_supabase_contract_recheck_20260727.json`.
`contract_ready=true` is necessary before deployment; it does not replace the
RLS, index, webhook-secret, or end-to-end acceptance checks below.

## Reproducible local preflight

From `web/`, run:

```sh
npm run verify
npm run build
```

`verify` runs Next core-web-vitals ESLint, full-tree TypeScript, the exact
firmware-to-web CTT/B2B/telemetry vectors, and webhook
authorization/identity/body-boundary cases. Its TypeScript host runner requires
Node 22.6 or newer. The production build also fetches the configured Inter and
JetBrains Mono definitions from Google Fonts, so a network-denied qualification
shell can prove `verify` but cannot independently close the build gate.

## Why order matters

The deployed route currently accepts unauthenticated TTN JSON and production
does not contain a `stratolink-2` device row, the fPort-11/fPort-12 tables, or
TTN replay-identity columns. Deploying the hardened route first would reject
real uplinks. The existing route ignores extra request headers, so all
prerequisites can be staged without interrupting ingestion.

## Zero-loss rollout order

1. Preserve a current telemetry export and note the latest TTN FCntUp and
   Supabase row time.
2. Register canonical device `stratolink-2` through the authenticated
   registration/admin flow. Verify it has a nonempty private claim code (report
   only presence, never its value); a public `/claim` reservation row is not a
   provisioned fleet identity and the hardened webhook rejects it.
3. Apply, in order, to the actual StratoLink Supabase project:
   - `009_wildlife_detections.sql`
   - `010_b2b_packets.sql`
   - `20260725090324_ttn_ingest_integrity.sql`
   - `20260725184000_ctt_detection_age.sql`
   - `20260725222000_telemetry_observability_v2.sql`
4. Verify the migration before changing application traffic:
   - all three telemetry/event tables have `ttn_device_id`,
     `dev_addr`, optional `session_key_id`, `ttn_received_at`, and `f_cnt`;
   - all three unique indexes cover `ttn_device_id`, `ttn_received_at`, and
     `f_cnt`;
   - anon/authenticated roles have SELECT only;
   - claim/token columns on `devices` are not selectable by anon;
   - `latest_telemetry` has `security_invoker=true`;
   - service role retains required DML.
5. Generate a new independent random webhook secret of at least 32 characters.
   Do not reuse a TTN API key, Supabase key, admin key, or launch token.
6. Add `TTN_WEBHOOK_SECRET` to the production deployment environment. Do not
   put it in a `NEXT_PUBLIC_*` variable or commit it.
7. Add this header to every regional TTN webhook while the old route is still
   deployed:

   `Authorization: Bearer <TTN_WEBHOOK_SECRET>`

   Current records:

   - NA application `stratolink`: webhook `stratolink-web`
   - EU application `eu-stratolink`: webhook `stratolink-vercel`
   - AS application `as-stratolink`: webhook `stratolink-vercel`

   All three point to `https://stratolink.org/api/ttn-webhook`. Read each
   webhook back and compare the value privately; logs/reports should show only
   header presence and length.
8. Deploy the hardened web build last. The first request reaching it will
   already have a registered device, compatible schema, and valid header.

## Acceptance checks

1. POST `{}` without authorization: HTTP 401, no database write.
2. POST with a wrong token: HTTP 401, no database write.
3. Valid real fPort-1 uplink: HTTP 200 and exactly one telemetry row containing
   raw TTN device ID, normalized DevAddr, TTN server receive time, FCntUp, and
   the session ID when TTN supplies one.
4. Replay that exact authenticated webhook body: HTTP 200 with
   `duplicate=true`; row count remains unchanged. The route must acknowledge
   `23505` only when PostgreSQL names that table's exact
   `idx_*_ttn_delivery` index. A different unique-constraint violation is a
   server error, not an idempotent retry, and must not be silently converted to
   HTTP 200.
5. A later manual or OTAA session may reuse DevAddr and FCntUp, but its
   distinct TTN server receive time must insert normally.
6. Unsupported fPort, truncated/oversized telemetry, invalid CTT, and invalid
   B2B frames return HTTP 400 with no insert.
7. A public callsign-reservation row with no private claim code returns HTTP
   403 and creates no telemetry/event row.
8. Public-key attempts to insert/update `devices` or telemetry fail.
9. Public dashboards still read permitted device and telemetry fields.
10. `/api/test-env` returns 404 in production.
11. Refresh the Supabase soak export and run:

    `SUPABASE_PUBLISHABLE_KEY=... python3 analysis/diagnostics/export_supabase_soak.py`

    `python3 analysis/diagnostics/backend_ingest_summary.py --final`

12. Read back NA/EU/AS webhook records and require the Authorization header on
    all three. A future geographic handover must not lose ingestion because
    only the local region was updated.
13. Because webhook queueing is currently disabled, prove the Storage recovery
    path without writing:

    ```sh
    TTN_API_KEY=... python3 analysis/diagnostics/ttn_storage_replay.py \
      --after <last-verified-TTN-time>
    ```

    The command prints only identity/count metadata and never payloads or
    credentials. After the hardened endpoint and integrity migration are live,
    an authorized recovery may add `--apply --webhook-url
    https://stratolink.org/api/ttn-webhook` with `TTN_WEBHOOK_SECRET` in the
    environment. Apply mode first requires an unauthenticated probe to return
    HTTP 401; it refuses to replay into the legacy route. Enable and verify
    Read-only package-association checks currently confirm exactly one
    `storage-integration` default association at FPort 100 on each of NA, EU,
    and AS. NA also contains current StratoLink-2 rows. Reconfirm those
    associations after configuration changes and add the same protection when
    a future AU application is provisioned.

## Rollback

The migrations are additive for historical rows and the old route ignores the
new Authorization header. If the hardened deployment fails, roll back only the
web deployment while retaining the staged schema, secret, and TTN header. Do
not drop columns/tables or remove the header during incident recovery.

# Current TTN webhook message-type state

NA, EU, and AS each previously sent both `uplink_message` and `join_accept` to
the same uplink-only route. A real reset/rejoin produced `as.webhook.fail`
immediately after join forwarding. On 2026-07-27 a guarded single-field update
cleared only `join_accept`; HTTP-200 readback proved `uplink_message` remained
enabled in all three regions. The redacted immutable evidence is
`logs/stratolink2_ttn_join_webhook_remediation_20260727.json`. Keep join-accept
delivery disabled unless a separately authenticated, tested consumer and path
are intentionally added. This TTN configuration fix does not replace the
database migrations, registry provisioning, authenticated uplink proof, or
retry/replay qualification below.

The first following precursor uplink at `2026-07-27T10:01:35.631Z` reached
Network Server and Application Server. The TTN audit stream omitted its Storage
event, so the first watcher remains a failed artifact. An authoritative Storage
API query and publishable-key-only Supabase export each returned exactly one row
at `10:01:35.832312Z`; the corrected, hash-bound evidence is
`logs/stratolink2_retry2_posttransition_delivery_20260727.json`. This proves the
legacy uplink path survived the message-type change. It does not prove the
hardened route, missing schema columns/tables, registry row, or retry behavior.
