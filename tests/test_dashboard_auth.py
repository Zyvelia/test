import asyncio
import time
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock,AsyncMock
import aiohttp
from aiohttp import web
from vivi.site.dashboard_auth import DashboardAuth

class DashboardAuthTests(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.auth=DashboardAuth();self.response=NS(status=200,headers={},json=AsyncMock(return_value=[dict(id='1',permissions='8'),dict(id='2',permissions='0')]))
  self.context=AsyncMock();self.context.__aenter__.return_value=self.response
  self.client=NS(get=Mock(return_value=self.context));self.auth.service=NS(session=self.client)
  self.session=dict(token='private-token',expires=time.time()+3600,csrf='csrf',user_id=10)
 async def test_browsing_many_pages_uses_one_bounded_permission_check(self):
  for _ in range(20):self.assertEqual(set(await self.auth.api_guilds(self.session)),{'1'})
  self.assertEqual(self.client.get.call_count,1)
  self.session['_guild_cache']['at']-=31;await self.auth.api_guilds(self.session);self.assertEqual(self.client.get.call_count,2)
 async def test_writes_bypass_browse_cache_and_detect_permission_revocation(self):
  await self.auth.api_guilds(self.session);self.response.json.return_value=[]
  self.assertEqual(await self.auth.api_guilds(self.session,fresh=True),{});self.assertEqual(self.client.get.call_count,2)
 async def test_parallel_checks_are_coalesced(self):
  async def slow():await asyncio.sleep(.02);return [dict(id='1',permissions='8')]
  self.response.json.side_effect=slow
  results=await asyncio.gather(*(self.auth.api_guilds(self.session,fresh=True) for _ in range(15)))
  self.assertTrue(all('1' in row for row in results));self.assertEqual(self.client.get.call_count,1)
 async def test_rate_limit_preserves_login_and_honors_cooldown(self):
  self.response.status=429;self.response.headers={'Retry-After':'15'};expires=self.session['expires']
  with self.assertRaises(web.HTTPTooManyRequests) as error:await self.auth.api_guilds(self.session)
  self.assertIn('login is still active',error.exception.text);self.assertEqual(self.session['expires'],expires)
  with self.assertRaises(web.HTTPTooManyRequests):await self.auth.api_guilds(self.session,fresh=True)
  self.assertEqual(self.client.get.call_count,1)
  self.session['_guild_retry']=0;self.response.status=200;await self.auth.api_guilds(self.session);self.assertEqual(self.client.get.call_count,2)
 async def test_only_unauthorized_response_invalidates_login(self):
  for status,error in [(403,web.HTTPForbidden),(500,web.HTTPServiceUnavailable),(503,web.HTTPServiceUnavailable)]:
   self.response.status=status
   with self.assertRaises(error):await self.auth.api_guilds(self.session)
   self.assertGreater(self.session['expires'],time.time())
  self.response.status=401
  with self.assertRaises(web.HTTPUnauthorized):await self.auth.api_guilds(self.session)
  self.assertEqual(self.session['expires'],0)
 async def test_network_error_does_not_log_user_out(self):
  self.client.get.side_effect=aiohttp.ClientConnectionError('offline')
  with self.assertRaises(web.HTTPServiceUnavailable) as error:await self.auth.api_guilds(self.session)
  self.assertIn('still signed in',error.exception.text);self.assertGreater(self.session['expires'],time.time())

 async def test_staff_discovery_does_not_broaden_administrator_authorization_cache(self):
  rows=await self.auth.api_guilds(self.session,include_all=True);self.assertEqual(set(rows),{'1','2'})
  admin=await self.auth.api_guilds(self.session);self.assertEqual(set(admin),{'1'});self.assertEqual(self.client.get.call_count,1)
