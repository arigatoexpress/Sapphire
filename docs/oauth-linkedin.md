# LinkedIn OAuth Refresh Recipe

Last verified: 2026-04-28

This recipe documents the safe 3-legged OAuth path for Sapphire's LinkedIn
publisher. It is doc-only: do not paste real tokens into this file, git, shell
history, PR comments, logs, or screenshots.

## When to Use This

Use this flow when Sapphire needs to publish through LinkedIn member or
organization scopes such as `w_member_social` or `w_organization_social`.
LinkedIn access tokens are short-lived, so the runtime must either refresh them
or repeat the authorization-code flow before expiry.

LinkedIn programmatic refresh tokens are not automatically available for every
app. The Microsoft Learn LinkedIn docs describe refresh tokens as available for
approved Marketing Developer Platform partners. If the app is not approved for
programmatic refresh tokens, use the authorization-code flow again with the same
least-privilege scopes.

## Prerequisites

- LinkedIn Developer app created under Ari's account or approved organization.
- Redirect URL registered exactly as it will be used by Sapphire.
- Required product access approved in the LinkedIn Developer Portal.
- Least-privilege scopes selected. Start with `w_member_social`; add
  `w_organization_social` only after the app and organization workflow require
  it.
- Secret storage ready outside git, for example a local secrets file with mode
  `0600` or an approved secret manager.

## Initial Authorization

1. Build the authorization URL:

   ```text
   https://www.linkedin.com/oauth/v2/authorization?response_type=code&client_id=<client_id>&redirect_uri=<url_encoded_redirect_uri>&scope=<url_encoded_scopes>&state=<random_state>
   ```

2. Open it in a browser while logged in as the LinkedIn member who owns the
   publishing consent.
3. Confirm the redirect `state` matches the generated value.
4. Exchange the returned `code` server-side:

   ```bash
   curl -X POST "https://www.linkedin.com/oauth/v2/accessToken" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     --data-urlencode "grant_type=authorization_code" \
     --data-urlencode "code=<authorization_code>" \
     --data-urlencode "client_id=<client_id>" \
     --data-urlencode "client_secret=<client_secret>" \
     --data-urlencode "redirect_uri=<registered_redirect_uri>"
   ```

5. Store only the returned token material in the approved secret store. Never
   commit it. Record the expiry timestamp, not the token value, in operational
   notes.

Expected useful fields:

- `access_token`
- `expires_in`
- `scope`
- `refresh_token`, if the app is approved for programmatic refresh tokens
- `refresh_token_expires_in`, if a refresh token is returned

## Refresh Path

When a refresh token is available, refresh before the access token expires:

```bash
curl -X POST "https://www.linkedin.com/oauth/v2/accessToken" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=refresh_token" \
  --data-urlencode "refresh_token=<refresh_token>" \
  --data-urlencode "client_id=<client_id>" \
  --data-urlencode "client_secret=<client_secret>"
```

Operational notes:

- Treat both access and refresh tokens as secrets.
- Do not assume refresh extends the refresh token lifetime. Track
  `refresh_token_expires_in` and schedule reauthorization before it expires.
- If LinkedIn returns a revocation, invalid-token, or approval error, fall back
  to the initial authorization flow.

## Runtime Contract

Sapphire code should read these values at request time from secret storage:

- `LINKEDIN_CLIENT_ID`
- `LINKEDIN_CLIENT_SECRET`
- `LINKEDIN_REDIRECT_URI`
- `LINKEDIN_ACCESS_TOKEN`
- `LINKEDIN_REFRESH_TOKEN`, when available
- `LINKEDIN_ACCESS_TOKEN_EXPIRES_AT`
- `LINKEDIN_REFRESH_TOKEN_EXPIRES_AT`, when available

Publishing code should fail closed when token material is missing or expired.
It should produce a local operator action item rather than attempting a live
post with stale credentials.

## Verification Without Live Posting

Safe checks:

- Validate environment-variable presence without printing values.
- Validate expiry timestamps are in the future.
- Use a dry-run publisher path that renders the payload but does not call
  LinkedIn.
- For any live LinkedIn API check, use a read-only endpoint first and record
  only status code, scope names, and expiry metadata.

Unsafe checks:

- Printing token values.
- Running a real post from a test or smoke script.
- Storing the authorization-code redirect URL with query parameters in a repo
  note after the code exchange.

## References

- LinkedIn 3-legged OAuth flow: <https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow>
- LinkedIn programmatic refresh tokens: <https://learn.microsoft.com/en-us/linkedin/shared/authentication/programmatic-refresh-tokens>
