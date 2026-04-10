from datetime import date, datetime, timedelta

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from ..enums import WeightBand, CarryType, RowStatus
from ..models import User, Offer
from ..utils import norm

router = Router()


class OfferFSM(StatesGroup):
    from_city = State()
    to_city = State()
    trip_date = State()
    capacity_band = State()
    baggage_type = State()


RULES_TEXT = (
    "📋 Правила:\n\n"
    "• Перевозка под вашу ответственность\n"
    "• Проверяйте содержимое\n"
    "• Запрещённые вещи нельзя\n"
    "• Всё обсуждается в чате\n"
)


async def get_user(session, tg_user_id):
    q = select(User).where(User.tg_user_id == tg_user_id)
    return (await session.execute(q)).scalar_one_or_none()


def get_days_until_sunday(start: date):
    return 6 - start.weekday() + 1


# ================= KEYBOARDS =================

def kb_calendar_current_week():
    b = InlineKeyboardBuilder()
    today = date.today()

    for i in range(get_days_until_sunday(today)):
        d = today + timedelta(days=i)
        b.button(text=d.strftime("%d.%m"), callback_data=f"o_date:{d.isoformat()}")

    b.button(text="➡️ Следующая неделя", callback_data="o_cal:next")
    b.button(text="📅 В течение месяца", callback_data="o_date:month")

    b.adjust(3)
    return b.as_markup()


def kb_calendar_next_week():
    b = InlineKeyboardBuilder()
    today = date.today()
    start = today + timedelta(days=(7 - today.weekday()))

    for i in range(7):
        d = start + timedelta(days=i)
        b.button(text=d.strftime("%d.%m"), callback_data=f"o_date:{d.isoformat()}")

    b.button(text="⬅️ Назад", callback_data="o_cal:back")
    b.button(text="📅 В течение месяца", callback_data="o_date:month")

    b.adjust(3)
    return b.as_markup()


def kb_weight():
    b = InlineKeyboardBuilder()
    b.button(text="до 1 кг", callback_data="o_w:1")
    b.button(text="1–3 кг", callback_data="o_w:2")
    b.button(text="3–5 кг", callback_data="o_w:3")
    b.button(text="5+ кг", callback_data="o_w:4")
    b.adjust(2)
    return b.as_markup()


def kb_carry():
    b = InlineKeyboardBuilder()
    b.button(text="👜 Ручная кладь", callback_data="o_c:1")
    b.button(text="🧳 Багаж", callback_data="o_c:2")
    b.button(text="👌 Не важно", callback_data="o_c:3")
    b.adjust(1)
    return b.as_markup()


def kb_confirm():
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data="off:confirm")
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
    await state.update_data(from_city=norm(m.text))
    await state.set_state(OfferFSM.to_city)

    await m.answer("2/5 Куда едете?")


@router.message(OfferFSM.to_city)
async def step_to_city(m: Message, state: FSMContext):
    await state.update_data(to_city=norm(m.text))
    await state.set_state(OfferFSM.trip_date)

    await m.answer("3/5 Когда поездка?", reply_markup=kb_calendar_current_week())


# ================= CALENDAR =================

@router.callback_query(F.data == "o_cal:next")
async def calendar_next(cq: CallbackQuery):
    await cq.message.edit_reply_markup(reply_markup=kb_calendar_next_week())
    await cq.answer()


@router.callback_query(F.data == "o_cal:back")
async def calendar_back(cq: CallbackQuery):
    await cq.message.edit_reply_markup(reply_markup=kb_calendar_current_week())
    await cq.answer()


@router.callback_query(F.data.startswith("o_date:"))
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

@router.callback_query(F.data.startswith("o_w:"))
async def step_capacity(cq: CallbackQuery, state: FSMContext):
    await cq.answer()

    mp = {
        "1": WeightBand.lt1,
        "2": WeightBand.w1_3,
        "3": WeightBand.w3_5,
        "4": WeightBand.gt5,  # ✅ ИСПРАВЛЕНО
    }

    key = cq.data.split(":")[1]

    if key not in mp:
        await cq.message.answer("Ошибка выбора веса")
        return

    await state.update_data(capacity_band=mp[key])
    await state.set_state(OfferFSM.baggage_type)

    await cq.message.answer("5/5 Тип:", reply_markup=kb_carry())


# ================= BAGGAGE =================

@router.callback_query(F.data.startswith("o_c:"))
async def step_baggage(cq: CallbackQuery, state: FSMContext):
    await cq.answer()

    mp = {
        "1": CarryType.hand_only,
        "2": CarryType.luggage_ok,
        "3": CarryType.any,
    }

    key = cq.data.split(":")[1]

    if key not in mp:
        await cq.message.answer("Ошибка выбора типа")
        return

    await state.update_data(baggage_type=mp[key])

    await cq.message.answer(RULES_TEXT, reply_markup=kb_confirm())


# ================= CONFIRM =================

@router.callback_query(F.data == "off:confirm")
async def finish_offer(cq: CallbackQuery, state: FSMContext, **kwargs):
    await cq.answer()

    session = kwargs.get("session")

    if not session:
        await cq.message.answer("Ошибка: нет соединения с БД")
        return

    try:
        user = await get_user(session, cq.from_user.id)
        if not user:
            await cq.message.answer("Пользователь не найден")
            return

        data = await state.get_data()

        if not data:
            await cq.message.answer("Ошибка: данные потеряны")
            return

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
            status=RowStatus.draft,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        session.add(offer)
        await session.commit()

        await state.clear()

        await cq.message.answer("✅ Поездка сохранена")

    except Exception as e:
        print("🔥 ERROR IN finish_offer:", e)
        await cq.message.answer("Ошибка при сохранении поездки")

