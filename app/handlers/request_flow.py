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

RULES_TEXT = (
    "📋 Правила:\n\n"
    "• Перевозка под вашу ответственность\n"
    "• Запрещённые вещи нельзя\n"
    "• Всё обсуждается в чате"
)

class RequestFSM(StatesGroup):
    from_city = State()
    to_city = State()
    category = State()
    weight_band = State()
    carry_type = State()
    time_type = State()


def request_to_range(time_type: str):
    today = date.today()

    if time_type == "soon":
        return today, today + timedelta(days=7)
    elif time_type == "week_1_2":
        return today + timedelta(days=7), today + timedelta(days=14)
    elif time_type == "month":
        return today, today + timedelta(days=30)

    return today, today + timedelta(days=7)


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
    b.button(text="👜 Ручная кладь", callback_data="c:1")
    b.button(text="🧳 Багаж", callback_data="c:2")
    b.button(text="👌 Не важно", callback_data="c:3")
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


async def get_user(session: AsyncSession, tg_user_id: int):
    q = select(User).where(User.tg_user_id == tg_user_id)
    return (await session.execute(q)).scalar_one_or_none()


@router.callback_query(F.data == "go:req")
async def start_request(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(RequestFSM.from_city)
    await cq.message.answer("📦 Отправить товар\n\n1/5 Откуда?")
    await cq.answer()


@router.message(RequestFSM.from_city)
async def step_from_city(m: Message, state: FSMContext):
    city = norm(m.text)
    if not city:
        return await m.answer("Введите город")

    await state.update_data(from_city=city)
    await state.set_state(RequestFSM.to_city)
    await m.answer("2/5 Куда?")


@router.message(RequestFSM.to_city)
async def step_to_city(m: Message, state: FSMContext):
    city = norm(m.text)
    if not city:
        return await m.answer("Введите город")

    await state.update_data(to_city=city)
    await state.set_state(RequestFSM.category)
    await m.answer("3/5 Категория:", reply_markup=kb_category())


@router.callback_query(F.data.startswith("cat:"))
async def step_category(cq: CallbackQuery, state: FSMContext):
    mp = {
        "1": Category.clothes,
        "2": Category.cosmetics,
        "3": Category.docs,
        "4": Category.tech,
        "5": Category.other,
    }

    await state.update_data(category=mp[cq.data.split(":")[1]].value)
    await state.set_state(RequestFSM.weight_band)

    await cq.message.answer("4/5 Вес:", reply_markup=kb_weight())
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
    await state.set_state(RequestFSM.carry_type)

    await cq.message.answer("Тип перевозки:", reply_markup=kb_carry())
    await cq.answer()


@router.callback_query(F.data.startswith("c:"))
async def step_carry(cq: CallbackQuery, state: FSMContext):
    mp = {
        "1": CarryType.hand_only,
        "2": CarryType.luggage_ok,
        "3": CarryType.any,
    }

    await state.update_data(carry_type=mp[cq.data.split(":")[1]].value)
    await state.set_state(RequestFSM.time_type)

    await cq.message.answer("5/5 Когда нужно?", reply_markup=kb_time())
    await cq.answer()


@router.callback_query(F.data.startswith("t:"))
async def step_time(cq: CallbackQuery, state: FSMContext):
    await state.update_data(time_type=cq.data.split(":")[1])

    await cq.message.answer(RULES_TEXT)
    await cq.message.answer("👇", reply_markup=kb_confirm())
    await cq.answer()


@router.callback_query(F.data == "req:confirm")
async def finish_request(cq: CallbackQuery, state: FSMContext, session: AsyncSession):
    await cq.answer()

    user = await get_user(session, cq.from_user.id)
    data = await state.get_data()

    date_from, date_to = request_to_range(data["time_type"])

    req = Request(
        user_id=user.id,
        from_city=data["from_city"],
        to_city=data["to_city"],
        category=data["category"],
        weight_band=data["weight_band"],
        carry_type=data["carry_type"],
        date_from=date_from,
        date_to=date_to,
        status="active",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    session.add(req)
    await session.commit()

    await state.clear()
    await cq.message.answer("✅ Заявка создана. Ищем совпадения...")

