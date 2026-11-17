"""Regression tests for missing slots, DST and concurrent publication."""
import unittest
from datetime import datetime
from scan_backup import ROME, due_slots
from merge_scan_result import combine

class RecoveryTests(unittest.TestCase):
    def test_missing_morning_is_not_lost_after_afternoon(self):
        for month in (1, 7, 11):
            now = datetime(2026, month, 17, 16, 5, tzinfo=ROME)
            self.assertEqual(due_slots(now, {}), ['09:30', '15:30'])
            data = {'audit': {'date': now.date().isoformat(), 'runs': {'15:30': {'status': 'complete'}}}}
            self.assertEqual(due_slots(now, data), ['09:30'])
    def test_no_early_scan_and_retry_failed(self):
        now = datetime(2026, 11, 17, 9, 29, tzinfo=ROME)
        self.assertEqual(due_slots(now, {}), [])
        now = now.replace(minute=30)
        data = {'audit': {'date': '2026-11-17', 'runs': {'09:30': {'status': 'failed'}}}}
        self.assertEqual(due_slots(now, data), ['09:30'])
    def test_completed_recovery_is_idempotent(self):
        coverage = {str(i): {'indexPagesAccessible': 5} for i in range(20)}
        data = {'audit': {'date': '2026-11-17', 'runs': {'09:30': {'status': 'partial', 'regionCoverage': coverage}}}}
        self.assertEqual(due_slots(datetime(2026,11,17,10,tzinfo=ROME), data), [])
    def test_terminal_failure_replaces_running(self):
        base = {'jobs': [{'id': 'saved', 'url': 'https://test/saved', 'saved': True}], 'audit': {'date': '2026-11-17', 'runs': {'09:30': {'status': 'running'}}}}
        scan = {'jobs': [], 'audit': {'date': '2026-11-17', 'runs': {'09:30': {'status': 'failed'}}}}
        result = combine(base, scan)
        self.assertEqual(result['audit']['runs']['09:30']['status'], 'failed')
        self.assertTrue(result['jobs'][0]['saved'])
    def test_late_previous_day_cannot_replace_today(self):
        latest = {'jobs': [], 'audit': {'date': '2026-11-17', 'runs': {}}}
        old = {'jobs': [], 'audit': {'date': '2026-11-16', 'runs': {'15:30': {'status': 'complete'}}}}
        result = combine(latest, old)
        self.assertEqual(result['audit']['date'], '2026-11-17')
        self.assertEqual(result['auditHistory'][0]['date'], '2026-11-16')

if __name__ == '__main__': unittest.main()
