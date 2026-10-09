import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from app.services.payment_fulfillment import fulfill_payment


class PaymentFulfillmentValidationTests(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.session.begin = MagicMock()

    def run_payment(self, **overrides):
        args = {
            "provider": "yookassa",
            "external_id": "test-payment-123",
            "tg_user_id": 123456789,
            "plan_key": "single",
            "amount_minor": 20000,
            "currency": "RUB",
        }
        args.update(overrides)
        return asyncio.run(
            fulfill_payment(self.session, **args)
        )

    def assert_rejected_before_transaction(self, **overrides):
        with self.assertRaises(ValueError):
            self.run_payment(**overrides)
        self.session.begin.assert_not_called()

    def test_unknown_plan_rejected(self):
        self.assert_rejected_before_transaction(plan_key="unknown")

    def test_unknown_provider_rejected(self):
        self.assert_rejected_before_transaction(provider="unknown")

    def test_empty_external_id_rejected(self):
        self.assert_rejected_before_transaction(external_id="")

    def test_zero_amount_rejected(self):
        self.assert_rejected_before_transaction(amount_minor=0)

    def test_invalid_currency_rejected(self):
        self.assert_rejected_before_transaction(currency="")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class PaymentFulfillmentIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_payment_returns_false_without_fulfillment(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.services import payment_fulfillment as pf

        session = MagicMock()
        transaction = MagicMock()
        transaction.__aenter__ = AsyncMock(return_value=None)
        transaction.__aexit__ = AsyncMock(return_value=False)
        session.begin.return_value = transaction

        user = MagicMock()
        user.id = 42
        user.contacts_left = 0

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        duplicate_result = MagicMock()
        duplicate_result.scalar_one_or_none.return_value = None

        session.execute = AsyncMock(
            side_effect=[user_result, duplicate_result]
        )

        with patch.object(pf, "insert") as mock_insert:
            statement = MagicMock()
            statement.values.return_value = statement
            statement.on_conflict_do_nothing.return_value = statement
            statement.returning.return_value = statement
            mock_insert.return_value = statement

            result = await pf.fulfill_payment(
                session,
                provider="yookassa",
                external_id="duplicate-test-id",
                tg_user_id=123456789,
                plan_key="single",
                amount_minor=200,
                currency="RUB",
            )

        self.assertFalse(result)
        self.assertEqual(user.contacts_left, 0)
        session.add.assert_not_called()
        self.assertEqual(session.execute.await_count, 2)

    async def test_missing_user_is_rejected(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.services.payment_fulfillment import fulfill_payment

        session = MagicMock()
        transaction = MagicMock()
        transaction.__aenter__ = AsyncMock(return_value=None)
        transaction.__aexit__ = AsyncMock(return_value=False)
        session.begin.return_value = transaction

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        with self.assertRaisesRegex(ValueError, "User not found"):
            await fulfill_payment(
                session,
                provider="yookassa",
                external_id="missing-user-test",
                tg_user_id=123456789,
                plan_key="single",
                amount_minor=200,
                currency="RUB",
            )

        session.add.assert_not_called()
        self.assertEqual(session.execute.await_count, 1)


class PaymentFulfillmentSuccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_payment_adds_five_contacts_without_subscription(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.services import payment_fulfillment as pf

        session = MagicMock()
        transaction = MagicMock()
        transaction.__aenter__ = AsyncMock(return_value=None)
        transaction.__aexit__ = AsyncMock(return_value=False)
        session.begin.return_value = transaction

        user = MagicMock()
        user.id = 42
        user.contacts_left = 3

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        inserted_result = MagicMock()
        inserted_result.scalar_one_or_none.return_value = 1001

        session.execute = AsyncMock(
            side_effect=[user_result, inserted_result]
        )

        with patch.object(pf, "insert") as mock_insert:
            statement = MagicMock()
            statement.values.return_value = statement
            statement.on_conflict_do_nothing.return_value = statement
            statement.returning.return_value = statement
            mock_insert.return_value = statement

            result = await pf.fulfill_payment(
                session,
                provider="yookassa",
                external_id="single-success-test",
                tg_user_id=123456789,
                plan_key="single",
                amount_minor=200,
                currency="RUB",
            )

        self.assertTrue(result)
        self.assertEqual(user.contacts_left, 8)
        session.add.assert_not_called()
        self.assertEqual(session.execute.await_count, 2)


class PaymentFulfillmentSubscriptionTests(unittest.IsolatedAsyncioTestCase):
    async def _run_subscription_test(self, existing_expires_at=None):
        from datetime import datetime, timedelta
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.services import payment_fulfillment as pf

        session = MagicMock()
        transaction = MagicMock()
        transaction.__aenter__ = AsyncMock(return_value=None)
        transaction.__aexit__ = AsyncMock(return_value=False)
        session.begin.return_value = transaction

        user = MagicMock()
        user.id = 42
        user.contacts_left = 0

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        payment_result = MagicMock()
        payment_result.scalar_one_or_none.return_value = 1002

        subscription_result = MagicMock()
        if existing_expires_at is None:
            subscription_result.scalar_one_or_none.return_value = None
        else:
            existing = MagicMock()
            existing.expires_at = existing_expires_at
            subscription_result.scalar_one_or_none.return_value = existing

        session.execute = AsyncMock(
            side_effect=[user_result, payment_result, subscription_result]
        )

        with patch.object(pf, "insert") as mock_insert, \
             patch.object(pf, "datetime") as mock_datetime:
            now = datetime(2026, 1, 1, 12, 0, 0)
            mock_datetime.utcnow.return_value = now

            statement = MagicMock()
            statement.values.return_value = statement
            statement.on_conflict_do_nothing.return_value = statement
            statement.returning.return_value = statement
            mock_insert.return_value = statement

            result = await pf.fulfill_payment(
                session,
                provider="yookassa",
                external_id="subscription-success-test",
                tg_user_id=123456789,
                plan_key="standard",
                amount_minor=55500,
                currency="RUB",
            )

        self.assertTrue(result)
        session.add.assert_called_once()
        created_subscription = session.add.call_args.args[0]
        self.assertEqual(created_subscription.user_id, 42)
        self.assertEqual(created_subscription.status, "active")
        self.assertEqual(created_subscription.source, "yookassa")
        self.assertEqual(created_subscription.started_at, now)

        expected_expiry = (
            existing_expires_at + timedelta(days=14)
            if existing_expires_at is not None
            else now + timedelta(days=14)
        )
        self.assertEqual(created_subscription.expires_at, expected_expiry)

    async def test_new_subscription_gets_fourteen_days(self):
        await self._run_subscription_test()

    async def test_active_subscription_is_extended(self):
        from datetime import datetime, timedelta
        now = datetime(2026, 1, 1, 12, 0, 0)
        await self._run_subscription_test(
            existing_expires_at=now + timedelta(days=5)
        )
