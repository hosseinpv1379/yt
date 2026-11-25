import http.client
import json
import re
import threading
import unittest

from localweb.__main__ import make_server


class LocalWebHttpTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host = f'127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, headers=None, body=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        conn.request(method, path, body=body, headers=headers or {})
        res = conn.getresponse()
        result = res.status, res.read()
        conn.close()
        return result

    def test_origin_token_and_host_are_required_for_mutations(self):
        status, page = self.request('GET', '/')
        self.assertEqual(status, 200)
        token = re.search(rb'name="session-token" content="([^"]+)', page).group(1).decode()
        headers = {'Origin': f'http://{self.host}', 'X-Session-Token': token, 'Content-Type': 'application/json'}
        self.assertEqual(self.request('POST', '/api/cancel', headers, '{}')[0], 200)
        self.assertEqual(self.request('POST', '/api/cancel', {**headers, 'Origin': 'https://evil.test'}, '{}')[0], 403)
        self.assertEqual(self.request('POST', '/api/cancel', {**headers, 'X-Session-Token': 'wrong'}, '{}')[0], 403)
        self.assertEqual(self.request('GET', '/', {'Host': 'evil.test'})[0], 403)

    def test_requests_do_not_return_api_keys(self):
        status, body = self.request('GET', '/api/settings')
        self.assertEqual(status, 200)
        prefs = json.loads(body)['preferences']
        self.assertNotIn('openai_api_key', prefs)
        self.assertNotIn('openrouter_api_key', prefs)
