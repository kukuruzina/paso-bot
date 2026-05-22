import asyncio

from sqlalchemy import select

from aiogram import Bot

from app.db import get_session
from app.models import (
    Request,
    Match,
    Offer,
    User,
)
from app.matching import find_matches_for_request
from app.config import load_config


# =====================================================
# SEND NOTIFICATIONS
# =====================================================

async def send_unnotified_matches(
    bot: Bot,
    session,
):

    q = select(Match).where(
        Match.notified_requester == False
    )

    matches = (
        await session.execute(q)
    ).scalars().all()

    print("UNNOTIFIED MATCHES:", len(matches))

    for match in matches:

        try:

            req = await session.get(
                Request,
                match.request_id
            )

            off = await session.get(
                Offer,
                match.offer_id
            )

            carrier = await session.get(
                User,
                off.user_id
            )

            requester = await session.get(
                User,
                req.user_id
            )

            if match.level == "best":
                badge = "🔥 Лучшее совпадение"
            else:
                badge = "🟡 Возможный вариант"

            await bot.send_message(
                requester.tg_user_id,

                f"{badge}\n\n"

                f"✈️ {off.from_city} → {off.to_city}\n"
                f"📅 {off.trip_date.strftime('%d.%m.%Y')}\n"
                f"📦 Вес: {off.capacity_band}\n"
                f"🚗 Транспорт: {off.transport_type}\n\n"

                "👇 Откройте PASO чтобы посмотреть"
            )

            match.notified_requester = True

            print(
                "✅ PUSH SENT:",
                match.id
            )

        except Exception as e:

            print(
                "❌ PUSH ERROR:",
                match.id,
                e
            )

    await session.commit()


# =====================================================
# MAIN
# =====================================================

async def main():

    cfg = load_config()

    bot = Bot(cfg.bot_token)

    async with get_session() as session:

        requests = (
            await session.execute(
                select(Request)
            )
        ).scalars().all()

        print("REQUESTS:", len(requests))

        # =====================================================
        # REBUILD MATCHES
        # =====================================================

        for req in requests:

            print("MATCH REQUEST:", req.id)

            await find_matches_for_request(
                bot,
                session,
                req.id,
                cfg.match_window_days,
                cfg.top_matches,
            )

        # =====================================================
        # SEND PUSHES
        # =====================================================

        await send_unnotified_matches(
            bot,
            session,
        )

    await bot.session.close()


# =====================================================
# START
# =====================================================

asyncio.run(main())

