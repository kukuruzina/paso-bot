from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import User
from ..keyboards import kb_main

router = Router()


async def upsert_user(session: AsyncSession, msg: Message):
    tg = msg.from_user
    if not tg:
        return None

    q = select(User).where(User.tg_user_id == tg.id)
    user = (await session.execute(q)).scalar_one_or_none()

    if not user:
        user = User(
            tg_user_id=tg.id,
            tg_username=tg.username,
            first_name=tg.first_name,
            last_name=tg.last_name,
            language_code=tg.language_code,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user


@router.message(CommandStart())
async def start(m: Message, session: AsyncSession, command: CommandObject):
    await upsert_user(session, m)

    # 👉 Если пользователь пришёл после оплаты
    if command.args and command.args.strip().lower() == "paid":
        await m.answer(
            "✅ Подписка активна!\n\n"
            "Давайте создадим заявку 👇"
        )

        # ⚡ сразу запускаем request flow
        # это эквивалент нажатия кнопки "Создать заявку"
        from ..handlers.request_flow import start_request
        from aiogram.types import CallbackQuery

        fake_callback = CallbackQuery(
            id="paid_start",
            from_user=m.from_user,
            chat_instance="paid",
            message=m,
            data="go:req"
        )

        # вызываем тот же handler
        await start_request(fake_callback, state=None)

        return

    # обычный старт
    await m.answer(
        "📦 PASO — сервис передачи посылок между городами и странами.\n\n"
        "Если кто-то уже едет/летит в нужный город или страну, "
        "он может взять вашу посылку и передать её получателю.\n\n"
        "Через сервис можно отправить:\n"
        "• документы\n"
        "• косметику\n"
        "• подарки\n"
        "• личные вещи\n\n"
        "Для использования сервиса требуется подписка.\n\n"
        "Что вы хотите сделать?",
        reply_markup=kb_main(),
    )
