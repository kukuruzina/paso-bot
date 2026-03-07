from __future__ import annotations

from datetime import date, datetime, timedelta

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import Category, WeightBand, CarryType, RewardMode, RowStatus
from ..keyboards import kb_main, kb_request_suggest
from ..matching import find_matches_for_request
from ..models import User, Request, Offer
from ..utils import norm
from ..config import load_config

router = Router()


# ---------- FSM ----------

class RequestFSM(StatesGroup):
    from_city = State()
    to_city = State()
    category = State()
    weight_band = State()
    carry_type = State()
    delivery_date_to = State()
    reward_mode = State()
    reward_amount = State()
    reward_currency = State()
    confirm_rules = State()


# ---------- RULES ----------

RULES_TEXT_REQUEST = (
    "Перед подтверждением, пожалуйста, ознакомьтесь с правилами и примите их:\n\n"
    "• Вы перевозите товары добровольно и на свой риск\n"
    "• Убедитесь, что товар разрешён к перевозке и ввозу/вывозу\n"
    "• Не берите посылки «вслепую» — уточняйте состав/упаковку\n"
    "• Условия и вознаграждение обсуждаются напрямую в чате\n"
    "• PASO не участвует в сделке и не удерживает средства\n"
    "• Нарушение правил или жалобы ведут к удалению из сервиса"
)


def kb_confirm_rules():
    b = InlineKeyboardBuilder()
    b.button(text="✅ Принимаю правила", callback_data="req:confirm_rules")
    b.adjust(1)
    return b.as_markup()


def kb_unlock():
    b = InlineKeyboardBuilder()
    b.button(text="🔓 Открыть доступ (подписка)", callback_data="go:subscribe")
    b.adjust(1)
    return b.as_markup()


# ---------- helpers ----------

async def get_user(session: AsyncSession, tg_user_id: int) -> User | None:
    q = select(User).where(User.tg_user_id == tg_user_id)
    return (await session.execute(q)).scalar_one_or_none()


def format_baggage(value: str) -> str:
    mp = {
        CarryType.hand_only: "только ручная кладь",
        CarryType.luggage_ok: "можно в багаж",
        CarryType.any: "ручная кладь или багаж",
    }
    return mp.get(value, value)


def format_weight_band(value: str) -> str:
    mp = {
        WeightBand.lt1: "до 1 кг",
        WeightBand.w1_3: "1–3 кг",
        WeightBand.w3_5: "3–5 кг",
        WeightBand.gt5: "5+ кг",
    }
    return mp.get(value, value)


# ---------- entry ----------

@router.callback_query(F.data == "go:req")
async def start_request(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(RequestFSM.from_city)
    await cq.message.answer(
        "📦 Отправить товар\n\n"
        "1/6 Откуда отправляем?\n"
        "Напишите город (например: Берлин)."
    )
    await cq.answer()


# ---------- steps ----------

@router.message(RequestFSM.from_city)
async def step_from_city(m: Message, state: FSMContext):
    city = norm(m.text)
    if not city:
        await m.answer("Введите город (например: Берлин).")
        return

    await state.update_data(from_city=city)
    await state.set_state(RequestFSM.to_city)
    await m.answer(
        "2/6 Куда доставить?\n"
        "Напишите город (например: Москва)."
    )


@router.message(RequestFSM.to_city)
async def step_to_city(m: Message, state: FSMContext):
    city = norm(m.text)
    if not city:
        await m.answer("Введите город (например: Москва).")
        return

    await state.update_data(to_city=city)
    await state.set_state(RequestFSM.category)
    await m.answer(
        "3/6 Категория:\n"
        "1 — документы\n"
        "2 — одежда / обувь\n"
        "3 — косметика\n"
        "4 — техника\n"
        "5 — другое\n\n"
        "Ответьте цифрой 1–5."
    )


@router.message(RequestFSM.category)
async def step_category(m: Message, state: FSMContext):
    mp = {
        "1": Category.docs,
        "2": Category.clothes,
        "3": Category.cosmetics,
        "4": Category.tech,
        "5": Category.other,
    }
    cat = mp.get((m.text or "").strip())
    if not cat:
        await m.answer("Введите цифру 1–5.")
        return

    await state.update_data(category=cat.value)
    await state.set_state(RequestFSM.weight_band)
    await m.answer(
        "4/6 Вес:\n"
        "1 — до 1 кг\n"
        "2 — 1–3 кг\n"
        "3 — 3–5 кг\n"
        "4 — 5+ кг\n\n"
        "Ответьте цифрой 1–4."
    )


@router.message(RequestFSM.weight_band)
async def step_weight(m: Message, state: FSMContext):
    mp = {
        "1": WeightBand.lt1,
        "2": WeightBand.w1_3,
        "3": WeightBand.w3_5,
        "4": WeightBand.gt5,
    }
    wb = mp.get((m.text or "").strip())
    if not wb:
        await m.answer("Введите цифру 1–4.")
        return

    await state.update_data(weight_band=wb.value)
    await state.set_state(RequestFSM.carry_type)
    await m.answer(
        "5/6 Тип перевозки:\n"
        "1 — только ручная кладь\n"
        "2 — можно в багаж\n"
        "3 — без разницы\n\n"
        "Ответьте цифрой 1–3."
    )


@router.message(RequestFSM.carry_type)
async def step_carry(m: Message, state: FSMContext):
    mp = {
        "1": CarryType.hand_only,
        "2": CarryType.luggage_ok,
        "3": CarryType.any,
    }
    ct = mp.get((m.text or "").strip())
    if not ct:
        await m.answer("Введите цифру 1–3.")
        return

    await state.update_data(carry_type=ct.value)
    await state.set_state(RequestFSM.delivery_date_to)
    await m.answer(
        "6/6 Когда нужно доставить?\n\n"
        "1 — как можно скорее\n"
        "2 — в течение 2 недель\n"
        "3 — в течение месяца\n"
        "4 — не срочно\n\n"
        "Ответьте цифрой 1–4."
    )


@router.message(RequestFSM.delivery_date_to)
async def step_date(m: Message, state: FSMContext):
    today = date.today()
    mp = {
        "1": today + timedelta(days=3),
        "2": today + timedelta(days=14),
        "3": today + timedelta(days=30),
        "4": today + timedelta(days=90),
    }
    d = mp.get((m.text or "").strip())
    if not d:
        await m.answer("Введите цифру 1–4.")
        return

    await state.update_data(delivery_date_to=d.isoformat())
    await state.set_state(RequestFSM.reward_mode)
    await m.answer(
        "Вознаграждение:\n"
        "1 — обсудить в чате\n"
        "2 — фикс\n"
        "3 — за кг\n\n"
        "Ответьте цифрой 1–3."
    )


@router.message(RequestFSM.reward_mode)
async def step_reward_mode(m: Message, state: FSMContext):
    mp = {
        "1": RewardMode.discuss,
        "2": RewardMode.fixed,
        "3": RewardMode.per_kg,
    }
    rm = mp.get((m.text or "").strip())
    if not rm:
        await m.answer("Введите 1–3.")
        return

    await state.update_data(reward_mode=rm.value)

    if rm == RewardMode.discuss:
        await state.update_data(reward_amount=None, reward_currency=None)
        await state.set_state(RequestFSM.confirm_rules)
        await m.answer(RULES_TEXT_REQUEST, reply_markup=kb_confirm_rules())
    else:
        await state.set_state(RequestFSM.reward_amount)
        await m.answer("Введите сумму (например: 30).")


@router.message(RequestFSM.reward_amount)
async def step_reward_amount(m: Message, state: FSMContext):
    try:
        amt = float((m.text or "").replace(",", "."))
        if amt <= 0:
            raise ValueError
    except Exception:
        await m.answer("Введите число больше 0.")
        return

    await state.update_data(reward_amount=amt)
    await state.set_state(RequestFSM.reward_currency)
    await m.answer(
        "Валюта:\n"
        "1 — RUB\n"
        "2 — EUR\n"
        "3 — USD\n"
        "4 — USDT\n\n"
        "Ответьте цифрой 1–4."
    )


@router.message(RequestFSM.reward_currency)
async def step_reward_currency(m: Message, state: FSMContext):
    mp = {"1": "RUB", "2": "EUR", "3": "USD", "4": "USDT"}
    cur = mp.get((m.text or "").strip())
    if not cur:
        await m.answer("Введите цифру 1–4.")
        return

    await state.update_data(reward_currency=cur)
    await state.set_state(RequestFSM.confirm_rules)
    await m.answer(RULES_TEXT_REQUEST, reply_markup=kb_confirm_rules())


@router.message(RequestFSM.confirm_rules)
async def confirm_rules_need_button(m: Message):
    await m.answer("Нажмите кнопку ✅ «Принимаю правила».")


@router.callback_query(RequestFSM.confirm_rules, F.data == "req:confirm_rules")
async def finish_request(cq: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_user(session, cq.from_user.id)
    if not user:
        await cq.message.answer("Ошибка пользователя. Нажмите /start.")
        await state.clear()
        await cq.answer()
        return

    data = await state.get_data()

    req = Request(
        user_id=user.id,
        from_country="unknown",
        from_city=data.get("from_city"),
        to_country="Russia",
        to_city=data.get("to_city"),
        item_description="обсудим в чате",
        category=data["category"],
        weight_band=data["weight_band"],
        carry_type=data["carry_type"],
        delivery_date_from=None,
        delivery_date_to=date.fromisoformat(data["delivery_date_to"]),
        reward_mode=data["reward_mode"],
        reward_amount=data.get("reward_amount"),
        reward_currency=data.get("reward_currency"),
        transit_allowed=True,
        status=RowStatus.active,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        # если поля нет в модели — можно убрать, но если добавила requires_premium в Request, оставь:
        requires_premium=data.get("requires_premium", False),
    )

    session.add(req)
    await session.commit()
    await session.refresh(req)

    await state.clear()
    await cq.message.answer("✅ Заявка создана. Ищу совпадения…")
    await cq.answer()

    cfg = load_config()

    matches = await find_matches_for_request(
        session=session,
        request_id=req.id,
        window_days=cfg.match_window_days,
        top_n=cfg.top_matches,
    )

    if not matches:
        await cq.message.answer(
            "Пока нет подходящих путешественников.\n"
            "Заявка сохранена.",
            reply_markup=kb_main(),
        )
        return

    # PAYWALL после найденных перевозчиков
    await cq.message.answer(
        "✅ Нашла подходящих перевозчиков!\n\n"
        "Чтобы начать чат и подтвердить сделку, нужна подписка.\n"
        "Оформить: /subscribe\n\n"
        "Выберите перевозчика ниже 👇",
        reply_markup=kb_unlock(),
    )

    for mt in matches:
        offer = await session.get(Offer, mt.offer_id)
        if not offer:
            continue

        offer_user = await session.get(User, offer.user_id)

        rating = "—"
        if offer_user and offer_user.rating_count:
            rating = f"{offer_user.rating_avg:.2f} ({offer_user.rating_count})"

        premium_badge = "👑 PREMIUM" if (offer_user and offer_user.is_premium_carrier) else ""

        txt = (
            "✈️ Путешественник\n\n"
            f"{offer.from_city} → {offer.to_city}\n"
            f"Дата поездки: {offer.trip_date}\n"
            f"Тип перевозки: {format_baggage(offer.baggage_type)}\n"
            f"Свободно: {format_weight_band(offer.capacity_band)}\n"
            f"⭐️ Рейтинг: {rating}\n"
            f"{premium_badge}"
        ).strip()

        await cq.message.answer(
            txt,
            reply_markup=kb_request_suggest(mt.id),
        )