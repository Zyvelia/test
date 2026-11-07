import os
import unittest
from unittest.mock import patch
from vivi.webconfig import dashboard_endpoint

class WebsiteOriginTests(unittest.TestCase):
    def test_local_and_https_origins_have_separate_listener_and_cookie_rules(self):
        with patch.dict(os.environ,{},clear=True):
            local=dashboard_endpoint('http://127.0.0.1:8765/callback')
            self.assertEqual(local['bind_host'],'127.0.0.1')
            self.assertFalse(local['secure_cookies'])
            public=dashboard_endpoint('https://vivi.example.com/callback')
            self.assertEqual((public['port'],public['public_port']),(8765,443))
            self.assertTrue(public['secure_cookies'])

    def test_unsafe_redirects_are_rejected(self):
        with patch.dict(os.environ,{},clear=True):
            for origin in ['http://example.com/callback','https://example.com/other',
                           'https://user:secret@example.com/callback','https://example.com/callback?next=evil',
                           'https://example.com/callback#fragment','https://bad..example/callback',
                           'https://bad.-example/callback','https://example.com:0/callback']:
                with self.subTest(origin=origin),self.assertRaises(ValueError):dashboard_endpoint(origin)

    def test_native_external_bind_and_http_port_mismatch_rejected(self):
        with patch.dict(os.environ,{'DASHBOARD_BIND_HOST':'0.0.0.0'},clear=True):
            with self.assertRaises(ValueError):dashboard_endpoint('https://vivi.example.com/callback')
            os.environ['VIVI_CONTAINER']='1'
            self.assertEqual(dashboard_endpoint('https://vivi.example.com/callback')['bind_host'],'0.0.0.0')
        with patch.dict(os.environ,{'DASHBOARD_LISTEN_PORT':'9876'},clear=True):
            with self.assertRaises(ValueError):dashboard_endpoint('http://127.0.0.1:8765/callback')
