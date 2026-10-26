import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from intake import connect, ingest, validate

LEAD = {'name': 'Synthetic Buyer', 'email': 'buyer@example.com',
        'request': 'Connect a CRM API integration', 'budget_usd': 500}


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(':memory:')

    def tearDown(self):
        self.db.close()

    def test_replay_creates_one_outbox_item(self):
        self.assertEqual(ingest(self.db, 'a', LEAD)['status'], 'created')
        self.assertEqual(ingest(self.db, 'a', LEAD)['status'], 'replayed')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0], 1)

    def test_conflicting_key_does_not_change_data(self):
        ingest(self.db, 'a', LEAD)
        with self.assertRaises(ValueError):
            ingest(self.db, 'a', dict(LEAD, budget_usd=20))
        self.assertEqual(self.db.execute('SELECT score FROM leads').fetchone()[0], 100)

    def test_case_insensitive_email_dedup(self):
        ingest(self.db, 'a', LEAD)
        self.assertEqual(ingest(self.db, 'b', dict(LEAD, email=' BUYER@example.com '))['status'], 'duplicate_email')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM leads').fetchone()[0], 1)

    def test_budget_boolean_is_rejected(self):
        with self.assertRaises(ValueError):
            validate(dict(LEAD, budget_usd=True))

    def test_invalid_email(self):
        with self.assertRaises(ValueError):
            validate(dict(LEAD, email='invalid'))

    def test_unknown_fields_rejected(self):
        with self.assertRaises(ValueError):
            validate(dict(LEAD, secret='do not store'))

    def test_policy_change_conflicts(self):
        ingest(self.db, 'a', LEAD)
        with self.assertRaises(ValueError):
            ingest(self.db, 'a', LEAD, 1000)

    def test_atomic_rollback(self):
        self.db.execute("CREATE TRIGGER fail_outbox BEFORE INSERT ON outbox BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            ingest(self.db, 'a', LEAD)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM leads').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 0)

    def test_rule_words_are_whole_words(self):
        ingest(self.db, 'a', dict(LEAD, request='rapid delivery', budget_usd=10))
        self.assertEqual(self.db.execute('SELECT score FROM leads').fetchone()[0], 0)

    def test_outbox_stays_pending(self):
        ingest(self.db, 'a', LEAD)
        self.assertEqual(self.db.execute('SELECT status FROM outbox').fetchone()[0], 'pending_review')

    def test_simultaneous_duplicate_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'test.sqlite3')
            connect(path).close()
            barrier = threading.Barrier(2)
            results, errors = [], []
            def worker():
                db = connect(path)
                try:
                    barrier.wait(timeout=5)
                    results.append(ingest(db, 'a', LEAD)['status'])
                except Exception as exc:
                    errors.append(exc)
                finally:
                    db.close()
            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(timeout=10)
            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertFalse(errors)
            self.assertCountEqual(results, ['created', 'replayed'])


if __name__ == '__main__':
    unittest.main()
