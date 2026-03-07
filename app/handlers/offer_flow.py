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


# ---------- RULES ----------

RULES_TEXT_OFFER = (
    "Перед подтверждением, пожалуйста, ознакомьтесь с правилами и примите их:\n\n"
    "• Вы перевозите товары добровольно и на свой риск\n"
    "• Убедитесь, что товар разрешён к перевозке и ввозу/вывозу\n"
    "• Не берите посылки «вслепую» — уточняйте состав/упаковку\n"
    "• Условия и вознаграждение обсуждаются напрямую в чате\n"
    "• PASO не участвует в сделке и не удерживает средства\n"
    "• Нарушение правил или жалобы ведут к удалению из сервиса"
)


def kb_confirm_offer():
    b = InlineKeyboardBuilder()
    b.button(text="✅ Принимаю правила", callback_data="off:confirm_rules")
    return b.as_markup()


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
        "✈️ Планирую поездку и могу взять\n\n"
        "1/5 Откуда вы выезжаете/вылетаете?\n"
        "Напишите город (например: Берлин)."
    )
    await cq.answer()


# ---------- steps ----------

@router.message(OfferFSM.from_city)
async def step_from_city(m: Message, state: FSMContext):
    city = norm(m.text)
    if not city:
        await m.answer("Введите город (например: Берлин).")
        return

    await state.update_data(from_city=city)
    await state.set_state(OfferFSM.to_city)
    await m.answer(
        "2/5 Куда едете?\n"
        "Напишите город (например: Москва)."
    )


@router.message(OfferFSM.to_city)
async def step_to_city(m: Message, state: FSMContext):
    city = norm(m.text)
    if not city:
        await m.answer("Введите город (например: Москва).")
        return

    await state.update_data(to_city=city)
    await state.set_state(OfferFSM.trip_date)
    await m.answer(
        "3/5 Когда поездка?\n\n"
        "1 — укажу точную дату (YYYY-MM-DD)\n"
        "2 — в течение 2 недель\n"
        "3 — в течение месяца\n"
        "4 — не уверен(а)\n\n"
        "Ответьте цифрой 1–4."
    )


@router.message(OfferFSM.trip_date)
async def step_trip_date(m: Message, state: FSMContext):
    txt = (m.text or "").strip()
    today = date.today()

    if txt == "1":
        await m.answer("Введите дату поездки в формате YYYY-MM-DD (например: 2026-03-01).")
        # остаёмся в OfferFSM.trip_date, но пометим что ждём дату
        await state.update_data(_await_exact_date=True)
        return

    # если ждём дату и пришла строка вида 2026-03-01
    data = await state.get_data()
    if data.get("_await_exact_date"):
        try:
            y, mm, dd = txt.split("-")
            d = date(int(y), int(mm), int(dd))
        except Exception:
            await m.answer("Не похоже на дату. Пример: 2026-03-01")
            return

        await state.update_data(trip_date=d.isoformat(), _await_exact_date=False)
        await state.set_state(OfferFSM.capacity_band)
        await m.answer(
            "4/5 Сколько свободного места есть?\n"
            "1 — до 1 кг\n"
            "2 — 1–3 кг\n"
            "3 — 3–5 кг\n"
            "4 — 5+ кг\n\n"
            "Ответьте цифрой 1–4."
        )
        return

    # варианты 2–4
    mp = {
        "2": today + timedelta(days=14),
        "3": today + timedelta(days=30),
        "4": today + timedelta(days=60),
    }
    d = mp.get(txt)
    if not d:
        await m.answer("Введите цифру 1–4.")
        return

    await state.update_data(trip_date=d.isoformat())
    await state.set_state(OfferFSM.capacity_band)
    await m.answer(
        "4/5 Сколько свободного места есть?\n"
        "1 — до 1 кг\n"
        "2 — 1–3 кг\n"
        "3 — 3–5 кг\n"
        "4 — 5+ кг\n\n"
        "Ответьте цифрой 1–4."
    )


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
        "5/5 Куда можно положить?\n"
        "1 — только ручная кладь\n"
        "2 — можно в багаж\n"
        "3 — без разницы\n\n"
        "Ответьте цифрой 1–3."
    )


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


@router.message(OfferFSM.confirm_rules)
async def confirm_need_button(m: Message):
    await m.answer("Нажмите кнопку ✅ «Принимаю правила».")


@router.callback_query(OfferFSM.confirm_rules, F.data == "off:confirm_rules")
async def finish_offer(cq: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_user(session, cq.from_user.id)
    if not user:
        await cq.message.answer("Ошибка пользователя. Нажмите /start.")
        await state.clear()
        await cq.answer()
        return

    data = await state.get_data()

    offer = Offer(
        user_id=user.id,
        from_country="unknown",
        from_city=data.get("from_city"),
        to_country="Russia",
        to_city=data.get("to_city"),
        trip_date=date.fromisoformat(data["trip_date"]),
        transit_country=None,
        transit_city=None,
        capacity_band=data["capacity_band"],
        baggage_type=data["baggage_type"],

        # ВАЖНО: чтобы не падало из-за NOT NULL constraint (по твоей ошибке)
        price_mode="discuss",
        price_amount=None,
        price_currency=None,

        status=RowStatus.active,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    session.add(offer)
    await session.commit()
    await session.refresh(offer)

    await state.clear()
    await cq.message.answer(
        "✅ Поездка сохранена. Теперь я смогу подбирать вам подходящие заявки.",
        reply_markup=kb_main(),
    )
    await cq.answer()
