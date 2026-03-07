from __future__ import annotations

from datetime import datetime
import uuid

import stripe
from yookassa import Configuration, Payment
from fastapi import FastAPI, Request, HTTPException
from sqlalchemy import select

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .config import load_config
from .db import init_global_db, get_session
from .models import User
from .services.subscriptions import activate_subscription

cfg = load_config()

init_global_db(cfg.database_url)

stripe.api_key = cfg.stripe_secret_key

# ✅ ОДИН app
app = FastAPI()

# ✅ один root
@app.get("/")
def root():
    return {"service": "PASO API", "status": "running"}

# ✅ один health
@app.get("/health")
async def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat()}

# yookassa config
if cfg.yookassa_shop_id and cfg.yookassa_secret_key:
    Configuration.account_id = cfg.yookassa_shop_id
    Configuration.secret_key = cfg.yookassa_secret_key