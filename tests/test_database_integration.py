"""Opt-in tests against a disposable PostgreSQL database only."""
import asyncio
import os
import unittest
import uuid
from datetime import UTC, datetime, timedelta

from app.database import Database, User, MinutePackage


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'requires a disposable PostgreSQL database')
class DatabaseIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database(os.environ['TEST_DATABASE_URL'])
        await self.db.initialize()
        self.user_id = int(uuid.uuid4().hex[:12], 16)
        async with self.db.sessions.begin() as session:
            session.add(User(telegram_id=self.user_id, wallet_balance_toman=500000, is_allowed=True, is_bot=False))

    async def asyncTearDown(self):
        await self.db.close()

    async def test_package_purchase_spend_and_idempotent_refund(self):
        self.assertEqual(await self.db.purchase_minutes(self.user_id, 'subtitle', 30, 50000, 30), 'purchased')
        self.assertEqual(await self.db.get_wallet_balance(self.user_id), 450000)
        package = (await self.db.available_minutes(self.user_id))[0]
        args = dict(user_id=self.user_id, chat_id=self.user_id, url='https://youtu.be/example',
                    selected_height=None, mode='subtitle', api_provider='openai', billable_minutes=20, package_id=package['id'])
        results = await asyncio.gather(*(self.db.create_package_job(uuid.uuid4().hex, **args) for _ in range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual((await self.db.available_minutes(self.user_id))[0]['minutes'], 10)
        from sqlalchemy import select
        from app.database import JobRecord
        async with self.db.sessions() as session:
            job = await session.scalar(select(JobRecord).where(JobRecord.telegram_user_id == self.user_id))
            job_id = job.id
        results = await asyncio.gather(self.db.refund_job_wallet(job_id), self.db.refund_job_wallet(job_id))
        self.assertEqual(sum(bool(r and r['refunded']) for r in results), 1)
        self.assertEqual((await self.db.available_minutes(self.user_id))[0]['minutes'], 30)

    async def test_content_order_refunds_once(self):
        job_id = uuid.uuid4().hex
        await self.db.create_wallet_job(job_id, self.user_id, self.user_id, 'https://youtu.be/test', None, 'subtitle', 'openai', 1, 10000)
        await self.db.update_job(job_id, 'completed', subtitle='1\n00:00:00,000 --> 00:00:01,000\nمتن\n')
        order_id = uuid.uuid4().hex
        self.assertEqual(await self.db.create_content_order(order_id, self.user_id, job_id, self.user_id, 'summary', 5000), 'created')
        outcomes = await asyncio.gather(self.db.refund_content_order(order_id), self.db.refund_content_order(order_id))
        self.assertEqual(sum(outcomes), 1)
        self.assertEqual(await self.db.get_wallet_balance(self.user_id), 490000)

    async def test_team_invite_is_single_use(self):
        team_id = await self.db.create_team(self.user_id, 'Test')
        self.assertIsNotNone(team_id)
        invite = await self.db.create_team_invite(self.user_id)
        member = self.user_id + 1
        async with self.db.sessions.begin() as session:
            session.add(User(telegram_id=member, wallet_balance_toman=0, is_allowed=True, is_bot=False))
        self.assertEqual(await self.db.join_team(member, invite), 'joined')
        self.assertEqual(await self.db.join_team(member, invite), 'invalid')
        self.assertEqual((await self.db.team_info(member))['id'], team_id)

    async def test_access_control_and_content_completion(self):
        job_id = uuid.uuid4().hex
        await self.db.create_wallet_job(job_id, self.user_id, self.user_id, 'https://youtu.be/test', None, 'subtitle', 'openai', 1, 10000)
        await self.db.update_job(job_id, 'completed', subtitle='1\n00:00:00,000 --> 00:00:01,000\nمتن\n')
        self.assertIsNone(await self.db.owned_subtitle(job_id, self.user_id + 1))
        self.assertFalse(await self.db.replace_subtitle(job_id, self.user_id + 1, 'old', 'new'))
        order_id = uuid.uuid4().hex
        self.assertEqual(await self.db.create_content_order(order_id, self.user_id, job_id, self.user_id, 'social', 5000), 'created')
        self.assertTrue(await self.db.finish_content_order(order_id, 'content'))
        self.assertFalse(await self.db.refund_content_order(order_id))
        self.assertEqual((await self.db.owned_content_result(self.user_id, order_id))['text'], 'content')
        self.assertIsNone(await self.db.owned_content_result(self.user_id + 1, order_id))
        self.assertEqual(await self.db.get_wallet_balance(self.user_id), 485000)

    async def test_refund_after_package_expiry_extends_one_day(self):
        await self.db.purchase_minutes(self.user_id, 'dub', 30, 10000, 1)
        package = (await self.db.available_minutes(self.user_id))[0]
        job_id = uuid.uuid4().hex
        self.assertIsNotNone(await self.db.create_package_job(job_id, self.user_id, self.user_id,
            'https://youtu.be/test', None, 'dub', 'openai', 10, package['id']))
        async with self.db.sessions.begin() as session:
            row = await session.get(MinutePackage, package['id'])
            row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        self.assertTrue((await self.db.refund_job_wallet(job_id))['refunded'])
        available = await self.db.available_minutes(self.user_id)
        self.assertEqual(available[0]['minutes'], 30)
        self.assertGreater(available[0]['expires_at'], datetime.now(UTC) + timedelta(hours=23))
