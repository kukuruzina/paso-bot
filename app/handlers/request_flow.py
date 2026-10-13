from datetime import date, datetime, timedelta

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from ..enums import Category, WeightBand, CarryType
from ..models import User, Request
from ..utils import norm

router = Router()


class RequestFSM(StatesGroup):
    from_city = State()
    to_city = State()
    category = State()
    weight_band = State()
    carry_type = State()
    delivery_date_to = State()


# ---------- RULES ----------

RULES_TEXT = (
    "📋 Правила:\n\n"
    "• Отправка на ваш риск\n"
    "• Проверяйте содержимое\n"
    "• Запрещённые вещи нельзя\n"
    "• Всё обсуждается в чате\n"
)


# ---------- KB ----------

def kb_category():
    b = InlineKeyboardBuilder()
    b.button(text="👕 Одежда", callback_data="r_cat:1")
    b.button(text="💄 Косметика", callback_data="r_cat:2")
    b.button(text="📄 Документы", callback_data="r_cat:3")
    b.button(text="📱 Техника", callback_data="r_cat:4")
    b.button(text="📦 Другое", callback_data="r_cat:5")
    b.adjust(1)
    return b.as_markup()


def kb_weight():
    b = InlineKeyboardBuilder()
    b.button(text="до 1 кг", callback_data="r_w:1")
    b.button(text="1–3 кг", callback_data="r_w:2")
    b.button(text="3–5 кг", callback_data="r_w:3")
    b.button(text="5+ кг", callback_data="r_w:4")
    b.adjust(2)
    return b.as_markup()


def kb_carry():
    b = InlineKeyboardBuilder()
    b.button(text="👜 Ручная кладь", callback_data="r_c:1")
    b.button(text="🧳 Багаж", callback_data="r_c:2")
    b.button(text="👌 Не важно", callback_data="r_c:3")
    b.adjust(1)
    return b.as_markup()


def kb_date():
    b = InlineKeyboardBuilder()
    b.button(text="⚡ Ближайшие дни", callback_data="r_d:1")
    b.button(text="📅 1–2 недели", callback_data="r_d:2")
    b.button(text="🗓 В течение месяца", callback_data="r_d:3")
    b.button(text="🐢 Не срочно", callback_data="r_d:4")
    b.adjust(1)
    return b.as_markup()


def kb_confirm():
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data="req:confirm")
    return b.as_markup()


async def get_user(session, tg_user_id):
    q = select(User).where(User.tg_user_id == tg_user_id)
    return (await session.execute(q)).scalar_one_or_none()


# ---------- FLOW ----------

@router.callback_query(F.data == "go:req")
async def start(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await state.clear()
    await state.set_state(RequestFSM.from_city)
    await cq.message.answer("📦 1/5 Откуда?")


@router.message(RequestFSM.from_city)
async def step1(m: Message, state: FSMContext):
    await state.update_data(from_city=norm(m.text))
    await state.set_state(RequestFSM.to_city)
    await m.answer("2/5 Куда?")


@router.message(RequestFSM.to_city)
async def step2(m: Message, state: FSMContext):
    await state.update_data(to_city=norm(m.text))
    await state.set_state(RequestFSM.category)
    await m.answer("3/5 Категория:", reply_markup=kb_category())


@router.callback_query(RequestFSM.category, F.data.startswith("r_cat:"))
async def step3(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await state.update_data(category=cq.data.split(":")[1])
    await state.set_state(RequestFSM.weight_band)
    await cq.message.answer("4/5 Вес:", reply_markup=kb_weight())


@router.callback_query(RequestFSM.weight_band, F.data.startswith("r_w:"))
async def step4(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await state.update_data(weight_band=cq.data.split(":")[1])
    await state.set_state(RequestFSM.carry_type)
    await cq.message.answer("Тип:", reply_markup=kb_carry())


@router.callback_query(RequestFSM.carry_type, F.data.startswith("r_c:"))
async def step5(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await state.update_data(carry_type=cq.data.split(":")[1])
    await state.set_state(RequestFSM.delivery_date_to)
    await cq.message.answer("5/5 Когда нужно:", reply_markup=kb_date())


@router.callback_query(RequestFSM.delivery_date_to, F.data.startswith("r_d:"))
async def step6(cq: CallbackQuery, state: FSMContext):
    await cq.answer()

    today = date.today()
    mp = {"1": 3, "2": 14, "3": 30, "4": 90}

    key = cq.data.split(":")[1]
    d = today + timedelta(days=mp[key])

    await state.update_data(delivery_date_to=d.isoformat())

    # 🔥 ВАЖНО: теперь полноценные правила
    await cq.message.answer(RULES_TEXT, reply_markup=kb_confirm())


@router.callback_query(F.data == "req:confirm")
async def finish(cq: CallbackQuery, state: FSMContext, **kwargs):
    await cq.answer()

    session = kwargs.get("session")
    if not session:
        await cq.message.answer("Ошибка: нет соединения с БД")
        return

    user = await get_user(session, cq.from_user.id)
    if not user:
        await cq.message.answer("Пользователь не найден")
        return

    data = await state.get_data()
    if not data:
        await cq.message.answer("Ошибка: данные потеряны")
        return

    req = Request(
        user_id=user.id,
        from_country="any",
        from_city=data.get("from_city") or "",
        to_country="any",
        to_city=data.get("to_city") or "",
        category=str(data.get("category")),
        weight_band=str(data.get("weight_band")),
        carry_type=str(data.get("carry_type")),
        delivery_date_to=date.fromisoformat(data.get("delivery_date_to")),
        reward_mode="discuss",
        status="active",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    session.add(req)
    await session.commit()

    await state.clear()

    await cq.message.answer("✅ Заявка создана")

