from __future__ import annotations

from datetime import date, datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Request, Offer, Match, User
from app.enums import CarryType, MatchStatus, RowStatus


# ---------- WEIGHT ----------

WEIGHT_RANK = {
    "lt1": 1,
    "1_3": 2,
    "3_5": 3,
    "gt5": 4,
}


def weight_covers(offer_band: str, req_band: str) -> bool:
    return WEIGHT_RANK.get(offer_band, 0) >= WEIGHT_RANK.get(req_band, 0)


# ---------- COMPATIBILITY ----------

def baggage_compatible(req_carry: str, off_baggage: str) -> bool:
    if req_carry == CarryType.any:
        return True
    if req_carry == CarryType.hand_only:
        return off_baggage in (CarryType.hand_only, CarryType.any)
    if req_carry == CarryType.luggage_ok:
        return off_baggage in (CarryType.luggage_ok, CarryType.any)
    return False


def city_match(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return a.strip().lower() == b.strip().lower()


def route_type(req: Request, off: Offer) -> str | None:
    if city_match(req.from_city, off.from_city) and city_match(req.to_city, off.to_city):
        return "direct"
    if city_match(req.from_city, off.to_city) and city_match(req.to_city, off.from_city):
        return "reverse"
    return None


def transit_ok(req: Request, off: Offer) -> bool:
    if not getattr(req, "transit_allowed", True):
        return not bool(getattr(off, "transit_country", None))
    return True


# ---------- SCORE ----------

def calc_score(req: Request, off: Offer, rt: str, offer_user: User | None) -> int:
    score = 0

    # маршрут
    if rt == "direct":
        score += 30
    elif rt == "reverse":
        score += 10

    # дедлайн
    if req.delivery_date_to:
        delta = (req.delivery_date_to - off.trip_date).days
        if delta >= 0:
            if delta == 0:
                score += 25
            elif delta <= 2:
                score += 15
            elif delta <= 7:
                score += 10

    # вес
    if weight_covers(off.capacity_band, req.weight_band):
        score += 15

    # транзит
    if getattr(req, "transit_allowed", True) and bool(getattr(off, "transit_country", None)):
        score += 3

    # ⭐ рейтинг
    if offer_user and offer_user.rating_count:
        score += int(offer_user.rating_avg * 2)

    # 👑 premium
    if offer_user and offer_user.is_premium_carrier:
        score += 15

    # 🆕 свежесть заявки
    if req.created_at:
        freshness = (datetime.utcnow() - req.created_at).days
        if freshness <= 1:
            score += 3

    return score


# =========================================================
# 📦 REQUEST → OFFERS
# =========================================================

async def find_matches_for_request(
    session: AsyncSession,
    request_id: int,
    window_days: int,
    top_n: int,
) -> list[Match]:

    print("🔥 MATCHING REQUEST STARTED", request_id)

    req = await session.get(Request, request_id)
    if not req or req.status != RowStatus.active:
        print("❌ Request not active or not found")
        return []

    q = select(Offer).where(Offer.status == RowStatus.active)
    offers = (await session.execute(q)).scalars().all()

    print("Found offers:", len(offers))

    candidates: list[tuple[Offer, int]] = []

    for off in offers:

        offer_user = await session.get(User, off.user_id)

        # PREMIUM фильтр
        if getattr(req, "requires_premium", False):
            if not offer_user or not offer_user.is_premium_carrier:
                continue

        rt = route_type(req, off)
        if rt is None:
            continue

        if not transit_ok(req, off):
            continue

        if req.delivery_date_to and off.trip_date > req.delivery_date_to:
            continue

        if off.trip_date < date.today() - timedelta(days=window_days):
            continue

        if not baggage_compatible(req.carry_type, off.baggage_type):
            continue

        if not weight_covers(off.capacity_band, req.weight_band):
            continue

        score = calc_score(req, off, rt, offer_user)
        candidates.append((off, score))

        print("✅ Candidate offer:", off.id, "score=", score)

    candidates.sort(key=lambda x: x[1], reverse=True)
    candidates = candidates[:top_n]

    created_matches: list[Match] = []

    for off, score in candidates:
        m = Match(
            request_id=req.id,
            offer_id=off.id,
            score=score,
            status=MatchStatus.proposed,
        )
        session.add(m)
        try:
            await session.flush()
            created_matches.append(m)
        except Exception:
            await session.rollback()
            continue

    await session.commit()
    print("MATCHING REQUEST DONE:", len(created_matches))

    return created_matches


# =========================================================
# ✈️ OFFER → REQUESTS
# =========================================================

async def find_matches_for_offer(
    session: AsyncSession,
    offer_id: int,
    window_days: int,
    top_n: int,
) -> list[Match]:

    print("🔥 MATCHING OFFER STARTED", offer_id)

    off = await session.get(Offer, offer_id)
    if not off:  # ← важно (чтобы работало для draft)
        print("❌ Offer not found")
        return []

    offer_user = await session.get(User, off.user_id)

    q = select(Request).where(Request.status == RowStatus.active)
    requests = (await session.execute(q)).scalars().all()

    print("Found requests:", len(requests))

    candidates: list[tuple[Request, int]] = []

    for req in requests:

        # 🎯 категории (если есть multi-select)
        if hasattr(off, "categories") and off.categories:
            if req.category not in off.categories:
                continue

        rt = route_type(req, off)
        if rt is None:
            continue

        if not transit_ok(req, off):
            continue

        if req.delivery_date_to and off.trip_date > req.delivery_date_to:
            continue

        if off.trip_date < date.today() - timedelta(days=window_days):
            continue

        if not baggage_compatible(req.carry_type, off.baggage_type):
            continue

        if not weight_covers(off.capacity_band, req.weight_band):
            continue

        score = calc_score(req, off, rt, offer_user)
        candidates.append((req, score))

        print("✅ Candidate request:", req.id, "score=", score)

    candidates.sort(key=lambda x: x[1], reverse=True)
    candidates = candidates[:top_n]

    created_matches: list[Match] = []

    for req, score in candidates:
        m = Match(
            request_id=req.id,
            offer_id=off.id,
            score=score,
            status=MatchStatus.proposed,
        )
        session.add(m)
        try:
            await session.flush()
            created_matches.append(m)
        except Exception:
            await session.rollback()
            continue

    await session.commit()
    print("MATCHING OFFER DONE:", len(created_matches))

    return created_matches

