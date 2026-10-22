# ZuriTrustAI

**Open-source, low-bandwidth maternal-health information, danger-sign screening and referral support.**
Built by [Zuri Circle Limited](https://zuricirclenetwork.com) with technical and cybersecurity advice from Lamar University.

> **Safety and verification status:** ZuriTrustAI is a development project, not a clinically validated medical device. It does not diagnose and does not replace a qualified health worker. Clinical content is a draft pending review and sign-off by the Zuri Circle Chief Medical Officer. See [DISCLAIMER.md](DISCLAIMER.md). Every software feature listed below is implemented in this repository and covered by automated tests (`python -m pytest -q`); re-run them on the exact commit you submit.

---

## The problem

Women in low-connectivity communities across Nigeria and Sub-Saharan Africa can face barriers to timely maternal-health information and referrals. ZuriTrustAI meets them on a **lightweight web page (about 10 KB of HTML/CSS/JS, no external libraries)** and on **WhatsApp** via the Meta Cloud API. The WhatsApp integration is implemented and tested with simulated webhooks; it goes live only once Zuri Circle connects its WhatsApp Business account.

## What it does

| Feature | How |
|---|---|
| **Danger-sign screening** | Users describe symptoms in their own words. A transparent, rules-based engine maps them to WHO-adapted danger signs (handles negation such as "no bleeding" and clause boundaries such as "no fever **but** bleeding") and returns *emergency / same-day / routine* with plain-language advice. |
| **Safety first** | Every free-text message is screened **before** any other answer, so "what should I eat? also I'm bleeding" goes straight to emergency advice. |
| **Verified information** | NLP retrieval (TF-IDF over words + character n-grams, robust to SMS spelling) answers only from a curated, sourced knowledge base. It never generates free-form medical advice; out-of-scope questions get a safe fallback. |
| **Trained NLP classifier (AI safety net)** | A Naive Bayes text classifier (`app/classifier.py`), trained on ~1,000 synthetic examples generated from the clinical danger-sign list (`python -m app.train_classifier`). It gives a second opinion and can only **add** a caution note when the rules find nothing; it never changes or downgrades a rules decision. 5-fold cross-validation on synthetic data: see `eval/REPORT_classifier.md`. Must be retrained on de-identified, consented, clinician-labelled data before real-world claims. |
| **Clinician hand-off (telehealth)** | Users reply `5`/`TALK` at any time, including straight after a danger warning. On WhatsApp, the user's number is shared with Zuri Circle's licensed health professionals **only after the user replies YES**; the call-back ticket carries the triage level and sign ids, never the message text. |
| **90-day execution tracks** | `JOIN`, weekly `CHECKIN`, `PROGRESS`. Stores only a pseudonymous id, start date and check-in weeks; completion = check-ins in 10+ of 13 weeks. Programme completion rate is computed, not self-reported. |
| **Anonymized community health indicators** | `/api/insights` (staff token required) aggregates the de-identified audit log: screens by urgency and week, referrals by state, most common danger signs, unanswered-question gaps, hand-offs and track completion. Counts below 5 are suppressed. |
| **Referral routing** | Emergency cases are routed only to 24-hour secondary/tertiary facilities; routine care to primary health centres. |
| **Economic resilience** | Links to Zuri Circle's 90-day execution tracks and savings guidance. |
| **Privacy by design** | No message text is stored. Phone numbers/session ids are pseudonymized with keyed HMAC. The audit log has an allow-list of fields and rejects free text. `DELETE` clears a session. |
| **Security** | WhatsApp webhook signature verification (`X-Hub-Signature-256`), CSP and security headers, rate limiting that cannot be bypassed with spoofed `X-Forwarded-For`, request-size limits, retry de-duplication. With `ZURI_ENV=production` the app refuses to start with missing or placeholder secrets. |

## Quick start

```bash
git clone https://github.com/mrana15/ZuriTrustAI.git
cd ZuriTrustAI
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                    # replace the secret placeholder; set ZURI_ENV=production when deploying
# Load environment variables using your shell or a trusted local environment loader.
# Avoid printing .env values to the terminal or logs.
python -m app.main                                      # http://127.0.0.1:8000
```

Docker:

```bash
docker build -t zuritrustai .
docker run -p 8000:8000 --env-file .env zuritrustai
```

## Tests and evaluation

```bash
python -m pytest -q                      # 61 unit and API tests
python -m app.train_classifier           # rebuild synthetic data, retrain, cross-validate
python -m eval.run_eval                  # development scenarios  -> eval/REPORT.md
python -m eval.run_eval holdout.json     # held-out scenarios     -> eval/REPORT_holdout.md
```

CI (GitHub Actions, `.github/workflows/ci.yml`) runs all three on every push and **fails if any emergency scenario is classified as routine**. Do not treat results on fictional or previously tuned scenarios as clinical validation.

### Current results (content v0.1.1, fictional scenarios; software testing, not clinical validation)

Generated by `eval/run_eval.py` on 22 Oct 2026; 61 unit/API tests passing. Reports are in `eval/`. The trained classifier added a caution note to 2 of 13 routine development cases and 0 of 7 routine held-out cases; it did not need to rescue any danger case in these sets because the rules caught them all.

| Set | Cases | Exact agreement | Emergencies flagged | Under-triage |
|---|---|---|---|---|
| Held-out, **first run** (before fixes) — [baseline report](eval/REPORT_holdout_baseline_v0.1.0.md) | 24 | 83.3% | 80.0% (8/10) | 4 |
| Development set (rules tuned on it) | 50 | 100% | 100% | 0 |
| Held-out after fixing the gaps it revealed | 24 | 100% | 100% | 0 |

The held-out set found two missed emergencies ("thinking of hurting myself", "newborn breathing very fast"). Both were fixed in content v0.1.1. Because the held-out set has now influenced the rules, **a new, independently written test set reviewed by the Chief Medical Officer is required** before any pilot claim.

## API

| Method | Path | Body / query | Purpose |
|---|---|---|---|
| GET | `/health` | | Status and content versions |
| GET | `/api/danger-signs` | | Danger-sign list (for checklists) |
| POST | `/api/screen` | `{"text": "..."}` or `{"sign_ids": ["swelling"]}` | Screening result |
| POST | `/api/chat` | `{"session_id": "...", "message": "..."}` | Conversational reply |
| GET | `/api/facilities` | `?state=Lagos&level=emergency` | Referral options |
| GET | `/api/resources` | | Economic-capability resources |
| GET | `/api/insights` | `Authorization: Bearer <ZURI_ADMIN_TOKEN>` | Anonymized community health indicators (staff only) |
| GET/POST | `/webhook/whatsapp` | Meta Cloud API | WhatsApp channel |

Example:

```bash
curl -s -X POST localhost:8000/api/screen -H 'Content-Type: application/json' \
     -d '{"text":"my head hurts and my vision is blurry"}'
```

## WhatsApp setup

1. Create a Meta developer app with the WhatsApp product and a test number.
2. Set `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`.
3. Expose the server over HTTPS and register `https://<host>/webhook/whatsapp` as the callback URL with the same verify token; subscribe to `messages`.
4. Without credentials, the intended behavior is **dry-run** mode (replies are computed but not sent). Verify this behavior in tests before deployment. Never use real users until the integration, privacy controls, and escalation pathways have been reviewed.

## Project structure

```
app/
  main.py          Flask app, API, WhatsApp webhook, security headers, rate limiting
  dialogue.py      Channel-independent conversation engine (safety-first)
  screening.py     Danger-sign screening (negation, clause and context handling)
  knowledge.py     Curated knowledge base + retrieval
  nlp.py           Normalization, tokenization, TF-IDF retriever (pure Python)
  referral.py      Facility routing by state and urgency
  privacy.py       Pseudonymization, redaction, allow-listed audit log
  classifier.py    Trained Naive Bayes triage classifier (caution-only safety net)
  train_classifier.py  Builds synthetic training data and trains the classifier
  handoff.py       Consent-based hand-off to licensed health professionals
  tracks.py        90-day execution tracks (SQLite, pseudonymous)
  insights.py      Anonymized community health indicators with small-cell suppression
  sessions.py      Short-lived in-memory session state
  whatsapp.py      Meta WhatsApp Cloud API client, signature verification
  data/            danger_signs.json, knowledge_base.json, facilities.sample.json, capability_resources.json,
                   triage_training.json (synthetic), triage_model.json (trained model)
  static/          Low-bandwidth web client
eval/              Fictional test scenarios and evaluation script
tests/             Unit and API tests
docs/              Architecture, clinical review process
```

## How this repository maps to the UNICEF Venture Fund application

| Application statement | Where it is implemented | Status |
|---|---|---|
| Low-bandwidth web and enterprise WhatsApp channels | `app/static/`, `app/whatsapp.py` | Implemented; WhatsApp tested with simulated webhooks, goes live when Zuri Circle connects its Business account |
| AI/ML maternal-health risk screening | `app/screening.py` (rules) + `app/classifier.py` (trained model) | Implemented; software-tested on fictional data, not clinically validated |
| Natural-language processing | `app/nlp.py`, `app/classifier.py` | Implemented (TF-IDF retrieval, negation handling, Naive Bayes) |
| Clinical routing to telehealth / emergency care under CMO governance | `app/referral.py`, `app/handoff.py`, `docs/clinical_review.md` | Implemented; needs verified facility list and the clinicians' webhook / contact |
| 90-day execution tracks | `app/tracks.py` | Implemented |
| Anonymized community health indicators for resource planning | `app/insights.py` | Implemented (aggregate counts, not predictive) |
| Open source, reusable by other programme countries | `LICENSE` (MIT), JSON content files | Implemented |

The system **does not diagnose**. Describe it as screening, information and referral support.

## Content governance

All clinical content lives in versioned JSON files so clinicians can review it without reading code. See [docs/clinical_review.md](docs/clinical_review.md). `facilities.sample.json` is documented as containing fictional placeholders only and must be replaced with a verified, maintained facility list before any pilot. Confirm the file contents and validate every referral contact with local partners.

## Roadmap (12 months)

1. Clinical review and sign-off of all content by the Chief Medical Officer; independent test set.
2. Local-language support (e.g. Hausa, Yoruba, Igbo, Nigerian Pidgin) with native-speaker review.
3. Verified facility directory with local partners; telehealth hand-off.
4. Security and privacy assessment; data-protection compliance (e.g. Nigeria Data Protection Act 2023).
5. Governed pilot with monitoring of referral quality and user experience; ethics approvals as required.

## Team

- **Zuri Circle Limited** — product, operations, clinical governance (Chief Medical Officer), community.
- **Dr. Md. Masud Rana**, Lamar University — technical advisor: AI/ML, architecture, open-source implementation.
- **Dr. Lucy Tsado**, Lamar University — cybersecurity, digital-risk and data-protection advisor.


## License

[MIT](LICENSE). Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
