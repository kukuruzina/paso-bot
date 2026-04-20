from datetime import date, datetime, timedelta

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User, Offer, Request
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
    transport_type = State()  # 🔥 новое


# ================= HELPERS =================

async def get_user(session, tg_user_id):
    q = select(User).where(User.tg_user_id == tg_user_id)
    return (await session.execute(q)).scalar_one_or_none()


def format_request_text(req: Request, user: User | None, transport_type: str):
    if user and user.rating_count:
        rating_str = f"{round(user.rating_avg,1)}⭐({user.rating_count})"
    else:
        rating_str = "новый"

    weight_map = {
        "lt1": "до 1 кг",
        "w1_3": "1–3 кг",
        "w3_5": "3–5 кг",
        "gt5": "5+ кг",
    }

    transport_map = {
        "plane": "✈️ Самолет",
        "car": "🚗 Машина",
        "any": "любой",
    }

    return (
        f"📦 {req.from_city} → {req.to_city}\n"
        f"📅 Нужно до: {req.delivery_date_to.strftime('%d.%m')}\n"
        f"🎒 Вес: {weight_map.get(str(req.weight_band), req.weight_band)}\n"
        f"🚘 Тип: {transport_map.get(transport_type, 'любой')}\n\n"
        f"👤 Рейтинг: {rating_str}"
    )


def match_keyboard(match_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="🔓 Открыть контакт (−1)", callback_data=f"match:contact:{match_id}")
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

    days_to_monday = (7 - today.weekday()) % 7 or 7
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


@router.callback_query(F.data == "o_cal:next")
async def calendar_next(cq: CallbackQuery):
    await cq.answer()
    await cq.message.edit_reply_markup(reply_markup=kb_calendar_next_week())


@router.callback_query(F.data == "o_cal:back")
async def calendar_back(cq: CallbackQuery):
    await cq.answer()
    await cq.message.edit_reply_markup(reply_markup=kb_calendar_current_week())


# ================= FLOW =================

@router.callback_query(F.data == "go:off")
async def start_offer(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(OfferFSM.from_city)

    await cq.message.answer("✈️ 1/6 Откуда выезжаете?")
    await cq.answer()


@router.message(OfferFSM.from_city)
async def step_from_city(m: Message, state: FSMContext):
    city = norm(m.text)

    if not city or len(city) < 3:
        return await m.answer("Введите корректный город")

    await state.update_data(from_city=city)
    await state.set_state(OfferFSM.to_city)

    await m.answer("2/6 Куда едете?")


@router.message(OfferFSM.to_city)
async def step_to_city(m: Message, state: FSMContext):
    city = norm(m.text)

    if not city or len(city) < 3:
        return await m.answer("Введите корректный город")

    await state.update_data(to_city=city)
    await state.set_state(OfferFSM.trip_date)

    await m.answer("3/6 Когда поездка?", reply_markup=kb_calendar_current_week())


@router.callback_query(F.data.startswith("o_date:"))
async def step_date(cq: CallbackQuery, state: FSMContext):
    await cq.answer()

    val = cq.data.split(":")[1]
    today = date.today()

    d = today + timedelta(days=30) if val == "month" else date.fromisoformat(val)

    await state.update_data(trip_date=d.isoformat())
    await state.set_state(OfferFSM.capacity_band)

    await cq.message.answer("4/6 Вес:", reply_markup=kb_weight())


def kb_weight():
    b = InlineKeyboardBuilder()
    b.button(text="до 1 кг", callback_data="o_w:1")
    b.button(text="1–3 кг", callback_data="o_w:2")
    b.button(text="3–5 кг", callback_data="o_w:3")
    b.button(text="5+ кг", callback_data="o_w:4")
    b.adjust(2)
    return b.as_markup()


@router.callback_query(F.data.startswith("o_w:"))
async def step_weight(cq: CallbackQuery, state: FSMContext):
    await cq.answer()

    mp = {
        "1": WeightBand.lt1,
        "2": WeightBand.w1_3,
        "3": WeightBand.w3_5,
        "4": WeightBand.gt5,
    }

    await state.update_data(capacity_band=mp[cq.data.split(":")[1]])
    await state.set_state(OfferFSM.baggage_type)

    await cq.message.answer("5/6 Тип багажа:", reply_markup=kb_carry())


def kb_carry():
    b = InlineKeyboardBuilder()
    b.button(text="👜 Ручная кладь", callback_data="o_c:1")
    b.button(text="🧳 Багаж", callback_data="o_c:2")
    b.button(text="👌 Не важно", callback_data="o_c:3")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(F.data.startswith("o_c:"))
async def step_carry(cq: CallbackQuery, state: FSMContext):
    await cq.answer()

    mp = {
        "1": CarryType.hand_only,
        "2": CarryType.luggage_ok,
        "3": CarryType.any,
    }

    await state.update_data(baggage_type=mp[cq.data.split(":")[1]])
    await state.set_state(OfferFSM.transport_type)

    await cq.message.answer("6/6 Как передвигаетесь?", reply_markup=kb_transport())


def kb_transport():
    b = InlineKeyboardBuilder()
    b.button(text="✈️ Самолет", callback_data="o_t:plane")
    b.button(text="🚗 Машина", callback_data="o_t:car")
    b.button(text="👌 Не важно", callback_data="o_t:any")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(F.data.startswith("o_t:"))
async def step_transport(cq: CallbackQuery, state: FSMContext):
    await cq.answer()

    val = cq.data.split(":")[1]
    await state.update_data(transport_type=val)

    await cq.message.answer(RULES_TEXT)
    await cq.message.answer("👇", reply_markup=kb_confirm())


def kb_confirm():
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data="off:confirm")
    return b.as_markup()


# ================= FINISH =================

@router.callback_query(F.data == "off:confirm")
async def finish_offer(cq: CallbackQuery, state: FSMContext, session: AsyncSession):
    await cq.answer()

    user = await get_user(session, cq.from_user.id)
    data = await state.get_data()

    offer = Offer(
        user_id=user.id,
        from_country="any",
        from_city=data["from_city"],
        to_country="any",
        to_city=data["to_city"],
        trip_date=date.fromisoformat(data["trip_date"]),
        capacity_band=data["capacity_band"],
        baggage_type=data["baggage_type"],
        transport_type=data.get("transport_type", "any"),  # 🔥
        price_mode="discuss",
        status=RowStatus.active,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    session.add(offer)
    await session.commit()
    await session.refresh(offer)

    await state.clear()

    matches = await find_matches_for_offer(session, offer.id, 5, 0)

    if not matches:
        return await cq.message.answer("😔 Пока заявок нет")

    await cq.message.answer(f"🔥 Найдено {len(matches)} заявок:\n")

    for i, m in enumerate(matches):
        if i >= 3:
            await cq.message.answer("🔒 Есть ещё заявки — открой доступ")
            break

        req = await session.get(Request, m.request_id)
        req_user = await session.get(User, req.user_id)

        await cq.message.answer(
            format_request_text(req, req_user, offer.transport_type),
            reply_markup=match_keyboard(m.id)
        )

