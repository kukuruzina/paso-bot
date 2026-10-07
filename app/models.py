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
    tg_user_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False
    )
    tg_username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    language_code: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )
    blocked_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )

    # ⭐ Рейтинг
    rating_avg: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0
    )

    rating_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )

    deals_as_customer: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    deals_as_carrier: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    # 👑 PREMIUM перевозчик
    is_premium_carrier: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )

    max_item_value_eur: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    # 📊 Статистика
    valuable_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )

    cash_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )

    docs_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )

    source: Mapped[str | None] = mapped_column(
        nullable=True
    )

    # 🔥 PAYWALL
    contacts_left: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )

    # 🚀 REFERRAL SYSTEM
    invited_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    invites_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )

    # Сколько контактов уже выдали
    invites_rewarded_contacts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )

    # Бонусы подписки
    invites_rewarded_sub_10: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )

    invites_rewarded_sub_20: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )

    # Связь с пригласившим
    inviter: Mapped["User"] = relationship(
        remote_side=[id],
        uselist=False
    )


# =========================================================
# SUBSCRIPTIONS
# =========================================================

class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False
    )

    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    user: Mapped[User] = relationship()


# =========================================================
# PAYMENTS
# =========================================================

class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    provider: Mapped[str] = mapped_column(
        String(32),
        nullable=False
    )

    amount: Mapped[int] = mapped_column(
        nullable=False
    )

    currency: Mapped[str] = mapped_column(
        String(8),
        default="RUB"
    )

    status: Mapped[str] = mapped_column(
        String(16),
        default="pending"
    )

    external_id: Mapped[str | None] = mapped_column(
        String(128)
    )

    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow
    )

    user: Mapped[User] = relationship()


# =========================================================
# PARCEL REQUESTS
# =========================================================

class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    from_country: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    from_city: Mapped[str | None] = mapped_column(
        String(64)
    )

    to_country: Mapped[str] = mapped_column(
        String(64),
        default="Russia",
        nullable=False
    )

    to_city: Mapped[str | None] = mapped_column(
        String(64)
    )

    item_description: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    category: Mapped[str] = mapped_column(
        String(24),
        nullable=False
    )

    weight_band: Mapped[str] = mapped_column(
        String(12),
        nullable=False
    )

    carry_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False
    )

    transport_type: Mapped[str] = mapped_column(
        String(16),
        default="any"
    )

    delivery_date_from: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    delivery_date_to: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    reward_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False
    )

    reward_amount: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True
    )

    reward_currency: Mapped[str | None] = mapped_column(
        String(8),
        nullable=True
    )

    transit_allowed: Mapped[bool] = mapped_column(
        Boolean,
        default=True
    )

    status: Mapped[str] = mapped_column(
        String(16),
        default="active",
        nullable=False
    )

    requires_premium: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    user: Mapped[User] = relationship()


# =========================================================
# PARCEL OFFERS
# =========================================================

class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    from_country: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    from_city: Mapped[str | None] = mapped_column(
        String(64)
    )

    to_country: Mapped[str] = mapped_column(
        String(64),
        default="Russia",
        nullable=False
    )

    to_city: Mapped[str | None] = mapped_column(
        String(64)
    )

    trip_date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    return_trip_date: Mapped[date | None] = mapped_column(
        nullable=True
    )

    transit_country: Mapped[str | None] = mapped_column(
        String(64)
    )

    transit_city: Mapped[str | None] = mapped_column(
        String(64)
    )

    capacity_band: Mapped[str] = mapped_column(
        String(12),
        nullable=False
    )

    baggage_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False
    )

    transport_type: Mapped[str] = mapped_column(
        String(16),
        default="any"
    )

    price_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False
    )

    price_amount: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True
    )

    price_currency: Mapped[str | None] = mapped_column(
        String(8),
        nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(16),
        default="active",
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    user: Mapped[User] = relationship()


# =========================================================
# PARCEL MATCHES
# =========================================================

class Match(Base):
    __tablename__ = "matches"

    __table_args__ = (
        UniqueConstraint(
            "request_id",
            "offer_id",
            name="uq_request_offer"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    request_id: Mapped[int] = mapped_column(
        ForeignKey("requests.id", ondelete="CASCADE")
    )

    offer_id: Mapped[int] = mapped_column(
        ForeignKey("offers.id", ondelete="CASCADE")
    )

    score: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    level: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(16),
        default="proposed",
        nullable=False
    )

    # Результат сделки от заказчика
    requester_result: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True
    )

    # Результат сделки от перевозчика
    carrier_result: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True
    )

    notified: Mapped[bool] = mapped_column(
        default=False
    )

    notified_requester: Mapped[bool] = mapped_column(
        default=False
    )

    notified_carrier: Mapped[bool] = mapped_column(
        default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    request: Mapped[Request] = relationship()
    offer: Mapped[Offer] = relationship()


# =========================================================
# MATCH CONTACT OPENS — PARCELS
# =========================================================

class MatchContactOpen(Base):
    __tablename__ = "match_contact_opens"

    __table_args__ = (
        UniqueConstraint(
            "match_id",
            "user_id",
            name="uq_match_contact_open",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )



# =========================================================
# TRIP REQUESTS
# =========================================================

class TripRequest(Base):
    __tablename__ = "trip_requests"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    # Маршрут
    from_city: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    to_city: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    # Конкретная дата или диапазон дат
    #
    # Конкретная дата:
    # date_from = 20.09
    # date_to   = 20.09
    #
    # Диапазон:
    # date_from = 20.09
    # date_to   = 25.09
    date_from: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    date_to: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    # Количество пассажиров
    passengers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1
    )

    # Дополнительная информация
    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # active / completed / cancelled
    status: Mapped[str] = mapped_column(
        String(16),
        default="active",
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    user: Mapped[User] = relationship()


# =========================================================
# TRIP OFFERS
# =========================================================

class TripOffer(Base):
    __tablename__ = "trip_offers"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    # Маршрут
    from_city: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    to_city: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    # У водителя пока всегда конкретная дата
    trip_date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    # Время отправления — пока необязательное
    departure_time: Mapped[str | None] = mapped_column(
        String(8),
        nullable=True
    )

    # Свободные места
    seats: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1
    )

    # Условия оплаты:
    # free / split / fixed / negotiable
    price_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="negotiable"
    )

    price_amount: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True
    )

    price_currency: Mapped[str | None] = mapped_column(
        String(8),
        nullable=True
    )

    # Дополнительная информация
    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # active / completed / cancelled
    status: Mapped[str] = mapped_column(
        String(16),
        default="active",
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    user: Mapped[User] = relationship()


# =========================================================
# TRIP MATCHES
# =========================================================

class TripMatch(Base):
    __tablename__ = "trip_matches"

    __table_args__ = (
        UniqueConstraint(
            "request_id",
            "offer_id",
            name="uq_trip_request_offer"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    request_id: Mapped[int] = mapped_column(
        ForeignKey("trip_requests.id", ondelete="CASCADE")
    )

    offer_id: Mapped[int] = mapped_column(
        ForeignKey("trip_offers.id", ondelete="CASCADE")
    )

    # Общий score matching
    score: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    # ideal / good
    level: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True
    )

    # proposed / accepted / rejected / completed
    status: Mapped[str] = mapped_column(
        String(16),
        default="proposed",
        nullable=False
    )

    # Контакты были открыты
    notified_requester: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )

    notified_driver: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    request: Mapped[TripRequest] = relationship()
    offer: Mapped[TripOffer] = relationship()
    

# =========================================================
# MATCH CHAT — PARCELS
# =========================================================

class MatchChat(Base):
    __tablename__ = "match_chats"

    id: Mapped[int] = mapped_column(primary_key=True)

    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"),
        unique=True,
    )

    tg_chat_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


# =========================================================
# REVIEWS — PARCELS
# =========================================================

class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)

    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE")
    )

    reviewer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    reviewed_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    rating: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    value_band_eur: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    had_cash: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True
    )

    had_docs: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

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

