from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import (
    BigInteger,
    String,
    DateTime,
    Date,
    Boolean,
    ForeignKey,
    Numeric,
    UniqueConstraint,
    Text,
    Integer,
    Float,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


# =========================================================
# USERS
# =========================================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    tg_username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    language_code: Mapped[str | None] = mapped_column(String(16))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    # ⭐ рейтинг
    rating_avg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 👑 PREMIUM перевозчик
    is_premium_carrier: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_item_value_eur: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 📊 статистика
    valuable_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cash_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    docs_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 🔥 PAYWALL
    contacts_left: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 🚀 REFERRAL SYSTEM
    invited_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    invites_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # сколько контактов уже выдали
    invites_rewarded_contacts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # бонусы подписки
    invites_rewarded_sub_10: Mapped[bool] = mapped_column(Boolean, default=False)
    invites_rewarded_sub_20: Mapped[bool] = mapped_column(Boolean, default=False)

    # связь (необязательно)
    inviter: Mapped["User"] = relationship(remote_side=[id], uselist=False)


# =========================================================
# SUBSCRIPTIONS
# =========================================================

class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    status: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship()


# =========================================================
# PAYMENTS
# =========================================================

class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[int] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")

    status: Mapped[str] = mapped_column(String(16), default="pending")

    external_id: Mapped[str | None] = mapped_column(String(128))

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    user: Mapped[User] = relationship()


# =========================================================
# REQUESTS
# =========================================================

class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    from_country: Mapped[str] = mapped_column(String(64), nullable=False)
    from_city: Mapped[str | None] = mapped_column(String(64))

    to_country: Mapped[str] = mapped_column(String(64), default="Russia", nullable=False)
    to_city: Mapped[str | None] = mapped_column(String(64))

    item_description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)

    weight_band: Mapped[str] = mapped_column(String(12), nullable=False)
    carry_type: Mapped[str] = mapped_column(String(16), nullable=False)

    delivery_date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_date_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    reward_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    reward_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    reward_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)

    transit_allowed: Mapped[bool] = mapped_column(Boolean, default=True)

    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)

    requires_premium: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship()


# =========================================================
# OFFERS
# =========================================================

class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    from_country: Mapped[str] = mapped_column(String(64), nullable=False)
    from_city: Mapped[str | None] = mapped_column(String(64))

    to_country: Mapped[str] = mapped_column(String(64), default="Russia", nullable=False)
    to_city: Mapped[str | None] = mapped_column(String(64))

    trip_date: Mapped[date] = mapped_column(Date, nullable=False)

    transit_country: Mapped[str | None] = mapped_column(String(64))
    transit_city: Mapped[str | None] = mapped_column(String(64))

    capacity_band: Mapped[str] = mapped_column(String(12), nullable=False)
    baggage_type: Mapped[str] = mapped_column(String(16), nullable=False)

    price_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    price_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship()


# =========================================================
# MATCHES
# =========================================================

class Match(Base):
    __tablename__ = "matches"

    __table_args__ = (
        UniqueConstraint("request_id", "offer_id", name="uq_request_offer"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id", ondelete="CASCADE"))
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id", ondelete="CASCADE"))

    score: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(16), default="proposed", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    request: Mapped[Request] = relationship()
    offer: Mapped[Offer] = relationship()


# =========================================================
# MATCH CHAT
# =========================================================

class MatchChat(Base):
    __tablename__ = "match_chats"

    id: Mapped[int] = mapped_column(primary_key=True)

    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"),
        unique=True,
    )

    tg_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# =========================================================
# REVIEWS
# =========================================================

class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)

    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))

    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    reviewed_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    value_band_eur: Mapped[int | None] = mapped_column(Integer, nullable=True)
    had_cash: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    had_docs: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


