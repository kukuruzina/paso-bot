from __future__ import annotations

from datetime import date, datetime, timedelta

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import WeightBand, CarryType, RowStatus
from ..keyboards import kb_main
from ..models import User, Offer
from ..utils import norm

router = Router()


# ---------- FSM ----------

class OfferFSM(StatesGroup):
    from_city = State()
    to_city = State()
    trip_date = State()
    capacity_band = State()
    baggage_type = State()
    confirm_rules = State()


# ---------- KEYBOARDS ----------

def kb_calendar(offset_days: int = 0):
    print("🔥 NEW CALENDAR LOADED")

    b = InlineKeyboardBuilder()

    today = date.today() + timedelta(days=offset_days)

    for i in range(7):
        d = today + timedelta(days=i)
        b.button(
            text=d.strftime("%d.%m"),
            callback_data=f"date:{d.isoformat()}",
        )

    b.button(text="➡️ Следующая неделя", callback_data=f"cal:next:{offset_days+7}")
    b.button(text="📅 Через 2 недели", callback_data="date:plus14")
    b.button(text="📅 Через месяц", callback_data="date:plus30")

    b.adjust(3)
    return b.as_markup()


def kb_confirm_offer():
    b = InlineKeyboardBuilder()
    b.button(text="✅ Принимаю правила", callback_data="off:confirm_rules")
    return b.as_markup()


# ---------- RULES ----------

RULES_TEXT_OFFER = (
    "📋 Правила:\n\n"
    "• Перевозка на ваш риск\n"
    "• Проверяйте содержимое\n"
    "• Запрещённые вещи нельзя\n"
    "• Всё обсуждается в чате\n"
)


# ---------- helpers ----------

async def get_user(session: AsyncSession, tg_user_id: int) -> User | None:
    q = select(User).where(User.tg_user_id == tg_user_id)
    return (await session.execute(q)).scalar_one_or_none()


# ---------- entry ----------

@router.callback_query(F.data == "go:off")
async def start_offer(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(OfferFSM.from_city)

    await cq.message.answer(
        "✈️ Предложить поездку\n\n1/5 Откуда выезжаете?"
    )
    await cq.answer()


# ---------- steps ----------

@router.message(OfferFSM.from_city)
async def step_from_city(m: Message, state: FSMContext):
    city = norm(m.text)
    if not city:
        await m.answer("Введите город")
        return

    await state.update_data(from_city=city)
    await state.set_state(OfferFSM.to_city)

    await m.answer("2/5 Куда едете?")


@router.message(OfferFSM.to_city)
async def step_to_city(m: Message, state: FSMContext):
    city = norm(m.text)
    if not city:
        await m.answer("Введите город")
        return

    await state.update_data(to_city=city)
    await state.set_state(OfferFSM.trip_date)

    await m.answer(
        "3/5 Когда поездка?",
        reply_markup=kb_calendar()
    )


# ---------- CALENDAR ----------

@router.callback_query(OfferFSM.trip_date, F.data.startswith("cal:"))
async def calendar_nav(cq: CallbackQuery, state: FSMContext):
    _, _, offset = cq.data.split(":")
    offset = int(offset)

    await cq.message.edit_reply_markup(
        reply_markup=kb_calendar(offset)
    )
    await cq.answer()


@router.callback_query(OfferFSM.trip_date, F.data.startswith("date:plus"))
async def step_date_plus(cq: CallbackQuery, state: FSMContext):
    val = cq.data.split(":")[1]

    today = date.today()

    if val == "plus14":
        d = today + timedelta(days=14)
    elif val == "plus30":
        d = today + timedelta(days=30)
    else:
        return

    await state.update_data(trip_date=d.isoformat())
    await state.set_state(OfferFSM.capacity_band)

    await cq.message.answer("4/5 Сколько веса можете взять?")
    await cq.answer()


@router.callback_query(OfferFSM.trip_date, F.data.startswith("date:"))
async def step_date(cq: CallbackQuery, state: FSMContext):
    val = cq.data.split(":")[1]

    await state.update_data(trip_date=val)
    await state.set_state(OfferFSM.capacity_band)

    await cq.message.answer("4/5 Сколько веса можете взять?")
    await cq.answer()


# ---------- CAPACITY ----------

@router.message(OfferFSM.capacity_band)
async def step_capacity(m: Message, state: FSMContext):
    mp = {
        "1": WeightBand.lt1,
        "2": WeightBand.w1_3,
        "3": WeightBand.w3_5,
        "4": WeightBand.gt5,
    }
    cap = mp.get((m.text or "").strip())
    if not cap:
        await m.answer("Введите цифру 1–4.")
        return

    await state.update_data(capacity_band=cap.value)
    await state.set_state(OfferFSM.baggage_type)

    await m.answer(
        "5/5 Тип перевозки:\n"
        "1 — ручная кладь\n"
        "2 — багаж\n"
        "3 — не важно"
    )


# ---------- BAGGAGE ----------

@router.message(OfferFSM.baggage_type)
async def step_baggage(m: Message, state: FSMContext):
    mp = {
        "1": CarryType.hand_only,
        "2": CarryType.luggage_ok,
        "3": CarryType.any,
    }
    bt = mp.get((m.text or "").strip())
    if not bt:
        await m.answer("Введите цифру 1–3.")
        return

    await state.update_data(baggage_type=bt.value)
    await state.set_state(OfferFSM.confirm_rules)

    await m.answer(RULES_TEXT_OFFER, reply_markup=kb_confirm_offer())


# ---------- CONFIRM ----------

@router.callback_query(OfferFSM.confirm_rules, F.data == "off:confirm_rules")
async def finish_offer(cq: CallbackQuery, state: FSMContext, session: AsyncSession):

    user = await get_user(session, cq.from_user.id)
    if not user:
        await cq.message.answer("Ошибка пользователя. Нажмите /start.")
        await state.clear()
        return

    data = await state.get_data()

    offer = Offer(
        user_id=user.id,
        from_country="unknown",
        from_city=data.get("from_city"),
        to_country="Russia",
        to_city=data.get("to_city"),
        trip_date=date.fromisoformat(data["trip_date"]),
        capacity_band=data["capacity_band"],
        baggage_type=data["baggage_type"],
        price_mode="discuss",
        status=RowStatus.active,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    session.add(offer)
    await session.commit()

    await state.clear()

    await cq.message.answer(
        "✅ Поездка сохранена",
        reply_markup=kb_main(),
    )
    await cq.answer()

