import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    bot_username: str
    database_url: str
    admin_tg_ids: set[int]
    match_window_days: int
    top_matches: int
    deals_chat_id: int | None

    # ЮKassa
    yookassa_shop_id: str | None
    yookassa_secret_key: str | None

    # Stripe
    stripe_secret_key: str | None
    stripe_webhook_secret: str | None
    public_base_url: str  # лучше не None

    # Subscription
    sub_price_eur: int
    sub_price_rub: int
    sub_duration_days: int


def load_config() -> Config:
    admin_raw = (os.getenv("ADMIN_TG_IDS") or "").strip()
    admin_ids = (
        {int(x.strip()) for x in admin_raw.split(",") if x.strip().isdigit()}
        if admin_raw
        else set()
    )

    deals_raw = (os.getenv("DEALS_CHAT_ID") or "").strip()

    public_base_url = (os.getenv("PUBLIC_BASE_URL") or "http://127.0.0.1:8000").strip()

    return Config(
        bot_token=os.environ["BOT_TOKEN"],
        bot_username=(os.getenv("BOT_USERNAME") or "").strip(),
        database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./paso.db"),
        admin_tg_ids=admin_ids,
        match_window_days=int(os.getenv("MATCH_WINDOW_DAYS", "3")),
        top_matches=int(os.getenv("TOP_MATCHES", "3")),
        deals_chat_id=int(deals_raw) if deals_raw else None,

        # ✅ ЮKassa (важно: без запятых в конце!)
        yookassa_shop_id=(os.getenv("YOOKASSA_SHOP_ID") or "").strip() or None,
        yookassa_secret_key=(os.getenv("YOOKASSA_SECRET_KEY") or "").strip() or None,

        # Stripe
        stripe_secret_key=(os.getenv("STRIPE_SECRET_KEY") or "").strip() or None,
        stripe_webhook_secret=(os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip() or None,
        public_base_url=public_base_url,

        # Subscription
        sub_price_eur=int(os.getenv("SUB_PRICE_EUR", "5")),
        sub_price_rub=int(os.getenv("SUB_PRICE_RUB", "555")),
        sub_duration_days=int(os.getenv("SUB_DURATION_DAYS", "30")),
    )