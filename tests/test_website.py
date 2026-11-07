import os
import unittest
from unittest.mock import patch
from vivi.site.webconfig import dashboard_endpoint

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

class ServerAvatarTests(unittest.TestCase):
    def test_discord_icons_use_cdn_and_support_animated_hashes(self):
        from vivi.site.website import server_avatar
        self.assertIn('https://cdn.discordapp.com/icons/123/'+'a'*32+'.png?size=128',server_avatar(123,'Velvet Ruins','a'*32))
        self.assertIn('.gif?size=128',server_avatar(123,'Velvet Ruins','a_'+'a'*32))
    def test_missing_or_invalid_icon_uses_initials_and_never_arbitrary_urls(self):
        from vivi.site.website import server_avatar
        for icon in [None,'','https://evil.example/icon.png','../icon','" onerror="alert(1)']:
            markup=server_avatar(123,'Velvet Ruins',icon);self.assertNotIn('<img',markup);self.assertIn('VR',markup)
    def test_server_name_is_escaped_in_image_and_fallback(self):
        from vivi.site.website import server_avatar
        markup=server_avatar(123,'<script> server','a'*32);self.assertNotIn('<script>',markup);self.assertIn('&lt;script&gt;',markup)
