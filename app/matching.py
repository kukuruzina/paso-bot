from __future__ import annotations

from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Request, Offer, Match, User
from app.enums import RowStatus
from app.utils import norm
from app.geo import city_in_country


# =====================================================
# WEIGHT
# =====================================================

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

    return WEIGHT_RANK.get(
        offer_band,
        0
    ) >= WEIGHT_RANK.get(
        req_band,
        0
    )


# =====================================================
# CARRY
# =====================================================

def baggage_compatible(req_carry, off_baggage) -> bool:

    req = normalize_enum(req_carry)
    off = normalize_enum(off_baggage)

    # любой вариант
    if req == "any":
        return True

    # ручная кладь
    if req == "hand":
        return True

    # нужен багаж
    if req == "luggage":
        return off == "luggage"

    return False


# =====================================================
# TRANSPORT
# =====================================================

def transport_compatible(req_transport, off_transport) -> bool:

    req = normalize_enum(req_transport)
    off = normalize_enum(off_transport)

    if req == "any" or off == "any":
        return True

    return req == off


# =====================================================
# CITY
# =====================================================

def city_match(a: str | None, b: str | None) -> bool:

    if not a or not b:
        return False

    return norm(a) == norm(b)


# =====================================================
# SCORE
# =====================================================

def calc_score(
    req: Request,
    off: Offer,
    offer_user: User | None
) -> int:

    score = 50

    # даты
    if req.delivery_date_to:

        delta = (
            req.delivery_date_to
            - off.trip_date
        ).days

        if delta >= 0:

            if delta == 0:
                score += 25

            elif delta <= 3:
                score += 15

            elif delta <= 7:
                score += 10

    # вес
    if weight_covers(
        off.capacity_band,
        req.weight_band
    ):
        score += 10

    # transport bonus
    off_transport = normalize_enum(
        getattr(off, "transport_type", "any")
    )

    if off_transport == "any":
        score += 1
    else:
        score += 3

    # рейтинг
    if (
        offer_user
        and offer_user.rating_count
    ):
        score += int(
            offer_user.rating_avg * 2
        )

    # premium
    if (
        offer_user
        and getattr(
            offer_user,
            "is_premium_carrier",
            False
        )
    ):
        score += 15

    return score


# =====================================================
# SAFE CREATE MATCH
# =====================================================

async def create_match_if_not_exists(
    session,
    req: Request,
    off: Offer,
    score: int,
    match_level: str,
):

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
        level=match_level,
        status="proposed",

        notified=False,
        notified_requester=False,
        notified_carrier=False,
    )

    session.add(m)

    try:

        await session.flush()
        return m

    except IntegrityError:

        return None


# =====================================================
# OFFER → REQUESTS
# =====================================================

async def find_matches_for_offer(
    session: AsyncSession,
    offer_id: int,
    window_days: int,
    top_n: int,
):

    print("🔥 MATCHING OFFER STARTED", offer_id)

    off = await session.get(
        Offer,
        offer_id
    )

    if not off:
        print("❌ Offer not found")
        return []

    offer_user = await session.get(
        User,
        off.user_id
    )

    q = select(Request).where(
        Request.status == RowStatus.active
    )

    requests = (
        await session.execute(q)
    ).scalars().all()

    candidates = []

    for req in requests:

        # ❌ self-match
        if req.user_id == off.user_id:
            continue

        req_from = norm(req.from_city)
        off_from = norm(off.from_city)

        req_to = norm(req.to_city)
        off_to = norm(off.to_city)

        from_ok = (
            city_match(req_from, off_from)
            or city_in_country(off_from, req_from)
            or city_in_country(req_from, off_from)
        )

        to_ok = (
            city_match(req_to, off_to)
            or city_in_country(off_to, req_to)
            or city_in_country(req_to, off_to)
        )

        if not from_ok or not to_ok:
            continue

        match_date = off.trip_date

        # даты
        if (
            req.delivery_date_from
            and match_date < req.delivery_date_from
        ):
            continue

        if (
            req.delivery_date_to
            and match_date > req.delivery_date_to + timedelta(days=5)
        ):
            continue

        # carry
        if not baggage_compatible(
            req.carry_type,
            off.baggage_type
        ):
            continue

        # transport
        transport_ok = transport_compatible(
            req.transport_type,
            off.transport_type
        )

        # level
        delta_days = abs(
            (
                match_date
                - req.delivery_date_to
            ).days
        )

        if delta_days <= 3 and transport_ok:
            match_level = "best"
        else:
            match_level = "possible"

        score = calc_score(
            req,
            off,
            offer_user
        )

        candidates.append(
            (
                req,
                score,
                match_level
            )
        )

    candidates.sort(
        key=lambda x: x[1],
        reverse=True
    )

    if top_n:
        candidates = candidates[:top_n]

    created = []

    for req, score, match_level in candidates:

        m = await create_match_if_not_exists(
            session,
            req,
            off,
            score,
            match_level
        )

        if m:
            created.append(m)

    await session.commit()

    print(
        "MATCHING OFFER DONE:",
        len(created)
    )

    return created


# =====================================================
# REQUEST → OFFERS
# =====================================================

async def find_matches_for_request(
    bot,
    session: AsyncSession,
    request_id: int,
    window_days: int,
    top_n: int,
):

    print(
        "🔥 MATCHING REQUEST STARTED",
        request_id
    )

    req = await session.get(
        Request,
        request_id
    )

    if not req:
        print("❌ Request not found")
        return []

    q = select(Offer).where(
        Offer.status == RowStatus.active
    )

    offers = (
        await session.execute(q)
    ).scalars().all()

    candidates = []

    for off in offers:

        # ❌ self-match
        if req.user_id == off.user_id:
            continue

        req_from = norm(req.from_city)
        off_from = norm(off.from_city)

        req_to = norm(req.to_city)
        off_to = norm(off.to_city)

        from_ok = (
            city_match(req_from, off_from)
            or city_in_country(off_from, req_from)
            or city_in_country(req_from, off_from)
        )

        to_ok = (
            city_match(req_to, off_to)

        or city_in_country(off_to, req_to)
            or city_in_country(req_to, off_to)
        )

        if not from_ok or not to_ok:
            continue

        # даты
        if (
            req.delivery_date_from
            and off.trip_date < req.delivery_date_from
        ):
            continue

        if (
            req.delivery_date_to
            and off.trip_date > req.delivery_date_to + timedelta(days=5)
        ):
            continue

        # carry
        if not baggage_compatible(
            req.carry_type,
            off.baggage_type
        ):
            continue

        # transport
        transport_ok = transport_compatible(
            req.transport_type,
            off.transport_type
        )

        # level
        delta_days = abs(
            (
                off.trip_date
                - req.delivery_date_to
            ).days
        )

        if delta_days <= 3 and transport_ok:
            match_level = "best"
        else:
            match_level = "possible"

        offer_user = await session.get(
            User,
            off.user_id
        )

        score = calc_score(
            req,
            off,
            offer_user
        )

        candidates.append(
            (
                off,
                score,
                match_level
            )
        )

    candidates.sort(
        key=lambda x: x[1],
        reverse=True
    )

    if top_n:
        candidates = candidates[:top_n]

    created = []

    for off, score, match_level in candidates:

        m = await create_match_if_not_exists(
            session,
            req,
            off,
            score,
            match_level
        )

        if m:
            created.append(m)

    await session.commit()

    print(
        "MATCHING REQUEST DONE:",
        len(created)
    )

    return created



