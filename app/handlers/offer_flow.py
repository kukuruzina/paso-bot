from datetime import date, datetime, timedelta

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User, Offer, Match, Request
from app.enums import WeightBand, CarryType, RowStatus
from app.matching import find_matches_for_offer
from app.utils import norm

router = Router()

# ================= RULES =================

RULES_TEXT = (
    "📋 Правила:\n\n"
    "• Перевозка под вашу ответственность\n"
    "• Запрещённые вещи нельзя\n"
    "• Всё обсуждается в чате"
)

# ================= FSM =================

class OfferFSM(StatesGroup):
    from_city = State()
    to_city = State()
    trip_date = State()
    capacity_band = State()
    baggage_type = State()


# ================= HELPERS =================

async def get_user(session, tg_user_id):
    q = select(User).where(User.tg_user_id == tg_user_id)
    return (await session.execute(q)).scalar_one_or_none()


def get_offer_time_type(trip_date: date):
    delta = (trip_date - date.today()).days
    if delta <= 7:
        return "soon"
    elif delta <= 14:
        return "week_1_2"
    return "month"


def format_match_text(req: Request, trip_date):
    username = req.user.username if req.user and req.user.username else "user"
    hidden = username[:2] + "***"

    t = get_offer_time_type(trip_date)

    if t == "soon":
        trip_str = trip_date.strftime("%d.%m") + " (скоро)"
    elif t == "week_1_2":
        trip_str = trip_date.strftime("%d.%m") + " (1–2 недели)"
    else:
        trip_str = "в течение месяца"

    return (
        f"📦 {req.from_city} → {req.to_city}\n"
        f"📅 до {req.date_to}\n"
        f"✈️ Поездка: {trip_str}\n"
        f"🎒 {req.weight_band}\n\n"
        f"👤 @{hidden}\n\n"
        f"🔒 Контакт скрыт"
    )


def match_keyboard(match_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="🔓 Открыть контакт", callback_data=f"unlock:{match_id}")
    return b.as_markup()


# ================= CALENDAR =================

def kb_calendar_current_week():
    b = InlineKeyboardBuilder()
    today = date.today()

    days_until_sunday = 6 - today.weekday()

    for i in range(days_until_sunday + 1):
        d = today + timedelta(days=i)
        b.button(
            text=d.strftime("%d.%m"),
            callback_data=f"o_date:{d.isoformat()}"
        )

    b.button(text="➡️ Следующая неделя", callback_data="o_cal:next")
    b.button(text="🐢 В течение месяца", callback_data="o_date:month")

    b.adjust(3)
    return b.as_markup()


def kb_calendar_next_week():
    b = InlineKeyboardBuilder()
    today = date.today()

    days_to_monday = (7 - today.weekday()) % 7
    if days_to_monday == 0:
        days_to_monday = 7

    start = today + timedelta(days=days_to_monday)

    for i in range(7):
        d = start + timedelta(days=i)
        b.button(
            text=d.strftime("%d.%m"),
            callback_data=f"o_date:{d.isoformat()}"
        )

    b.button(text="⬅️ Назад", callback_data="o_cal:back")
    b.button(text="🐢 В течение месяца", callback_data="o_date:month")

    b.adjust(3)
    return b.as_markup()


# ================= FLOW =================

@router.callback_query(F.data == "go:off")
async def start_offer(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(OfferFSM.from_city)

    await cq.message.answer("✈️ 1/5 Откуда выезжаете?")
    await cq.answer()


@router.message(OfferFSM.from_city)
async def step_from_city(m: Message, state: FSMContext):
    city = norm(m.text)
    if not city:
        return await m.answer("Введите город")

    await state.update_data(from_city=city)
    await state.set_state(OfferFSM.to_city)

    await m.answer("2/5 Куда едете?")


@router.message(OfferFSM.to_city)
async def step_to_city(m: Message, state: FSMContext):
    city = norm(m.text)
    if not city:
        return await m.answer("Введите город")

    await state.update_data(to_city=city)
    await state.set_state(OfferFSM.trip_date)

    await m.answer("3/5 Когда поездка?", reply_markup=kb_calendar_current_week())


# ================= NAV =================

@router.callback_query(F.data == "o_cal:next", OfferFSM.trip_date)
async def calendar_next(cq: CallbackQuery):
    await cq.message.edit_reply_markup(reply_markup=kb_calendar_next_week())
    await cq.answer()


@router.callback_query(F.data == "o_cal:back", OfferFSM.trip_date)
async def calendar_back(cq: CallbackQuery):
    await cq.message.edit_reply_markup(reply_markup=kb_calendar_current_week())
    await cq.answer()


# ================= DATE =================

@router.callback_query(F.data.startswith("o_date:"), OfferFSM.trip_date)
async def step_date(cq: CallbackQuery, state: FSMContext):
    await cq.answer()

    val = cq.data.split(":")[1]
    today = date.today()

    if val == "month":
        d = today + timedelta(days=30)
    else:
        d = date.fromisoformat(val)

    await state.update_data(trip_date=d.isoformat())
    await state.set_state(OfferFSM.capacity_band)

    await cq.message.answer("4/5 Вес:", reply_markup=kb_weight())


# ================= WEIGHT =================

def kb_weight():
    b = InlineKeyboardBuilder()
    b.button(text="до 1 кг", callback_data="o_w:1")
    b.button(text="1–3 кг", callback_data="o_w:2")
    b.button(text="3–5 кг", callback_data="o_w:3")
    b.button(text="5+ кг", callback_data="o_w:4")
    b.adjust(2)
    return b.as_markup()


@router.callback_query(F.data.startswith("o_w:"))
async def step_capacity(cq: CallbackQuery, state: FSMContext):
    await cq.answer()

    mp = {
        "1": WeightBand.lt1,
        "2": WeightBand.w1_3,
        "3": WeightBand.w3_5,
        "4": WeightBand.gt5,
    }

    await state.update_data(capacity_band=mp[cq.data.split(":")[1]])
    await state.set_state(OfferFSM.baggage_type)

    await cq.message.answer("5/5 Тип:", reply_markup=kb_carry())


# ================= BAGGAGE =================

def kb_carry():
    b = InlineKeyboardBuilder()
    b.button(text="👜 Ручная кладь", callback_data="o_c:1")
    b.button(text="🧳 Багаж", callback_data="o_c:2")
    b.button(text="👌 Не важно", callback_data="o_c:3")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(F.data.startswith("o_c:"))
async def step_baggage(cq: CallbackQuery, state: FSMContext):
    await cq.answer()

    mp = {
        "1": CarryType.hand_only,
        "2": CarryType.luggage_ok,
        "3": CarryType.any,
    }

    await state.update_data(baggage_type=mp[cq.data.split(":")[1]])

    await cq.message.answer(RULES_TEXT)
    await cq.message.answer("👇", reply_markup=kb_confirm())


def kb_confirm():
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data="off:confirm")
    return b.as_markup()


# ================= CONFIRM =================

@router.callback_query(F.data == "off:confirm")
async def finish_offer(cq: CallbackQuery, state: FSMContext, session: AsyncSession):
    await cq.answer()

    user = await get_user(session, cq.from_user.id)
    data = await state.get_data()

    offer = Offer(
        user_id=user.id,
        from_country="any",
        from_city=data.get("from_city"),
        to_country="any",
        to_city=data.get("to_city"),

        trip_date=date.fromisoformat(data.get("trip_date")),

        capacity_band=data.get("capacity_band"),
        baggage_type=data.get("baggage_type"),

        price_mode="discuss",
        status=RowStatus.active,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    session.add(offer)
    await session.commit()
    await session.refresh(offer)

    await state.clear()

    print("🚀 CALL MATCHING FOR OFFER", offer.id)

    matches = await find_matches_for_offer(session, offer.id, 5, 0)

    if not matches:
        await cq.message.answer("😔 Пока совпадений нет")
        return

    await cq.message.answer(f"🔥 Найдено {len(matches)} совпадений:\n")

    for m in matches:
        req = await session.get(Request, m.request_id)
        if not req:
            continue

        await cq.message.answer(
            format_match_text(req, offer.trip_date),
            reply_markup=match_keyboard(m.id)
        )


