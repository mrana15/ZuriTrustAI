# Security policy

## Reporting a vulnerability

Please do not publish exploit details or sensitive data in a public issue. If private vulnerability reporting is enabled for this GitHub repository, use the repository's **Security → Report a vulnerability** workflow. Otherwise, contact the repository maintainers privately using a verified contact channel published by Zuri Circle Limited.

**Before making this repository public:** configure and test a monitored security contact or enable GitHub private vulnerability reporting. Do not leave this process unowned.

## Implemented security and privacy controls

Each control below is implemented and has an automated test (`tests/`). Re-run `python -m pytest -q` before making a security or privacy claim, and note that tests are not a substitute for an independent security audit.

| Control | Code | Test |
|---|---|---|
| Message text never persisted; audit log accepts only allow-listed, de-identified fields | `app/privacy.py` | `test_audit_log_refuses_free_text_fields`, `test_audit_log_never_contains_message_text` |
| Phone numbers / session ids pseudonymized with HMAC-SHA256 and a deployment secret | `app/privacy.py` | `test_pseudonymize_is_stable_and_keyed` |
| Production refuses to start with missing or placeholder secrets, or WhatsApp without a webhook secret | `app/config.py` | `ProductionConfigTests` |
| WhatsApp webhook signatures verified (`X-Hub-Signature-256`) | `app/whatsapp.py` | `test_whatsapp_rejects_bad_signature` |
| Client-supplied `X-Forwarded-For` ignored unless `ZURI_TRUSTED_PROXIES` is set | `app/main.py` | `test_spoofed_forwarded_for_does_not_bypass_rate_limit` |
| CSP and security headers; 64 KB request limit; per-client rate limiting | `app/main.py` | `test_health_and_index`, `test_rate_limit` |
| Clinician hand-off shares a phone number only after explicit YES; tickets never contain message text | `app/handoff.py`, `app/dialogue.py` | `test_whatsapp_handoff_requires_consent_and_sends_no_text` |
| Community indicators are aggregate only, staff-token protected, counts below 5 suppressed | `app/insights.py`, `app/main.py` | `test_insights_auth_and_suppression` |
| 90-day track data is pseudonymous and erased by `DELETE` | `app/tracks.py` | `test_track_flow_and_delete` |
| Web client inserts text with `textContent` only and loads no third-party scripts | `app/static/app.js` | manual review |
| Secrets read from environment; `.env` git-ignored | `app/config.py`, `.gitignore` | manual review |

## Deployment checklist

- [ ] Use HTTPS behind a correctly configured reverse proxy and set `ZURI_TRUSTED_PROXIES` to the number of proxies you control (default 0 trusts none).
- [ ] Set `ZURI_ENV=production` (the Docker image does this by default).
- [ ] Set strong, unique values for `ZURI_HMAC_SECRET`, `WHATSAPP_APP_SECRET`, and `WHATSAPP_VERIFY_TOKEN`; reject placeholders and missing secrets in production.
- [ ] Keep credentials out of Git history, logs, screenshots, and video recordings. Rotate any secret that was exposed.
- [ ] Restrict access to logs and define retention and deletion procedures.
- [ ] If multiple instances are deployed, use a properly secured shared store for sessions and rate limits.
- [ ] Complete a data-protection impact assessment and review applicable laws in each deployment country.
- [ ] Complete security testing and incident-response planning before any real-user pilot.
- [ ] Do not use real patient data in development, tests, demos, or evaluation datasets.
