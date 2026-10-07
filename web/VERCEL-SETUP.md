# Vercel settings for the site release

Use the existing `shepherdkruses-projects/v0-strato-link-marketing-site` project. PR [#77](https://github.com/ShepherdKruse/Stratolink/pull/77) is merged and the new site is live at [stratolink.org](https://stratolink.org). Supabase migrations, the raw-data privacy cutover and production GitHub OAuth are verified. Production registration is still disabled pending the environment update and redeploy below.

## 1. Add these server variables

In **Settings > Environment Variables**:

| Variable | Preview | Production |
| --- | --- | --- |
| `SITE_URL` | `https://stratolink.org` | `https://stratolink.org` |
| `AUTH_ALLOWED_ORIGINS` | `https://v0-strato-link-marketing-sit-git-ccbef2-shepherdkruses-projects.vercel.app` | Leave unset |
| `COMMUNITY_REGISTRATION_ENABLED` | `true` | Set `true` and redeploy; the privacy cutover is verified |
| `PAYLOAD_STAFF_USER_IDS` | Teddy's verified Supabase user UUID | Same UUID |
| `PAYLOAD_CLAIM_COOKIE_SECRET` | Generate a new secret | Generate a different new secret |

Find Teddy's User UID in **Supabase > Authentication > Users**, using the GitHub account `Twarner491`. Additional organizers can be added as comma-separated UUIDs after they sign in with GitHub. The staff value grants organizer privileges; it is not a GitHub username. Keep account UUIDs in the server settings rather than this public repository.

Generate each cookie secret locally with:

```sh
node -p "require('crypto').randomBytes(32).toString('base64url')"
```

Enter the results directly into Vercel as sensitive server variables. Do not send them in chat or put them in GitHub. Keep separate Preview and Production values.

Retain the existing Supabase server credential, public Supabase configuration, Mapbox token and private forecast `BLOB_READ_WRITE_TOKEN`, with the appropriate Preview/Production scopes. Keep Root Directory `web` and Node 22; the repository specifies the Vite build settings. Public auth accepts the existing `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` names as well as the new `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` names. The GitHub OAuth client secret stays in Supabase, not Vercel.

## 2. Redeploy and share the preview

For further preview review, redeploy the review branch after saving its Preview variables. From that deployment, choose **Share > Anyone with the link** and send Teddy the generated link. Keep deployment protection enabled. Use the branch URL above for that review; a different hostname requires matching allowed-origin and Supabase callback settings.

This enables website/account review. Leave real TTN webhooks pointed at production. A protected preview cannot receive normal TTN deliveries.

## 3. Production handoff

The production site and database privacy cutover are complete. Confirm the Production variables above, set `COMMUNITY_REGISTRATION_ENABLED=true`, and redeploy the current `main` deployment. Then verify registration, reservation, owner status changes, a dedicated TTN connection and a QR claim before announcing registration. Production checks have established unsigned-webhook rejection, not a completed live TTN delivery. Verify that old deployment URLs and aliases are protected or retired so they cannot continue serving the old webhook or unmasked data.

The detailed verification and cutover sequence is in [DEPLOYMENT.md](DEPLOYMENT.md).
