from __future__ import annotations

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

from app.enums import Category, WeightBand, CarryType, RowStatus
from app.models import User, Request, Offer
from app.utils import norm
from ..keyboards import kb_popular_cities_INLINE

router = Router()

# ================= RULES =================

RULES_TEXT = (
    "📋 Правила:\n\n"
    "• Отправка на ваш риск\n"
    "• Запрещённые вещи нельзя\n"
    "• Всё обсуждается в чате"
)

# ================= FSM =================

class RequestFSM(StatesGroup):
    from_city = State()
    to_city = State()
    category = State()
    transport_type = State()
    weight_band = State()
    carry_type = State()
    time_type = State()
    confirm = State( )


# ================= HELPERS =================

async def get_user(session: AsyncSession, tg_user_id: int):
    q = select(User).where(User.tg_user_id == tg_user_id)
    return (await session.execute(q)).scalar_one_or_none()


def request_to_range(time_type: str):
    today = date.today()

    if time_type == "soon":
        return today, today + timedelta(days=7)
    elif time_type == "week_1_2":
        return today + timedelta(days=7), today + timedelta(days=14)
    elif time_type == "month":
        return today, today + timedelta(days=30)

    return today, today + timedelta(days=7)


# ================= FORMAT HELPERS (NEW) =================

def format_time_label(req) -> str:
    """
    Человеческий формат времени для карточки
    """
    if not req.delivery_date_from or not req.delivery_date_to:
        return "в ближайшие дни"

    delta = (req.delivery_date_to - req.delivery_date_from).days

    if delta <= 7:
        return "в ближайшие дни"
    elif delta <= 14:
        return "1–2 недели"
    else:
        return "в течение месяца"


def format_carry_label(carry_type: str) -> str:
    """
    Формат перевозки (ручная / багаж)
    """
    mapping = {
        "hand": "🎒 в ручной клади",
        "luggage": "🧳 в багаже",
        "any": "🧳 не важно",
    }
    return mapping.get(str(carry_type), "")


def format_weight_label(weight_band) -> str:
    mapping = {
        "lt1": "до 1 кг",
        "w1_3": "1–3 кг",
        "w3_5": "3–5 кг",
        "gt5": "5+ кг",
    }

    val = weight_band.value if hasattr(weight_band, "value") else str(weight_band)
    return mapping.get(val, val)


# ================= UI =================

def kb_category():
    b = InlineKeyboardBuilder()
    b.button(text="👕 Одежда/Обувь", callback_data="cat:1")
    b.button(text="💄 Косметика/Лекарства", callback_data="cat:2")
    b.button(text="📄 Документы", callback_data="cat:3")
    b.button(text="📱 Техника", callback_data="cat:4")
    b.button(text="📦 Другое", callback_data="cat:5")
    b.adjust(1)
    return b.as_markup()


def kb_weight():
    b = InlineKeyboardBuilder()
    b.button(text="до 1 кг", callback_data="w:1")
    b.button(text="1–3 кг", callback_data="w:2")
    b.button(text="3–5 кг", callback_data="w:3")
    b.button(text="5+ кг", callback_data="w:4")
    b.adjust(2)
    return b.as_markup()


def kb_carry():
    b = InlineKeyboardBuilder()
    b.button(text="🎒 Можно в ручной клади", callback_data="c:1")
    b.button(text="🧳 Нужен багаж", callback_data="c:2")
    b.button(text="👌 Без разницы", callback_data="c:3")
    b.adjust(1)
    return b.as_markup()


def kb_transport():
    b = InlineKeyboardBuilder()
    b.button(text="✈️ Самолет", callback_data="t2:plane")
    b.button(text="🚗 Машина", callback_data="t2:car")
    b.button(text="👌 Не важно", callback_data="t2:any")
    b.adjust(1)
    return b.as_markup()


def kb_time():
    b = InlineKeyboardBuilder()
    b.button(text="⚡ Ближайшие дни", callback_data="t:soon")
    b.button(text="📅 1–2 недели", callback_data="t:week_1_2")
    b.button(text="🐢 В течение месяца", callback_data="t:month")
    b.adjust(1)
    return b.as_markup()


def kb_confirm():
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data="req:confirm")
    return b.as_markup()


def match_keyboard(offer_id: int, user):
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
        callback_data=f"match:contact:{offer_id}"
    )

    return b.as_markup()


# ================= CARD =================

def format_offer_text(off: Offer, user: User | None):
    if user and user.rating_count:
        rating_str = f"{round(user.rating_avg, 1)}⭐({user.rating_count})"
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
        f"✈️ {off.from_city} → {off.to_city}\n"
        f"📅 Дата: {off.trip_date.strftime('%d.%m')}\n"
        f"🎒 Место: {weight_map.get(str(off.capacity_band), off.capacity_band)}\n"
        f"🧳 Тип: {transport_map.get(str(off.transport_type), 'любой')}\n\n"
        f"👤 Рейтинг: {rating_str}"
    )

def format_request_text(req: Request, user: User | None, transport_type: str | None):
    try:
        # рейтинг
        if user and user.rating_count:
            rating_str = f"{round(user.rating_avg,1)}⭐({user.rating_count})"
        else:
            rating_str = "новый"

        # вес
        weight_map = {
            "lt1": "до 1 кг",
            "w1_3": "1–3 кг",
            "w3_5": "3–5 кг",
            "gt5": "5+ кг",
        }

        weight_str = weight_map.get(str(req.weight_band), "до 1 кг")

        # транспорт
        transport_map = {
            "plane": "самолет",
            "car": "машина",
            "any": "не важно",
        }

        transport_str = transport_map.get(str(transport_type), "не важно")

        # срок
        if req.delivery_date_from and req.delivery_date_to:
            days = (req.delivery_date_to - req.delivery_date_from).days

            if days <= 3:
                time_str = "ближайшие дни"
            elif days <= 14:
                time_str = "1–2 недели"
            else:
                time_str = "в течение месяца"
        else:
            time_str = "по договорённости"

        return (
            f"📦 {req.from_city} → {req.to_city}\n"
            f"📅 Нужно: {time_str}\n"
            f"🎒 Вес: {weight_str}\n"
            f"🧳 Перевозка: {transport_str}\n\n"
            f"👤 Рейтинг: {rating_str}"
        )

    except Exception as e:
        print("❌ format_request_text ERROR:", e)
        return "📦 Ошибка отображения заявки"


# ================= FLOW =================

@router.callback_query(F.data == "go:req")
async def start_request(cq: CallbackQuery, state: FSMContext):

    await state.clear()
    await state.set_state(RequestFSM.from_city)

    await cq.message.answer(
        "📦 Отправить посылку\n\n"
        "1/6 Откуда? Выберите из популярных направлений или введите свое:",
        reply_markup=kb_popular_cities_INLINE(),
    )

    await cq.answer()


# =========================================================
# INLINE POPULAR CITIES
# =========================================================

@router.callback_query(
    RequestFSM.from_city,
    F.data.startswith("city:")
)
async def select_from_city(
    cq: CallbackQuery,
    state: FSMContext
):

    city = cq.data.split(":")[1]

    await state.update_data(from_city=city)
    await state.set_state(RequestFSM.to_city)

    await cq.message.answer(
        "2/6 Куда? Выберите из популярных направлений или введите свое:",
        reply_markup=kb_popular_cities_INLINE(exclude=city),
    )

    await cq.answer()


@router.callback_query(
    RequestFSM.to_city,
    F.data.startswith("city:")
)
async def select_to_city(
    cq: CallbackQuery,
    state: FSMContext
):

    city = cq.data.split(":")[1]

    await state.update_data(to_city=city)
    await state.set_state(RequestFSM.category)

    await cq.message.answer(
        "3/6 Категория:",
        reply_markup=kb_category(),
    )

    await cq.answer()


# =========================================================
# MANUAL INPUT
# =========================================================

@router.message(RequestFSM.from_city)
async def step_from_city(m: Message, state: FSMContext):

    city = norm(m.text)

    if not city or len(city) < 3:
        return await m.answer("Введите корректный город")

    await state.update_data(from_city=city)
    await state.set_state(RequestFSM.to_city)

    await m.answer(
        "2/6 Куда?",
        reply_markup=kb_popular_cities_INLINE(exclude=city),
    )


@router.message(RequestFSM.to_city)
async def step_to_city(m: Message, state: FSMContext):

    city = norm(m.text)

    if not city or len(city) < 3:
        return await m.answer("Введите корректный город")

    await state.update_data(to_city=city)
    await state.set_state(RequestFSM.category)

    await m.answer(
        "3/6 Категория:",
        reply_markup=kb_category(),
    )


@router.callback_query(F.data.startswith("cat:"))
async def step_category(cq: CallbackQuery, state: FSMContext):

    mp = {
        "1": Category.clothes,
        "2": Category.cosmetics,
        "3": Category.docs,
        "4": Category.tech,
        "5": Category.other,
    }

    await state.update_data(
        category=mp[cq.data.split(":")[1]].value
    )

    await state.set_state(RequestFSM.transport_type)

    await cq.message.answer(
        "4/6 Какой транспорт?",
        reply_markup=kb_transport(),
    )

    await cq.answer()


@router.callback_query(F.data.startswith("t2:"))
async def step_transport(cq: CallbackQuery, state: FSMContext):
    await state.update_data(transport_type=cq.data.split(":")[1])

    # 🔥 потом вес
    await state.set_state(RequestFSM.weight_band)
    await cq.message.answer("5/6 Вес:", reply_markup=kb_weight())
    await cq.answer()


@router.callback_query(F.data.startswith("w:"))
async def step_weight(cq: CallbackQuery, state: FSMContext):
    mp = {
        "1": WeightBand.lt1,
        "2": WeightBand.w1_3,
        "3": WeightBand.w3_5,
        "4": WeightBand.gt5,
    }

    await state.update_data(weight_band=mp[cq.data.split(":")[1]].value)

    # 🔥 потом carry
    await state.set_state(RequestFSM.carry_type)
    await cq.message.answer("6/6 Как нужно перевезти?", reply_markup=kb_carry())
    await cq.answer()


@router.callback_query(F.data.startswith("c:"))
async def step_carry(cq: CallbackQuery, state: FSMContext):
    mp = {
        "1": "hand",
        "2": "luggage",
        "3": "any",
    }

    await state.update_data(carry_type=mp[cq.data.split(":")[1]])

    await state.set_state(RequestFSM.time_type)
    await cq.message.answer("Когда нужно?", reply_markup=kb_time())
    await cq.answer()


@router.callback_query(F.data.startswith("t:"))
async def step_time(cq: CallbackQuery, state: FSMContext):
    await state.update_data(time_type=cq.data.split(":")[1])

    await state.set_state(RequestFSM.confirm)

    await cq.message.answer(RULES_TEXT)
    await cq.message.answer("👇", reply_markup=kb_confirm())
    await cq.answer()


# ================= FINISH =================

@router.callback_query(F.data == "req:confirm")
async def finish_request(cq: CallbackQuery, state: FSMContext, session: AsyncSession):
    await cq.answer()

    # 🔥 1. ПРОВЕРКА STATE (защита от старых кнопок)
    current_state = await state.get_state()
    if current_state != RequestFSM.confirm.state:
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
        "category",
        "weight_band",
        "carry_type",
    ]

    missing = [f for f in required_fields if not data.get(f)]

    if missing:
        print("❌ FSM DATA MISSING:", missing, data)
        await state.clear()
        return await cq.message.answer(
            "❌ Данные потерялись. Пожалуйста создайте заявку заново /start"
        )

    # 🔥 3. ДАТЫ
    time_type = data.get("time_type", "soon")
    date_from, date_to = request_to_range(time_type)

    # 🔥 4. СОЗДАЁМ REQUEST

    if not cq.from_user.username:

        await cq.message.answer(
            "⚠️ Для использования PASO нужен username в Telegram.\n\n"
            "Откройте:\n"
            "Telegram → Настройки → Имя пользователя"
        )

        return

    req = Request(
        user_id=user.id,
        from_country="any",
        from_city=data.get("from_city"),
        to_country="any",
        to_city=data.get("to_city"),
        item_description="товар",
        category=data.get("category"),
        weight_band=data.get("weight_band"),
        carry_type=data.get("carry_type"),
        transport_type=data.get("transport_type", "any"),
        reward_mode="none",
        delivery_date_from=date_from,
        delivery_date_to=date_to,
        status=RowStatus.active,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    session.add(req)
    await session.commit()
    await session.refresh(req)

    await state.clear()

    # 🔥 5. MATCHING
    from app.matching import find_matches_for_request

    matches = await find_matches_for_request(
        session,
        req.id,
        window_days=0,
        top_n=3,
    )

    if not matches:
        await cq.message.answer("😔 Пока перевозчиков нет")
        return await cq.message.edit_reply_markup(reply_markup=None)

    await cq.message.answer(f"🔥 Найдено {len(matches)} перевозчиков:\n")

# 📦 ПОКАЗ ПОЛЬЗОВАТЕЛЮ
    for i, m in enumerate(matches):

        if i >= 3:
            await cq.message.answer("🔒 Есть ещё перевозчики — открой доступ")
            break

        off = await session.get(Offer, m.offer_id)
        off_user = await session.get(User, off.user_id)

        badge = "🔥 Лучший вариант\n\n" if i == 0 else ""

        await cq.message.answer(
            badge + format_offer_text(off, off_user),
            reply_markup=match_keyboard(m.id, user),
        )


    # 🔔 PUSH: уведомляем перевозчиков (без дублей)
    for m in matches:

        if getattr(m, "notified_carrier", False):
            continue

        off = await session.get(Offer, m.offer_id)
        off_user = await session.get(User, off.user_id)

        if not off_user or off_user.tg_user_id == cq.from_user.id:
            continue

        try:
            # сообщение 1
            await cq.bot.send_message(
                off_user.tg_user_id,
                "🔥 Появилась новая заявка под вашу поездку:\n",
            )

            # сообщение 2
            await cq.bot.send_message(
                off_user.tg_user_id,
                format_request_text(req, user, off.transport_type),
                reply_markup=match_keyboard(m.id, user),
            )

            # ✅ флаг
            m.notified_carrier = True

            print(f"📤 PUSH SENT (carrier): match_id={m.id}")

        except Exception as e:
            import traceback
            print("❌ PUSH ERROR:", e)
            traceback.print_exc()


    # 🔥 сохраняем изменения
        await session.commit()




