from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TripRequest, TripOffer, TripMatch, User


def _date_distance(trip_date: date, date_from: date, date_to: date) -> int:
    """Расстояние от даты поездки до диапазона запроса."""
    if date_from <= trip_date <= date_to:
        return 0

    if trip_date < date_from:
        return (date_from - trip_date).days

    return (trip_date - date_to).days


def _match_level(distance: int) -> str | None:
    if distance <= 2:
        return "ideal"
    if distance <= 7:
        return "good"
    return None


def _date_score(distance: int) -> int:
    return max(75 - distance * 10, 5)


def _seats_score(seats: int, passengers: int) -> int:
    spare_seats = max(seats - passengers, 0)

    if spare_seats == 0:
        return 25
    if spare_seats == 1:
        return 20
    if spare_seats == 2:
        return 15
    return 10


def _score(distance: int, seats: int, passengers: int) -> int:
    return _date_score(distance) + _seats_score(seats, passengers)


async def create_trip_match_if_not_exists(
    session: AsyncSession,
    request: TripRequest,
    offer: TripOffer,
    level: str,
    score: int,
) -> TripMatch | None:
    existing = await session.execute(
        select(TripMatch).where(
            TripMatch.request_id == request.id,
            TripMatch.offer_id == offer.id,
        )
    )

    if existing.scalar_one_or_none() is not None:
        return None

    match = TripMatch(
        request_id=request.id,
        offer_id=offer.id,
        level=level,
        score=score,
        status="proposed",
    )

    session.add(match)

    try:
        await session.flush()
        return match
    except IntegrityError:
        await session.rollback()
        return None


async def find_matches_for_trip_request(
    session: AsyncSession,
    request_id: int,
    top_n: int = 10,
) -> list[TripMatch]:

    request = await session.get(TripRequest, request_id)

    if not request or request.status != "active":
        return []

    result = await session.execute(
        select(TripOffer)
        .where(
            TripOffer.status == "active",
            TripOffer.from_city == request.from_city,
            TripOffer.to_city == request.to_city,
            TripOffer.user_id != request.user_id,
        )
    )

    offers = result.scalars().all()

    candidates = []

    for offer in offers:
        # Количество пассажиров должно помещаться в предложение
        if offer.seats < request.passengers:
            continue

        distance = _date_distance(
            offer.trip_date,
            request.date_from,
            request.date_to,
        )

        level = _match_level(distance)

        if not level:
            continue

        score = _score(
            distance,
            offer.seats,
            request.passengers,
        )

        candidates.append(
            (score, distance, offer)
        )

    candidates.sort(
        key=lambda item: (-item[0], item[1])
    )

    matches = []

    for score, distance, offer in candidates[:top_n]:
        level = _match_level(distance)

        if not level:
            continue

        match = await create_trip_match_if_not_exists(
            session=session,
            request=request,
            offer=offer,
            level=level,
            score=score,
        )

        if match:
            matches.append(match)

    await session.commit()

    return matches


async def find_matches_for_trip_offer(
    session: AsyncSession,
    offer_id: int,
    top_n: int = 10,
) -> list[TripMatch]:

    offer = await session.get(TripOffer, offer_id)

    if not offer or offer.status != "active":
        return []

    result = await session.execute(
        select(TripRequest)
        .where(
            TripRequest.status == "active",
            TripRequest.from_city == offer.from_city,
            TripRequest.to_city == offer.to_city,
            TripRequest.user_id != offer.user_id,
        )
    )

    requests = result.scalars().all()

    candidates = []

    for request in requests:
        if offer.seats < request.passengers:
            continue

        distance = _date_distance(
            offer.trip_date,
            request.date_from,
            request.date_to,
        )

        level = _match_level(distance)

        if not level:
            continue

        score = _score(
            distance,
            offer.seats,
            request.passengers,
        )

        candidates.append(
            (score, distance, request)
        )

    candidates.sort(
        key=lambda item: (-item[0], item[1])
    )

    matches = []

    for score, distance, request in candidates[:top_n]:
        level = _match_level(distance)

        if not level:
            continue

        match = await create_trip_match_if_not_exists(
            session=session,
            request=request,
            offer=offer,
            level=level,
            score=score,
        )

        if match:
            matches.append(match)

    await session.commit()

    return matches
