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


    def test_stripe_invalid_signature_returns_400(self):
        from unittest.mock import patch
        import stripe

        with (
            patch("app.stripe_server.STRIPE_WEBHOOK_SECRET", "whsec_test"),
            patch(
                "app.stripe_server.stripe.Webhook.construct_event",
                side_effect=stripe.SignatureVerificationError(
                    "invalid signature", "test-signature"
                ),
            ),
        ):
            response = self.client.post(
                "/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "invalid"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "Invalid Stripe webhook signature",
        )

    def test_stripe_unsupported_event_is_ignored(self):
        from unittest.mock import patch

        event = {
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": "pi_test_only"}},
        }
        with (
            patch("app.stripe_server.STRIPE_WEBHOOK_SECRET", "whsec_test"),
            patch(
                "app.stripe_server.stripe.Webhook.construct_event",
                return_value=event,
            ),
            patch("app.stripe_server.stripe.checkout.Session.retrieve") as retrieve,
        ):
            response = self.client.post(
                "/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "test-signature"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        retrieve.assert_not_called()

    def test_stripe_paid_checkout_uses_verified_price_and_amount(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_test_only"}},
        }
        checkout = {
            "id": "cs_test_only",
            "payment_status": "paid",
            "mode": "payment",
            "metadata": {"tg_user_id": "123456789", "plan": "single"},
            "line_items": {
                "data": [{"price": {"id": "price_test_single"}, "quantity": 1}]
            },
            "amount_total": 2000,
            "currency": "eur",
        }
        price = {
            "id": "price_test_single",
            "unit_amount": 2000,
            "currency": "eur",
            "active": True,
        }

        db_session = object()
        session_context = MagicMock()
        session_context.__aenter__ = AsyncMock(return_value=db_session)
        session_context.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.stripe_server.STRIPE_WEBHOOK_SECRET", "whsec_test"),
            patch("app.stripe_server.STRIPE_PRICES", {"single": "price_test_single"}),
            patch(
                "app.stripe_server.stripe.Webhook.construct_event",
                return_value=event,
            ),
            patch(
                "app.stripe_server.stripe.checkout.Session.retrieve",
                return_value=checkout,
            ) as retrieve_checkout,
            patch(
                "app.stripe_server.stripe.Price.retrieve",
                return_value=price,
            ) as retrieve_price,
            patch("app.stripe_server.get_session", return_value=session_context),
            patch(
                "app.services.payment_fulfillment.fulfill_payment",
                new_callable=AsyncMock,
                return_value=True,
            ) as fulfill_payment,
        ):
            response = self.client.post(
                "/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "test-signature"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        retrieve_checkout.assert_called_once_with(
            "cs_test_only",
            expand=["line_items.data.price"],
        )
        retrieve_price.assert_called_once_with("price_test_single")
        fulfill_payment.assert_awaited_once_with(
            db_session,
            provider="stripe",
            external_id="cs_test_only",
            tg_user_id=123456789,
            plan_key="single",
            amount_minor=2000,
            currency="EUR",
        )

    def test_stripe_checkout_amount_mismatch_does_not_fulfill(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_test_mismatch"}},
        }
        checkout = {
            "id": "cs_test_mismatch",
            "payment_status": "paid",
            "mode": "payment",
            "metadata": {"tg_user_id": "123456789", "plan": "single"},
            "line_items": {
                "data": [{"price": {"id": "price_test_single"}, "quantity": 1}]
            },
            "amount_total": 1,
            "currency": "eur",
        }
        price = {
            "id": "price_test_single",
            "unit_amount": 2000,
            "currency": "eur",
            "active": True,
        }

        with (
            patch("app.stripe_server.STRIPE_WEBHOOK_SECRET", "whsec_test"),
            patch("app.stripe_server.STRIPE_PRICES", {"single": "price_test_single"}),
            patch(
                "app.stripe_server.stripe.Webhook.construct_event",
                return_value=event,
            ),
            patch(
                "app.stripe_server.stripe.checkout.Session.retrieve",
                return_value=checkout,
            ),
            patch(
                "app.stripe_server.stripe.Price.retrieve",
                return_value=price,
            ),
            patch("app.stripe_server.get_session") as get_session,
            patch(
                "app.services.payment_fulfillment.fulfill_payment",
                new_callable=AsyncMock,
            ) as fulfill_payment,
        ):
            response = self.client.post(
                "/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "test-signature"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "Payment validation failed",
        )
        get_session.assert_not_called()
        fulfill_payment.assert_not_awaited()


if __name__ == "__main__":
    unittest.main(verbosity=2)
