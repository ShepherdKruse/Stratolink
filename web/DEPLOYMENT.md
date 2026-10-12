# Deployment

The shared deployment uses [Stratolink-hq/Stratolink](https://github.com/Stratolink-hq/Stratolink), the existing Vercel project `shepherdkruses-projects/v0-strato-link-marketing-site`, and Supabase project `iazmnyyfsobucndqncgw`.

## Vercel

Keep the Git integration connected to `Stratolink-hq/Stratolink` with production branch `main`. Use Root Directory `web`, Node 22, the Vite preset, and output directory `dist`. Routes and security headers are in [vercel.json](vercel.json).

The complete environment contract is in [README.md](README.md#deployment) and [.env.example](.env.example). In particular:

- Set `SITE_URL=https://stratolink.org` in Production.
- Set `COMMUNITY_REGISTRATION_ENABLED=true` to accept new balloon registrations and TTN connections.
- Set `PAYLOAD_STAFF_USER_IDS` to the approved organizers' Supabase user UUIDs, not GitHub usernames.
- Set an independent `PAYLOAD_CLAIM_COOKIE_SECRET` for each environment. Generate 32 random bytes locally and enter the value directly in Vercel's sensitive server settings.
- Keep server database credentials and `BLOB_READ_WRITE_TOKEN` server-only. Never prefix a private value with `VITE_` or `NEXT_PUBLIC_`.

Public build variables require a rebuild. Server settings also require a new deployment to reach existing functions.

## Authentication and previews

Configure the GitHub provider in the existing Supabase project. Its OAuth callback is `https://iazmnyyfsobucndqncgw.supabase.co/auth/v1/callback`; the GitHub client secret stays in Supabase.

Allow `https://stratolink.org/dashboard` as the production return URL. Add local and preview callbacks individually, with their exact origin and `/dashboard` path. Add those same origins to `AUTH_ALLOWED_ORIGINS` in the environment being tested. Do not use wildcard preview domains.

Keep Vercel preview protection enabled. Protected previews can test the website and account UI, but cannot receive ordinary TTN deliveries. Leave real webhooks pointed at production. When reviewing accounts in a preview against the shared backend, use dedicated test payloads and preserve the production `SITE_URL` so generated webhook URLs point to the live handler.

## Database

The current application migrations are in [supabase/migrations](../supabase/migrations/). Historical schema files remain in [lib/supabase/migrations](lib/supabase/migrations/). That older chain contains duplicate migration versions and is not a complete fresh-project installer. Review the actual database history before applying migrations; do not replay already-applied files under new versions.

The [backend integration harness](scripts/backend-integration.mjs) builds a disposable PostgreSQL database from the required baseline and current migrations. Use `npm run test:backend` with Docker to verify the sequence.

The raw-data cutover in `20261007225324_private_raw_data_cutover.sql` removes browser access to application tables, views, and the legacy coordinate RPC. The website uses authenticated server APIs and privacy-filtered public endpoints. Keep the cutover in place when rolling back website code; the retired browser client depends on raw reads and is not a compatible rollback.

Extension-owner permission changes are separate from application migrations. See [platform hardening](../supabase/platform-hardening/README.md).

## Registration and claims

Use [organizer onboarding](ONBOARDING.md) for inventory, verified regional TTN bindings, and printed ownership labels. Existing device IDs, telemetry, radio sessions, and nonce history must survive registration changes.

Fresh claim links use `/activate/{deviceId}#k={token}`. The one-time token expires after seven days. A device ID, old PIN, or legacy launch token does not establish ownership. The server exchanges the fragment for a short-lived, origin-bound HttpOnly claim cookie before GitHub sign-in.

Official team membership comes from verified GitHub provider IDs. It gives the three maintainers shared access to official balloons, but does not grant staff inventory privileges. Those require `PAYLOAD_STAFF_USER_IDS`.

## Release checks

1. Run `npm run verify` and `npm run test:backend` from `web`.
2. Confirm the Vercel preview uses the intended commit and project settings.
3. Check sign-in, registration, ownership isolation, and claim expiry using dedicated review payloads. Do not claim the historical official balloons or replace their radio mappings as a test.
4. Check one real uplink through a dedicated TTN connection. An unsigned request being rejected does not verify delivery. Do not replay historical packets into the live archive.
5. After merging, run `node web/scripts/check-production.mjs <commit-sha>` from the repository root. The production-verification workflow runs the same check after a successful production deployment.
6. Verify the forecast worker independently of stored forecast reads. Keep the GitHub Actions secrets available after a repository transfer; `.github/workflows/gfs-ingest.yml` is the scheduled writer.
7. Confirm old deployments and aliases are protected or retired. Their server functions retain deployment-time credentials. An old unauthenticated webhook or unmasked forecast must not remain public.

Use a corrected server-backed release for rollback. Do not restore the retired site or loosen database permissions to make it work.
