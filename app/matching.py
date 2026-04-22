from __future__ import annotations

from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Request, Offer, Match, User
from app.enums import CarryType, RowStatus
from app.utils import norm


# ================= WEIGHT =================

WEIGHT_RANK = {
    "lt1": 1,
    "w1_3": 2,
    "w3_5": 3,
    "gt5": 4,
}


def normalize_enum(val):
    if hasattr(val, "value"):
        return val.value
    return val


def weight_covers(offer_band, req_band) -> bool:
    offer_band = normalize_enum(offer_band)
    req_band = normalize_enum(req_band)

    return WEIGHT_RANK.get(offer_band, 0) >= WEIGHT_RANK.get(req_band, 0)


# ================= CARRY =================

def baggage_compatible(req_carry, off_baggage) -> bool:
    req = normalize_enum(req_carry)
    off = normalize_enum(off_baggage)

    # 👌 без разницы → подходит всё
    if req == "any":
        return True

    # 🧳 нужен багаж → только если он есть
    if req == "luggage":
        return off == "luggage"

    # 🎒 можно ручную → подходят оба
    if req == "hand":
        return off in ("hand", "luggage")

    return False

# ================= TRANSPORT =================

def transport_compatible(off_transport):
    return True  # пока не фильтруем


def transport_match(req_transport, off_transport):
    req_transport = normalize_enum(req_transport)
    off_transport = normalize_enum(off_transport)

    if req_transport == "any" or off_transport == "any":
        return True

    return req_transport == off_transport


# ================= CITY =================

def city_match(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return norm(a) == norm(b)


# ================= SCORE =================

def calc_score(req: Request, off: Offer, offer_user: User | None) -> int:
    score = 50

    # даты
    if req.delivery_date_to:
        delta = (req.delivery_date_to - off.trip_date).days
        if delta >= 0:
            if delta == 0:
                score += 25
            elif delta <= 3:
                score += 15
            elif delta <= 7:
                score += 10

    # вес
    if weight_covers(off.capacity_band, req.weight_band):
        score += 10

    # transport бонус
    off_transport = normalize_enum(getattr(off, "transport_type", "any"))

    if off_transport == "any":
        score += 1
    else:
        score += 3

    # рейтинг
    if offer_user and offer_user.rating_count:
        score += int(offer_user.rating_avg * 2)

    # премиум
    if offer_user and getattr(offer_user, "is_premium_carrier", False):
        score += 15

    return score


# =========================================================
# 🔧 ОБЩИЙ МЕТОД СОЗДАНИЯ MATCH
# =========================================================

async def create_match_if_not_exists(session, req: Request, off: Offer, score: int):
    existing = await session.execute(
        select(Match).where(
            Match.request_id == req.id,
            Match.offer_id == off.id,
        )
    )

    if existing.scalar_one_or_none():
        return None

    m = Match(
        request_id=req.id,
        offer_id=off.id,
        score=score,
        status="proposed",
    )

    session.add(m)
    return m


# =========================================================
# ✈️ OFFER → REQUESTS (ОСТАВИЛ КАК ЕСТЬ)
# =========================================================

async def find_matches_for_offer(
    session: AsyncSession,
    offer_id: int,
    window_days: int,
    top_n: int,
):
    print("🔥 MATCHING OFFER STARTED", offer_id)

    off = await session.get(Offer, offer_id)
    if not off:
        print("❌ Offer not found")
        return []

    offer_user = await session.get(User, off.user_id)

    q = select(Request).where(Request.status == RowStatus.active)
    requests = (await session.execute(q)).scalars().all()

    print("Found requests:", len(requests))

    candidates = []

    for req in requests:

        # маршрут
        if not (city_match(req.from_city, off.from_city) and city_match(req.to_city, off.to_city)):
            continue

        # даты
        if req.delivery_date_from and off.trip_date < req.delivery_date_from:
            continue

        if req.delivery_date_to and off.trip_date > req.delivery_date_to:
            continue

        # carry
        if not baggage_compatible(req.carry_type, off.baggage_type):
            continue

        # transport
        if not transport_compatible(off.transport_type):
            continue

        score = calc_score(req, off, offer_user)
        candidates.append((req, score))

    candidates.sort(key=lambda x: x[1], reverse=True)

    if top_n:
        candidates = candidates[:top_n]

    created = []

    for req, score in candidates:
        m = await create_match_if_not_exists(session, req, off, score)
        if m:
            created.append(m)

    await session.commit()

    print("MATCHING OFFER DONE:", len(created))
    return created


# =========================================================
# 📦 REQUEST → OFFERS
# =========================================================

async def find_matches_for_request(
    session: AsyncSession,
    request_id: int,
    window_days: int,
    top_n: int,
):

    print("🔥 MATCHING REQUEST STARTED", request_id)

    req = await session.get(Request, request_id)
    if not req:
        print("❌ Request not found")
        return []

    q = select(Offer).where(Offer.status == RowStatus.active)
    offers = (await session.execute(q)).scalars().all()

    print("Found offers:", len(offers))

    candidates = []

    for off in offers:

        print(
            "🔍 CHECK:",
            off.id,
            off.from_city,
            "→",
            off.to_city,
            "|",
            req.from_city,
            "→",
            req.to_city,
        )

        # маршрут
        if not (city_match(req.from_city, off.from_city) and city_match(req.to_city, off.to_city)):
            print("❌ skip: city mismatch")
            continue

        # даты (две стороны)
        if req.delivery_date_from and off.trip_date < req.delivery_date_from:
            print("❌ skip: too early")
            continue

        if req.delivery_date_to and off.trip_date > req.delivery_date_to:
            print("❌ skip: too late")
            continue

        # carry
        if not baggage_compatible(req.carry_type, off.baggage_type):
            print("❌ skip: carry mismatch")
            continue

        # transport (пока мягкий)
        if not transport_compatible(off.transport_type):
            print("❌ skip: transport mismatch")
            continue

        offer_user = await session.get(User, off.user_id)

        score = calc_score(req, off, offer_user)
        candidates.append((off, score))

        print("✅ MATCH CANDIDATE:", off.id, "score=", score)

    print("CANDIDATES:", len(candidates))

    # 🔥 сортировка
    candidates = sorted(candidates, key=lambda x: x[1], reverse=True)

    # 🔥 топ N
    if top_n and top_n > 0:
        candidates = candidates[:top_n]

    created = []

    for off, score in candidates:

        print("👉 TRY CREATE:", off.id)

        existing = await session.execute(
            select(Match).where(
                Match.request_id == req.id,
                Match.offer_id == off.id,
            )
        )

        existing_match = existing.scalar_one_or_none()

        if existing_match:
            print("⚠️ already exists:", off.id)
            created.append(existing_match)
            continue

        m = Match(
            request_id=req.id,
            offer_id=off.id,
            score=score,
            status="proposed",
        )

        session.add(m)

        try:
            await session.flush()
            created.append(m)
            print("🔥 CREATED MATCH:", off.id)

        except Exception as e:
            print("❌ ERROR:", e)
            await session.rollback()
            continue

    await session.commit()

    print("MATCHING REQUEST DONE:", len(created))

    return created



