from datetime import date, datetime, timedelta

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User, Offer, Request
from app.enums import WeightBand, CarryType, RowStatus
from app.matching import find_matches_for_offer
from app.utils import norm
from app.keyboards import kb_popular_cities
from app.handlers.request_flow import format_offer_text

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
    transport_type = State()
    capacity_band = State()
    baggage_type = State()
    confirm = State( )


# ================= HELPERS =================

async def get_user(session, tg_user_id):
    q = select(User).where(User.tg_user_id == tg_user_id)
    return (await session.execute(q)).scalar_one_or_none()


def format_request_text(req: Request, user: User | None, transport_type: str):
    # рейтинг
    if user and user.rating_count:
        rating_str = f"{round(user.rating_avg,1)}⭐({user.rating_count})"
    else:
        rating_str = "новый"

    # 🔥 время → из диапазона в текст
    if not req.delivery_date_from or not req.delivery_date_to:
        time_str = "как можно быстрее"
    else:
        delta = (req.delivery_date_to - req.delivery_date_from).days

        if delta <= 7:
            time_str = "ближайшие дни"
        elif delta <= 14:
            time_str = "1–2 недели"
        else:
            time_str = "в течение месяца"

    # 🔥 вес
    weight_map = {
        "lt1": "до 1 кг",
        "w1_3": "1–3 кг",
        "w3_5": "3–5 кг",
        "gt5": "5+ кг",
    }

    # 🔥 перевозка (одно слово!)
    carry_map = {
        "hand": "ручная кладь",
        "luggage": "багаж",
        "any": "не важно",
    }

    return (
        f"📦 {req.from_city} → {req.to_city}\n"
        f"📅 Нужно: {time_str}\n"
        f"🎒 Вес: {weight_map.get(str(req.weight_band), req.weight_band)}\n"
        f"🧳 Перевозка: {carry_map.get(str(req.carry_type), '')}\n\n"
        f"👤 Рейтинг: {rating_str}"
    )


def match_keyboard(match_id: int, user):
    b = InlineKeyboardBuilder()

    if user.is_admin:
        btn_text = "🔓 Открыть контакт"
    else:
        btn_text = (
            f"🔓 Открыть контакт • "
            f"останется: {max((user.contacts_left or 0) - 1, 0)}"
        )

    b.button(
        text=btn_text,
        callback_data=f"match:contact:{match_id}"
    )

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

    await cq.message.answer(
        "🧳 Взять посылку\n\n"
        "1/6 Откуда выезжаете? Выберите из популярных направлений или введите свое: ",
        reply_markup=kb_popular_cities(),
    )

    await cq.answer()


# =========================================================
# INLINE POPULAR CITIES
# =========================================================

@router.callback_query(
    OfferFSM.from_city,
    F.data.startswith("city:")
)
async def select_from_city(
    cq: CallbackQuery,
    state: FSMContext
):

    city = cq.data.split(":")[1]

    await state.update_data(from_city=city)
    await state.set_state(OfferFSM.to_city)

    await cq.message.answer(
        "2/6 Куда едете? Выберите из популярных направлений или введите свое:",
        reply_markup=kb_popular_cities(exclude=city),
    )

    await cq.answer()


@router.callback_query(
    OfferFSM.to_city,
    F.data.startswith("city:")
)
async def select_to_city(
    cq: CallbackQuery,
    state: FSMContext
):

    city = cq.data.split(":")[1]

    await state.update_data(to_city=city)
    await state.set_state(OfferFSM.trip_date)

    await cq.message.answer(
        "3/6 Когда поездка?",
        reply_markup=kb_calendar_current_week(),
    )

    await cq.answer()


# =========================================================
# MANUAL INPUT
# =========================================================

@router.message(OfferFSM.from_city)
async def step_from_city(m: Message, state: FSMContext):

    city = norm(m.text)

    if not city or len(city) < 3:
        return await m.answer("Введите корректный город")

    await state.update_data(from_city=city)
    await state.set_state(OfferFSM.to_city)

    await m.answer(
        "2/6 Куда едете?",
        reply_markup=kb_popular_cities(exclude=city),
    )


@router.message(OfferFSM.to_city)
async def step_to_city(m: Message, state: FSMContext):

    city = norm(m.text)

    if not city or len(city) < 3:
        return await m.answer("Введите корректный город")

    await state.update_data(to_city=city)
    await state.set_state(OfferFSM.trip_date)

    await m.answer(
        "3/6 Когда поездка?",
        reply_markup=kb_calendar_current_week(),
    )


@router.callback_query(F.data.startswith("o_date:"))
async def step_date(cq: CallbackQuery, state: FSMContext):

    await cq.answer()

    val = cq.data.split(":")[1]
    today = date.today()

    d = (
        today + timedelta(days=30)
        if val == "month"
        else date.fromisoformat(val)
    )

    await state.update_data(trip_date=d.isoformat())

    # транспорт
    await state.set_state(OfferFSM.transport_type)

    await cq.message.answer(
        "4/6 Как передвигаетесь?",
        reply_markup=kb_transport(),
    )

def kb_transport():
    b = InlineKeyboardBuilder()
    b.button(text="✈️ Самолет", callback_data="o_t:plane")
    b.button(text="🚗 Машина", callback_data="o_t:car")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(F.data.startswith("o_t:"))
async def step_transport(cq: CallbackQuery, state: FSMContext):
    await cq.answer()

    val = cq.data.split(":")[1]
    await state.update_data(transport_type=val)

    # 🔥 потом вес (возможности)
    await state.set_state(OfferFSM.capacity_band)
    await cq.message.answer("5/6 Сколько сможете взять?", reply_markup=kb_weight())


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

    # 🔥 потом багаж
    await state.set_state(OfferFSM.baggage_type)
    await cq.message.answer("6/6 В чем сможете взять?", reply_markup=kb_carry_offer())


def kb_carry_offer():
    b = InlineKeyboardBuilder()
    b.button(text="🎒 Только ручная кладь", callback_data="o_c:1")
    b.button(text="🧳 Есть багаж", callback_data="o_c:2")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(F.data.startswith("o_c:"))
async def step_carry(cq: CallbackQuery, state: FSMContext):
    await cq.answer()

    mp = {
        "1": "hand",
        "2": "luggage",
    }

    await state.update_data(baggage_type=mp[cq.data.split(":")[1]])

    # 🔥 ВАЖНО: финальное состояние
    await state.set_state(OfferFSM.confirm)

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

    # 🔥 1. ПРОВЕРКА STATE (защита от старых кнопок)
    current_state = await state.get_state()
    if current_state != OfferFSM.confirm.state:
        await state.clear()
        return await cq.message.answer(
            "❌ Сессия устарела, начните заново /start"
        )

    user = await get_user(session, cq.from_user.id)
    if not user:
        return await cq.message.answer("❌ Пользователь не найден")

    data = await state.get_data()

    # 🔥 2. ПРОВЕРКА ДАННЫХ (защита от потери FSM)
    required_fields = [
        "from_city",
        "to_city",
        "trip_date",
        "capacity_band",
        "baggage_type",
    ]

    missing = [f for f in required_fields if not data.get(f)]

    if missing:
        print("❌ FSM DATA MISSING:", missing, data)
        await state.clear()
        return await cq.message.answer(
            "❌ Данные потерялись. Пожалуйста создайте поездку заново /start"
        )

    # 🔥 3. СОЗДАЁМ OFFER

    if not cq.from_user.username:

        await cq.message.answer(
            "⚠️ Для использования PASO нужен username в Telegram.\n\n"
            "Откройте:\n"
            "Telegram → Настройки → Имя пользователя"
        )

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
        transport_type=data.get("transport_type", "any"),
        price_mode="discuss",
        status=RowStatus.active,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    session.add(offer)
    await session.commit()
    await session.refresh(offer)

    await state.clear()

    # 🔥 4. MATCHING
    from app.matching import find_matches_for_offer

    matches = await find_matches_for_offer(
        session,
        offer.id,
        window_days=0,
        top_n=5
    )

    if not matches:
        await cq.message.answer("😔 Пока подходящих заявок нет")
        return await cq.message.edit_reply_markup(reply_markup=None)

    await cq.message.answer(f"🔥 Найдено {len(matches)} заявок:\n")

    user = await session.scalar(
        select(User).where(User.tg_user_id == cq.from_user.id)
    )

# 📦 ПОКАЗ ПЕРЕВОЗЧИКУ
    for i, m in enumerate(matches):

        if i >= 3:
            await cq.message.answer("🔒 Есть ещё заявки — открой доступ")
            break

        req = await session.get(Request, m.request_id)
        if not req:
            continue

        req_user = await session.get(User, req.user_id)

        await cq.message.answer(
            format_request_text(req, req_user, offer.transport_type),
            reply_markup=match_keyboard(m.id, user),
        )


    # 🔔 PUSH: уведомляем отправителей (без дублей)
    for m in matches:

        # уже отправляли
        if getattr(m, "notified_requester", False):
            continue

        req = await session.get(Request, m.request_id)
        if not req:
            continue

        req_user = await session.get(User, req.user_id)

        # не пушим самому себе
        if not req_user or req_user.tg_user_id == cq.from_user.id:
            continue

        try:
            off_user = await session.get(User, offer.user_id)

            # сообщение 1
            await cq.bot.send_message(
                req_user.tg_user_id,
                "🔥 Появился перевозчик под вашу заявку:\n",
            )

            # сообщение 2 (карточка перевозчика)
            await cq.bot.send_message(
                req_user.tg_user_id,
                format_offer_text(offer, off_user),
                reply_markup=match_keyboard(m.id, user),
            )

            # ✅ ставим флаг только после успеха
            m.notified_requester = True

            print(f"📤 PUSH SENT (requester): match_id={m.id}")

        except Exception as e:
            import traceback
            print("❌ PUSH ERROR (request user):", e)
            traceback.print_exc()


    # 🔥 сохраняем изменения
    await session.commit()





