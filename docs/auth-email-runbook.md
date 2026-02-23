# Auth/Email Runbook (Railway + Mailjet)

## Register status codes (`POST /api/auth/register`)

- `200`: user created and verification email send completed successfully.
- `409`: email already registered (Mailjet is not called in this branch).
- `422`: request validation error (email/password/terms payload).
- `503`: verification email send failed (user creation is rolled back).

## First checks (Railway variables)

Required for registration email delivery:

- `MAILJET_API_KEY`
- `MAILJET_SECRET_KEY`
- `MAILJET_FROM_EMAIL`

Recommended / supporting:

- `MAILJET_FROM_NAME`
- `MAILJET_API_URL` (default should point to `api.mailjet.com`)
- `MAILJET_TIMEOUT_SECONDS`
- `FRONTEND_URL`
- `EMAIL_VERIFY_PATH`

## What to inspect in Railway logs

Search for register flow markers:

- `register attempt`
- `register duplicate_email`
- `register verification_email_send_started`
- `register verification_email_send_failed`
- `register success`

Search for Mailjet flow markers:

- `Mailjet send success`
- `Mailjet send failure`
- `Mailjet retry scheduled`

Notes:

- Emails are masked in logs.
- API keys / secrets must never appear in logs.

## What to inspect in Mailjet

- API key belongs to the expected account/project.
- `MAILJET_FROM_EMAIL` sender/domain is verified.
- Events for the target recipient around the request timestamp.
- Suppression / blocklist state for the recipient.

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
- no new Mailjet event
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

- `409` on register response: email already registered (duplicate-email branch); Mailjet is not called.
- `503` + `Mailjet send failure`: Mailjet transport/HTTP/message error; check sender verification and API keys.
- Mailjet HTTP **409** in logs: Mailjet returned Conflict. The app retries once; if it keeps failing, check Mailjet dashboard (sender/domain verification, account limits) and the logged `detail=` (ErrorCode/ErrorMessage). Sender and domain must be verified in [Sender domains & addresses](https://app.mailjet.com/account/sender).
- `422`: frontend payload bug or validation mismatch.
