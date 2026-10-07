# Organizer onboarding

Use this workflow for assembled payloads registered in a shared Stratolink TTN application. People registering radios in their own TTN applications use the dashboard's registration flow instead.

The permanent board address is `/activate/{deviceId}`. It identifies the payload but grants no ownership. A separate, expiring claim link adds the payload to a signed-in GitHub account. Fresh links use `/activate/{deviceId}#k={token}` so the credential stays out of the initial HTTP request and access logs. Claiming does not mark it flying or change its recorded launch.

## Staff access

Set `PAYLOAD_STAFF_USER_IDS` on the server to a comma-separated list of the organizers' verified Supabase user UUIDs. Obtain those IDs from Supabase Authentication after GitHub sign-in. A GitHub username, reservation name, or client-supplied role is not staff authorization. Keep `COMMUNITY_REGISTRATION_ENABLED` disabled in Production until the deployment cutover is verified.

The CLI authenticates with the organizer's current Supabase access token from their signed-in dashboard session. Save that token as plain text in a file outside the repository, owned by the organizer and readable only by them (`chmod 600`). Do not use a GitHub personal access token, Supabase service key, or TTN API key as the session token. It expires with the session; sign in again when needed. Do not paste credentials into command arguments, screenshots, or chat.

The commands below use illustrative paths and identifiers. Create the parent output directory first. Each applied operation requires a new output directory; the CLI creates it with mode `700` and writes files with mode `600`.

```sh
npm run onboarding:staff -- inventory \
  --origin https://stratolink.org \
  --token-file /private/stratolink/session
```

Inventory includes reservations, ownership state, known radio identifiers, and active shared integrations. It excludes legacy PINs, claim credentials, webhook tokens and owner UUIDs. Confirm the recipient and existing reservation before preparing a board. Keep the exact device ID. Do not replace an existing reservation because its radio is not provisioned yet.

## Prepare the radio

1. Open the intended shared application in the TTN Console. Check for an existing end device with the planned device ID or DevEUI before creating anything. For an existing radio, preserve its keys, session, frame counters and nonce history. Do not delete and recreate it.
2. For a new radio, use **End devices > Register end device > Enter end device specifics manually**. Match the board's firmware, frequency plan and radio module. The US915 development settings are in [Getting started](https://stratolink.org/docs/getting-started#register-with-the-things-network): OTAA, LoRaWAN 1.0.3, Regional Parameters 1.0.3 revision A, Class A, and US915 FSB 2. Use the JoinEUI configured by that firmware.
3. Generate credentials only for the new radio. Keep its DevEUI, JoinEUI and AppKey in the private board configuration. Populate the actual firmware template supplied for that board. The older template has three unqualified credential macros; the development template has regional overrides. Do not rename macros or copy another payload's AppKey.
4. Finish Console registration so the Identity, Network, Application and Join Server records all exist. Install the matching device-level uplink decoder. Check the radio settings and successful OTAA join, then inspect a real uplink. A visible entry in the device list alone is not enough.
5. Repeat only for the additional radio regions the hardware and firmware support. The current development firmware uses separate regional DevEUIs and AppKeys. Record each cluster, application, TTN device ID, DevEUI and frequency plan against the same physical payload. Never infer that two records are the same payload from their suffixes.
6. Confirm the application already has its approved shared Stratolink webhook and an active integration listed by the CLI. Keep its URL, Authorization header and other settings unchanged. If no integration exists for that application and cluster, stop and have an administrator set one up and verify it. This tool does not create integration credentials or reconfigure live hooks.

See the existing [hardware instructions](https://stratolink.org/docs/hardware) for programming and the [TTN delivery checks](https://stratolink.org/docs/troubleshooting#ttn-receives-packets-but-the-dashboard-is-empty) for reception problems. Do not replay historical flight packets into production as a setup test.

## Attach the verified radio

Create a temporary TTN application API key with permission to read end devices, including the Join Server device record, then save it in a separate mode `600` file outside the repository. No TTN write or root-key read permission is needed. The server checks the Identity, Network, Application and Join Server registries. It requests identity fields from the Join Server, never the AppKey, and does not retain the API key. If a registry rejects the read, check the key's application rights rather than adding broad write access.

Choose the existing shared integration ID from inventory. First inspect the proposed operation:

```sh
npm run onboarding:staff -- connect \
  --origin https://stratolink.org \
  --token-file /private/stratolink/session \
  --device reserved-callsign \
  --dev-eui 0123456789ABCDEF \
  --cluster nam1 \
  --application existing-application \
  --integration 11111111-2222-4333-8444-555555555555
```

The default dry run reads staff inventory only. It does not verify TTN or change either service. Repeat with these options to verify TTN and attach the identity:

```sh
  --ttn-key-file /private/stratolink/ttn-read-key \
  --out /private/stratolink/connection-01 \
  --apply
```

Append those options to the complete command above. An existing conflicting mapping is rejected. A connection to another supported region preserves the primary DevEUI, all earlier connections and all telemetry. The existing shared webhook credential is reused, not rotated. The output directory contains a connection receipt. Revoke the temporary TTN verification key when finished.

## Issue the ownership label

For an unowned payload with a verified primary DevEUI:

```sh
npm run onboarding:staff -- issue \
  --origin https://stratolink.org \
  --token-file /private/stratolink/session \
  --device reserved-callsign \
  --dev-eui 0123456789ABCDEF
```

After reviewing the dry run, repeat the complete command with `--apply --out /private/stratolink/label-01`.

Open `label.html` from that private directory and print it locally. `claim-qr.svg` contains the printable QR; `result.json` contains the activation URL and expiry. Treat all three as private until handing the label to the intended recipient. The claim is valid for seven days and can be used once. Issuing another link invalidates the previous one. Do not engrave an expiring claim credential onto the permanent PCB.

If a signed-in user already owns the reservation, do not issue a second claim. Attach its verified radio and let that owner manage the payload directly. For an unowned reservation, the old reservation name is preserved for organizer review but does not authenticate the recipient.

The recipient scans the label, signs in with GitHub, confirms the payload and claims it. A device-only or expired link retains the device context but cannot transfer ownership. Previously exposed legacy PINs and launch tokens are not accepted as account-ownership proof. Scanning never resets flight status, launch time, launch coordinates or telemetry.

## Review and failure handling

- Test new claims and bindings against disposable fixtures or dedicated review payloads. Do not claim the two official historical balloons as a test.
- For local or protected preview API review with production `SITE_URL`, add `--claim-origin https://stratolink.org` when issuing a label. This checks the expected printed URL without sending production traffic to a protected preview. A preview-generated production link is not a completed production test.
- A failed request is never retried automatically. Inspect inventory before retrying an interrupted write. If a claim response was lost, issue a fresh label after checking that the payload is still unowned.
- A failed attachment does not delete TTN registrations. Resolve the mismatched registry or reservation before retrying.
- Keep session files, TTN keys and printed claim artifacts outside the repository. Remove them securely through the normal local workflow when no longer needed.

The old `/api/admin/register-payload` implementation is not used. Its write-then-delete rollback could remove an existing TTN registration. Automated TTN creation is deliberately outside this tool; the Console workflow above preserves the same organizer outcome with explicit registry checks.
