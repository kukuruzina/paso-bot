import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.stripe_server import app


class PaymentWebhookTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_yookassa_missing_payment_id_returns_400(self):
        response = self.client.post(
            "/yookassa/webhook",
            json={"event": "payment.succeeded", "object": {}},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Missing payment ID")

    def test_stripe_missing_signature_returns_400(self):
        with patch("app.stripe_server.STRIPE_WEBHOOK_SECRET", "test-secret"):
            response = self.client.post(
                "/stripe/webhook",
                content=b"{}",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "Missing Stripe signature",
        )

    def test_yookassa_unsupported_event_is_ignored(self):
        with patch(
            "app.stripe_server.get_session",
        ) as mock_get_session:
            response = self.client.post(
                "/yookassa/webhook",
                json={
                    "event": "payment.waiting_for_capture",
                    "object": {"id": "test-only-id"},
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        mock_get_session.assert_not_called()



    def test_yookassa_success_uses_verified_payment_data(self):
        from unittest.mock import AsyncMock, MagicMock

        verified = {
            "payment_id": "test-only-id",
            "tg_user_id": 123456789,
            "plan_key": "single",
            "amount_minor": 20000,
            "currency": "RUB",
        }

        db_session = object()
        session_context = MagicMock()
        session_context.__aenter__ = AsyncMock(return_value=db_session)
        session_context.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.stripe_server.get_session", return_value=session_context),
            patch(
                "app.services.yookassa_verification.verify_yookassa_payment",
                new_callable=AsyncMock,
                return_value=verified,
            ) as verify_payment,
            patch(
                "app.services.payment_fulfillment.fulfill_payment",
                new_callable=AsyncMock,
                return_value=True,
            ) as fulfill_payment,
        ):
            response = self.client.post(
                "/yookassa/webhook",
                json={
                    "event": "payment.succeeded",
                    "object": {"id": "test-only-id"},
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        verify_payment.assert_awaited_once_with("test-only-id")
        fulfill_payment.assert_awaited_once_with(
            db_session,
            provider="yookassa",
            external_id="test-only-id",
            tg_user_id=123456789,
            plan_key="single",
            amount_minor=20000,
            currency="RUB",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
