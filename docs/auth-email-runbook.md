# Auth/Email Runbook (Railway + Resend)

## Register status codes (`POST /api/auth/register`)

- `200`: user created and verification email send completed successfully.
- `409`: email already registered (Resend is not called in this branch).
- `422`: request validation error (email/password/terms payload).
- `503`: verification email send failed (user creation is rolled back).

## First checks (Railway variables)

Required for registration and password-reset email delivery:

- `RESEND_API_KEY` — from [Resend API Keys](https://resend.com/api-keys)
- `RESEND_FROM_EMAIL` — sender, e.g. `Acme <onboarding@resend.dev>` (domain must be [verified](https://resend.com/domains))
- `RESEND_TEMPLATE_VERIFY_EMAIL` — template id for email verification (from [Resend Templates](https://resend.com/templates))
- `RESEND_TEMPLATE_PASSWORD_RESET` — template id for password reset

### Template variables (must match your Resend templates)

- **Verify email template**: `CONFIRM_LINK` (full URL with token), `USER_NAME` (display name or "there").
- **Password reset template**: `RESET_LINK` (full URL with token), `USER_NAME`.

Define these variables in your templates in the Resend dashboard and use them in the template body (e.g. `{{{CONFIRM_LINK}}}`, `{{{USER_NAME}}}`).

Recommended / supporting:

- `FRONTEND_URL`, `EMAIL_VERIFY_PATH`, `PASSWORD_RESET_PATH` (used to build links passed into templates)

## What to inspect in Railway logs

Search for register flow markers:

- `register attempt`
- `register duplicate_email`
- `register verification_email_send_started`
- `register verification_email_sent_ok REGISTER_EMAIL_SENT`
- `register verification_email_send_failed`
- `register success`

Search for Resend flow markers:

- `Resend send success type=verify_email`
- `Resend send success type=password_reset`
- `Resend send failure type=...`

Notes:

- Emails are masked in logs.
- API keys must never appear in logs.

## What to inspect in Resend

- [Dashboard](https://resend.com/emails): delivery status, opens, bounces.
- Domain and sender verified; template IDs match env vars; template variables match (`CONFIRM_LINK` / `RESET_LINK`, `USER_NAME`).

## Reproduce with curl

### Register (new email)

```bash
curl -i -X POST "https://<your-domain>/api/auth/register" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: manual-smoke-001" \
  -d '{
    "displayName": "Smoke User",
    "email": "smoke-user@example.com",
    "password": "password123",
    "confirmPassword": "password123",
    "termsAgree": true
  }'
```

### Duplicate register (should be `409`)

Repeat the same request and confirm:

- HTTP `409`
- backend log contains `register duplicate_email`

### Resend verify email

```bash
curl -i -X POST "https://<your-domain>/api/auth/verify-email/request" \
  -H "Content-Type: application/json" \
  -d '{"email":"smoke-user@example.com"}'
```

Expected:

- HTTP `200`
- generic response body (privacy-safe)

## Common interpretations

- `409` on register: email already registered; Resend is not called.
- `503` + `Resend send failure`: check Resend API key, from address, template ids and variables; see log `error=...`.
- `422`: frontend payload or validation mismatch.
