from __future__ import annotations

from datetime import date, datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Request, Offer, Match, User
from app.enums import CarryType, RowStatus
from app.utils import norm


WEIGHT_RANK = {
    "lt1": 1,
    "1_3": 2,
    "3_5": 3,
    "gt5": 4,
}


def weight_covers(offer_band: str, req_band: str) -> bool:
    return WEIGHT_RANK.get(offer_band, 0) >= WEIGHT_RANK.get(req_band, 0)


def baggage_compatible(req_carry: str, off_baggage: str) -> bool:
    if req_carry == CarryType.any:
        return True
    if req_carry == CarryType.hand_only:
        return off_baggage in (CarryType.hand_only, CarryType.any)
    if req_carry == CarryType.luggage_ok:
        return off_baggage in (CarryType.luggage_ok, CarryType.any)
    return True


def city_match(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return norm(a) == norm(b)


def calc_score(req: Request, off: Offer, offer_user: User | None) -> int:
    score = 50  # базовый за совпадение маршрута

    if req.delivery_date_to:
        delta = (req.delivery_date_to - off.trip_date).days
        if delta >= 0:
            if delta == 0:
                score += 25
            elif delta <= 3:
                score += 15
            elif delta <= 7:
                score += 10

    if weight_covers(off.capacity_band, req.weight_band):
        score += 10

    if offer_user and offer_user.rating_count:
        score += int(offer_user.rating_avg * 2)

    if offer_user and offer_user.is_premium_carrier:
        score += 15

    return score


# =========================================================
# ✈️ OFFER → REQUESTS
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

        print(
            "🔍 CHECK:",
            req.id,
            req.from_city,
            "→",
            req.to_city,
            "|",
            off.from_city,
            "→",
            off.to_city,
        )

        # маршрут
        if not (city_match(req.from_city, off.from_city) and city_match(req.to_city, off.to_city)):
            print("❌ skip: city mismatch")
            continue

        # даты
        if req.delivery_date_from and off.trip_date < req.delivery_date_from:
            print("❌ skip: too early")
            continue

        if req.delivery_date_to and off.trip_date > req.delivery_date_to:
            print("❌ skip: too late")
            continue

        score = calc_score(req, off, offer_user)
        candidates.append((req, score))

        print("✅ MATCH CANDIDATE:", req.id, "score=", score)

    print("CANDIDATES:", len(candidates))

    if top_n and top_n > 0:
        candidates = sorted(candidates, key=lambda x: x[1], reverse=True)[:top_n]

    created = []

    for req, score in candidates:

        print("👉 TRY CREATE:", req.id)

        existing = await session.execute(
            select(Match).where(
                Match.request_id == req.id,
                Match.offer_id == off.id,
            )
        )

        if existing.scalar_one_or_none():
            print("⚠️ already exists:", req.id)
            continue

        m = Match(
            request_id=req.id,
            offer_id=off.id,
            score=score,
            status="proposed",  # 🔥 ФИКС
        )

        session.add(m)

        try:
            await session.flush()
            created.append(m)
            print("🔥 CREATED MATCH:", req.id)

        except Exception as e:
            print("❌ ERROR:", e)
            await session.rollback()
            continue

    await session.commit()
    print("MATCHING OFFER DONE:", len(created))

    return created

