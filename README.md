# Lead Intake Pilot

A small, original Python work sample for a paid lead-qualification integration pilot. Built with Codex for Daksh Verma on 26 October 2026; uses synthetic data only.

## Demonstrated behavior

- Validates structured lead records and rejects unknown fields.
- Normalizes emails, retains original records on duplicate email submission.
- Scores with an explicit configurable budget threshold and whole-word service matching.
- Stores a human-review acknowledgment draft and CRM outbox item in SQLite.
- Serializes duplicate requests with an idempotency key and atomic transaction.
- Rejects the same key with different input or scoring policy.
- Rolls the entire operation back on outbox failure.

This is an offline rules-based prototype, not an LLM-powered product or production CRM integration. It sends no messages, contacts no external API, and makes no payments. The score is an illustrative business rule, not a validated prediction. SQLite holds plaintext data; use synthetic inputs only.

## Run (Python 3.11+; no dependencies)

```powershell
python -m unittest -v
python intake.py example.json --db pilot.sqlite3 --key sample-001
python intake.py example.json --db pilot.sqlite3 --key sample-001
```

Expected: first command creates one lead; replay returns the same lead ID without another outbox item. Tests cover duplicate submissions including two concurrent connections, conflicting keys, policy changes, validation, rollback and pending review.

## Proposed client pilot

US$100 for a separately agreed milestone: connect one existing intake source to one sandbox CRM endpoint, retain a local idempotency record, generate acknowledgment drafts for human approval, and demonstrate duplicate/error handling with synthetic records. Confirm the actual API and authentication requirements before accepting the milestone. Client funds the milestone before implementation starts. Ongoing work may be proposed at US$25/hour; capacity is confirmed before agreement.

An optional future LLM extraction step must validate output using the same schema and have timeouts, redacted logs, budget controls and a human review path. This sample does not implement that step. A production service also needs authentication, access control, encrypted storage, retention controls, monitoring and a durable retry worker before real customer data is used.

## Rights

MIT. All included application source and sample data were newly authored for this work sample; no startup/client repository code or assets were copied. Python and SQLite are runtime dependencies governed by their respective licenses.
