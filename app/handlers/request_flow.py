from __future__ import annotations

from datetime import date, datetime, timedelta

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..enums import Category, WeightBand, CarryType
from ..models import User, Request
from ..utils import norm

router = Router()


# ---------- FSM ----------

class RequestFSM(StatesGroup):
    from_city = State()
    to_city = State()
    category = State()
    weight_band = State()
    carry_type = State()
    delivery_date_to = State()


# ---------- KEYBOARDS ----------

def kb_category():
    b = InlineKeyboardBuilder()
    b.button(text="👕 Одежда", callback_data="cat:1")
    b.button(text="💄 Косметика", callback_data="cat:2")
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
    b.button(text="👜 Ручная кладь", callback_data="c:1")
    b.button(text="🧳 Багаж", callback_data="c:2")
    b.button(text="👌 Не важно", callback_data="c:3")
    b.adjust(1)
    return b.as_markup()


def kb_date():
    b = InlineKeyboardBuilder()
    b.button(text="⚡ Ближайшие дни", callback_data="d:1")
    b.button(text="📅 1–2 недели", callback_data="d:2")
    b.button(text="🗓 В течение месяца", callback_data="d:3")
    b.button(text="🐢 Не срочно", callback_data="d:4")
    b.adjust(1)
    return b.as_markup()


def kb_confirm():
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data="req:confirm")
    return b.as_markup()


# ---------- helpers ----------

async def get_user(session: AsyncSession, tg_user_id: int):
    q = select(User).where(User.tg_user_id == tg_user_id)
    return (await session.execute(q)).scalar_one_or_none()


# ---------- START ----------

@router.callback_query(F.data == "go:req")
async def start_request(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(RequestFSM.from_city)

    await cq.message.answer("📦 Отправить товар\n\n1/5 Откуда?")
    await cq.answer()


# ---------- TEXT ----------

@router.message(RequestFSM.from_city)
async def step_from_city(m: Message, state: FSMContext):
    city = norm(m.text)
    if not city:
        await m.answer("Введите город")
        return

    await state.update_data(from_city=city)
    await state.set_state(RequestFSM.to_city)

    await m.answer("2/5 Куда?")


@router.message(RequestFSM.to_city)
async def step_to_city(m: Message, state: FSMContext):
    city = norm(m.text)
    if not city:
        await m.answer("Введите город")
        return

    await state.update_data(to_city=city)
    await state.set_state(RequestFSM.category)

    await m.answer("3/5 Категория:", reply_markup=kb_category())


# ---------- CATEGORY ----------

@router.callback_query(F.data.startswith("cat:"))
async def step_category(cq: CallbackQuery, state: FSMContext):
    print("🔥 CATEGORY CLICK")

    val = cq.data.split(":")[1]

    mp = {
        "1": Category.clothes,
        "2": Category.cosmetics,
        "3": Category.docs,
        "4": Category.tech,
        "5": Category.other,
    }

    await state.update_data(category=mp[val].value)
    await state.set_state(RequestFSM.weight_band)

    await cq.message.answer("4/5 Вес:", reply_markup=kb_weight())
    await cq.answer()


# ---------- WEIGHT ----------

@router.callback_query(F.data.startswith("w:"))
async def step_weight(cq: CallbackQuery, state: FSMContext):
    print("🔥 WEIGHT CLICK")

    val = cq.data.split(":")[1]

    mp = {
        "1": WeightBand.lt1,
        "2": WeightBand.w1_3,
        "3": WeightBand.w3_5,
        "4": WeightBand.gt5,
    }

    await state.update_data(weight_band=mp[val].value)
    await state.set_state(RequestFSM.carry_type)

    await cq.message.answer("Тип перевозки:", reply_markup=kb_carry())
    await cq.answer()


# ---------- CARRY ----------

@router.callback_query(F.data.startswith("c:"))
async def step_carry(cq: CallbackQuery, state: FSMContext):
    print("🔥 CARRY CLICK")

    val = cq.data.split(":")[1]

    mp = {
        "1": CarryType.hand_only,
        "2": CarryType.luggage_ok,
        "3": CarryType.any,
    }

    await state.update_data(carry_type=mp[val].value)
    await state.set_state(RequestFSM.delivery_date_to)

    await cq.message.answer("5/5 Когда?", reply_markup=kb_date())
    await cq.answer()


# ---------- DATE ----------

@router.callback_query(F.data.startswith("d:"))
async def step_date(cq: CallbackQuery, state: FSMContext):
    print("🔥 DATE CLICK")

    today = date.today()

    mp = {
        "1": today + timedelta(days=3),
        "2": today + timedelta(days=14),
        "3": today + timedelta(days=30),
        "4": today + timedelta(days=90),
    }

    val = cq.data.split(":")[1]

    await state.update_data(delivery_date_to=mp[val].isoformat())

    await cq.message.answer("📋 Правила", reply_markup=kb_confirm())
    await cq.answer()


# ---------- CONFIRM ----------

@router.callback_query(F.data == "req:confirm")
async def finish_request(cq: CallbackQuery, state: FSMContext, session: AsyncSession):

    print("🔥 CONFIRM CLICKED")

    user = await get_user(session, cq.from_user.id)
    data = await state.get_data()

    if not data:
        await cq.message.answer("Ошибка: нет данных")
        return

    req = Request(
        user_id=user.id,
        from_city=data["from_city"],
        to_city=data["to_city"],
        category=data["category"],
        weight_band=data["weight_band"],
        carry_type=data["carry_type"],
        delivery_date_to=date.fromisoformat(data["delivery_date_to"]),
        status="draft",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    session.add(req)
    await session.commit()

    await state.clear()

    await cq.message.answer("✅ Заявка создана")
    await cq.answer()

