# Changelog

## 0.2.0 (22 Oct 2026)
- Trained NLP triage classifier (Naive Bayes, synthetic training data) as a caution-only safety net behind the rules engine; training script with cross-validation report.
- Consent-based hand-off to Zuri Circle licensed health professionals (`5` / `TALK`).
- 90-day execution tracks: `JOIN`, `CHECKIN`, `PROGRESS`; computed completion rate; erased by `DELETE`.
- `/api/insights`: anonymized community health indicators with small-cell suppression (staff token).
- Evaluation report shows the classifier's caution notes; 61 tests.

## 0.1.2 (22 Oct 2026)
- Production mode (`ZURI_ENV=production`, default in Docker) refuses to start with missing or placeholder `ZURI_HMAC_SECRET`, or with WhatsApp enabled but no webhook secret / verify token.
- Rate limiting and audit keys use the direct peer address; `X-Forwarded-For` is trusted only from `ZURI_TRUSTED_PROXIES` reverse proxies (spoofing fix).
- Documentation revised: stronger `.gitignore`, `.env.example` placeholders, contribution rules, vulnerability-reporting process, release checklist; security controls mapped to tests.
- 5 new tests (46 total).

## 0.1.1 (20 Oct 2026)
- Danger-sign content v0.1.1: fixed two emergencies missed by the held-out evaluation; added urinary-burning and high-blood-pressure signs.

## 0.1.0 (20 Oct 2026)
- Initial release: web + WhatsApp channels, danger-sign screening, knowledge-base retrieval, referral routing, privacy layer, tests and evaluation.
