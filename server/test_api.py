import os
import tempfile
import unittest
import uuid

_tmp = tempfile.TemporaryDirectory()
os.environ['DATABASE_PATH'] = os.path.join(_tmp.name, 'test.db')
from app import app


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.email = str(uuid.uuid4()) + '@example.com'
        self.token = self.client.post('/api/register', json={'email': self.email, 'password': 'correct-horse-42'}).json['token']
        self.auth = {'Authorization': 'Bearer '+self.token}

    def item(self, **kwargs):
        return dict({'id': str(uuid.uuid4()), 'op': str(uuid.uuid4()), 'rev': 0, 'kind': 'deadline', 'title': 'Assignment', 'due': '2026-12-20', 'category': 'Study', 'priority': 'High', 'completed': False, 'updated': '2026-10-07T12:00:00Z', 'deleted': False}, **kwargs)

    def sync(self, changes, auth=None):
        return self.client.post('/api/sync', headers=auth or self.auth, json={'changes': changes})

    def test_retries_are_idempotent(self):
        item = self.item()
        first = self.sync([item]).json
        second = self.sync([item]).json
        self.assertEqual(first, second)
        self.assertEqual(second['items'][0]['rev'], 1)

    def test_conflicting_offline_edits_are_copied(self):
        item = self.item()
        self.sync([item])
        a = {**item, 'op': str(uuid.uuid4()), 'rev': 1, 'title': 'Device A'}
        b = {**item, 'op': str(uuid.uuid4()), 'rev': 1, 'title': 'Device B'}
        self.sync([a])
        result = self.sync([b]).json
        self.assertEqual(result['conflicts'], 1)
        self.assertEqual({x['title'] for x in result['items']}, {'Device A','Device B (conflict copy)'})
        self.assertEqual(self.sync([b]).json, result)

    def test_stale_delete_keeps_newer_edit(self):
        item = self.item()
        self.sync([item])
        self.sync([{**item, 'rev': 1, 'op': str(uuid.uuid4()), 'title': 'New work'}])
        result = self.sync([{**item, 'rev': 1, 'op': str(uuid.uuid4()), 'deleted': True}]).json
        self.assertEqual(result['conflicts'], 1)
        self.assertFalse(result['items'][0]['deleted'])

    def test_normal_delete_syncs_tombstone(self):
        item = self.item()
        self.sync([item])
        result = self.sync([{**item, 'rev': 1, 'op': str(uuid.uuid4()), 'deleted': True}]).json
        self.assertTrue(result['items'][0]['deleted'])
        self.assertEqual(self.sync([]).json['items'], result['items'])

    def test_users_cannot_read_each_others_data(self):
        self.sync([self.item()])
        other = self.client.post('/api/register',json={'email': str(uuid.uuid4())+'@example.com','password': 'another-password'}).json
        self.assertEqual(self.sync([],{'Authorization': 'Bearer '+other['token']}).json['items'], [])
        self.assertEqual(self.client.post('/api/sync',json={'changes': []}).status_code,401)

    def test_entire_batch_validates_before_write(self):
        self.assertEqual(self.sync([self.item(),self.item(title='')]).status_code,400)
        self.assertEqual(self.sync([]).json['items'],[])

    def test_login_and_bad_password(self):
        self.assertEqual(self.client.post('/api/login',json={'email': self.email,'password':'wrong-password'}).status_code,401)
        self.assertIn('token',self.client.post('/api/login',json={'email': self.email,'password':'correct-horse-42'}).json)

    def test_notes_roundtrip(self):
        item=self.item(kind='note',content='A note\nWith a second line',pinned=True)
        result=self.sync([item]).json['items'][0]
        self.assertEqual(result['content'],item['content'])
        self.assertTrue(result['pinned'])


if __name__ == '__main__':
    unittest.main()
