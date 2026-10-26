"""Original, offline lead intake sample. No network calls or AI claims."""
import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path


def validate(record):
    if not isinstance(record, dict):
        raise ValueError('Lead must be an object')
    required = {'name', 'email', 'request', 'budget_usd'}
    if set(record) != required:
        raise ValueError('Expected exactly name, email, request, budget_usd')
    result = {}
    for field, limit in [('name', 120), ('email', 254), ('request', 4000)]:
        value = record[field]
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError(f'Invalid {field}')
        result[field] = value.strip()
    result['email'] = result['email'].lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', result['email']):
        raise ValueError('Invalid email')
    budget = record['budget_usd']
    if type(budget) is not int or not 0 <= budget <= 1_000_000:
        raise ValueError('budget_usd must be an integer from 0 to 1000000')
    result['budget_usd'] = budget
    return result


def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL,
        payload TEXT NOT NULL, score INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS receipts (
        key TEXT PRIMARY KEY, digest TEXT NOT NULL,
        lead_id INTEGER NOT NULL REFERENCES leads(id));
      CREATE TABLE IF NOT EXISTS outbox (
        lead_id INTEGER PRIMARY KEY REFERENCES leads(id),
        payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending_review');
    ''')
    return db


def ingest(db, key, record, minimum_budget=300):
    if not isinstance(key, str) or not 1 <= len(key) <= 128:
        raise ValueError('A 1-128 character idempotency key is required')
    if type(minimum_budget) is not int or minimum_budget < 0:
        raise ValueError('minimum_budget must be a nonnegative integer')
    lead = validate(record)
    payload = json.dumps(lead, sort_keys=True, ensure_ascii=False)
    # Include policy in request identity so a changed scoring request cannot replay silently.
    digest = hashlib.sha256((str(minimum_budget) + ':' + payload).encode()).hexdigest()
    try:
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT digest, lead_id FROM receipts WHERE key=?', (key,)).fetchone()
        if previous:
            if previous[0] != digest:
                raise ValueError('Idempotency key reused with different input or scoring policy')
            db.commit()
            return {'lead_id': previous[1], 'status': 'replayed'}
        # Email duplicates are retained as the original lead, never overwritten.
        existing = db.execute('SELECT id FROM leads WHERE email=?', (lead['email'],)).fetchone()
        if existing:
            lead_id, status = existing[0], 'duplicate_email'
        else:
            words = set(re.findall(r'[a-z]+', lead['request'].lower()))
            score = (50 if lead['budget_usd'] >= minimum_budget else 0) + (
                50 if words & {'api', 'crm', 'integration', 'automation'} else 0)
            lead_id = db.execute('INSERT INTO leads(email,payload,score) VALUES (?,?,?)',
                                 (lead['email'], payload, score)).lastrowid
            # Plain-text draft. No send action exists; no external CRM is contacted.
            draft = {'lead': lead, 'score': score, 'classification': 'rules_only',
                     'draft': 'Thank you for your inquiry. We will review the scope and confirm next steps.'}
            db.execute('INSERT INTO outbox(lead_id,payload) VALUES (?,?)',
                       (lead_id, json.dumps(draft, ensure_ascii=False)))
            status = 'created'
        db.execute('INSERT INTO receipts(key,digest,lead_id) VALUES (?,?,?)', (key, digest, lead_id))
        db.commit()
        return {'lead_id': lead_id, 'status': status}
    except Exception:
        db.rollback()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--db', default='pilot.sqlite3')
    parser.add_argument('--key', required=True)
    parser.add_argument('--minimum-budget', type=int, default=300)
    args = parser.parse_args()
    db = connect(args.db)
    try:
        result = ingest(db, args.key, json.loads(args.input.read_text(encoding='utf-8')), args.minimum_budget)
        print(json.dumps(result))
    finally:
        db.close()


if __name__ == '__main__':
    main()
