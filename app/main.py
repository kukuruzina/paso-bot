import logging
import os
from datetime import datetime

import stripe
from fastapi import FastAPI

from app.db import get_session
from app.models import User, Subscription, Payment
from app.services.subscriptions import activate_subscription
from app.config import load_config

cfg = load_config()

# ======================
# CONFIG
# ======================

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")

stripe.api_key = STRIPE_SECRET_KEY

app = FastAPI()

logging.basicConfig(level=logging.INFO)


def _now():
    return datetime.utcnow()

