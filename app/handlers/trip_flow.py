from __future__ import annotations

import logging

from datetime import datetime, date, timedelta

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import CallbackQuery, Message

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import User, TripRequest, TripOffer, TripMatch, TripMatchContactOpen
from app.keyboards import kb_trips, kb_trip_back, kb_trip_cities, kb_trip_match, kb_trip_departure_time, kb_trip_offer_seats, kb_trip_price_mode, kb_trip_currency
from app.services.paywall import can_access_contacts, spend_contact_no_commit

from app.trip_matching import (
    find_matches_for_trip_request,
    find_matches_for_trip_offer,
)

router = Router()

logger = logging.getLogger(__name__)

# =========================================================
# НОРМАЛИЗАЦИЯ ГОРОДОВ
# =========================================================

def normalize_city(value: str) -> str:
    """Убирает флаг страны из начала города, сохраняя само название."""
    value = (value or "").strip()
    if value and len(value) >= 2 and ord(value[0]) > 0x1F000:
        parts = value.split(maxsplit=1)
        if len(parts) == 2:
            value = parts[1].strip()
    return value


# =========================================================
# FSM — ИЩУ ПОЕЗДКУ
# =========================================================

class TripRequestStates(StatesGroup):
    from_city = State()
    to_city = State()
    date_from = State()
    date_to = State()
    passengers = State()
    comment = State()


# =========================================================
# FSM — ПРЕДЛАГАЮ ПОЕЗДКУ
# =========================================================

class TripOfferStates(StatesGroup):
    from_city = State()
    to_city = State()
    trip_date = State()
    departure_time = State()
    seats = State()
    price_mode = State()
    price_amount = State()
    price_currency = State()
    comment = State()

# =========================================================
# ВЫБОР ГОРОДОВ ДЛЯ ПОЕЗДОК
# =========================================================

@router.callback_query(
    TripRequestStates.from_city,
    F.data.startswith("trip_city:")
)
async def trip_request_from_city_callback(
    callback: CallbackQuery,
    state: FSMContext,
):
    city = callback.data.split(":", 1)[1]

    if city == "other":
        await callback.message.edit_text(
            "🔍 Ищу поездку\n\n"
            "Введите город отправления:"
        )
        await callback.answer()
        return

    await state.update_data(from_city=normalize_city(city))
    await state.set_state(TripRequestStates.to_city)

    await callback.message.edit_text(
        "🔍 Ищу поездку\n\n"
        "В какой город вы хотите приехать?",
        reply_markup=kb_trip_cities(exclude=city),
    )
    await callback.answer()


@router.message(TripRequestStates.from_city)
async def trip_request_from_city_manual(
    message: Message,
    state: FSMContext,
):
    from_city = (message.text or "").strip()

    if not from_city:
        await message.answer("Введите город отправления.")
        return

    await state.update_data(from_city=normalize_city(from_city))
    await state.set_state(TripRequestStates.to_city)

    await message.answer(
        "🔍 Ищу поездку\n\n"
        "В какой город вы хотите приехать?",
        reply_markup=kb_trip_cities(exclude=from_city),
    )


@router.callback_query(
    TripRequestStates.to_city,
    F.data.startswith("trip_city:")
)
async def trip_request_to_city_callback(
    callback: CallbackQuery,
    state: FSMContext,
):
    city = callback.data.split(":", 1)[1]

    if city == "other":
        await callback.message.edit_text(
            "🔍 Ищу поездку\n\n"
            "Введите город назначения:"
        )
        await callback.answer()
        return

    data = await state.get_data()
    from_city = data.get("from_city")

    if from_city and from_city.casefold() == city.casefold():
        await callback.answer(
            "Города отправления и назначения должны отличаться.",
            show_alert=True,
        )
        return

    await state.update_data(to_city=normalize_city(city))
    await state.set_state(TripRequestStates.date_from)

    await callback.message.edit_text(
        "📅 На какую дату вы ищете поездку?",
        reply_markup=kb_trip_request_date_from_current_week(),
    )
    await callback.answer()


@router.message(TripRequestStates.to_city)
async def trip_request_to_city_manual(
    message: Message,
    state: FSMContext,
):
    to_city = (message.text or "").strip()

    if not to_city:
        await message.answer("Введите город назначения.")
        return

    data = await state.get_data()
    from_city = data.get("from_city")

    if from_city and from_city.casefold() == to_city.casefold():
        await message.answer(
            "Город отправления и назначения должны отличаться.\n"
            "Введите город назначения ещё раз."
        )
        return

    await state.update_data(to_city=normalize_city(to_city))
    await state.set_state(TripRequestStates.date_from)

    await message.answer(
        "📅 На какую дату вы ищете поездку?",
        reply_markup=kb_trip_request_date_from_current_week(),
    )


@router.callback_query(
    TripOfferStates.from_city,
    F.data.startswith("trip_city:")
)
async def trip_offer_from_city_callback(
    callback: CallbackQuery,
    state: FSMContext,
):
    city = callback.data.split(":", 1)[1]

    if city == "other":
        await callback.message.edit_text(
            "🚗 Предлагаю поездку\n\n"
            "Введите город отправления:"
        )
        await callback.answer()
        return

    await state.update_data(from_city=normalize_city(city))
    await state.set_state(TripOfferStates.to_city)

    await callback.message.edit_text(
        "🚗 Предлагаю поездку\n\n"
        "В какой город вы едете?",
        reply_markup=kb_trip_cities(exclude=city),
    )
    await callback.answer()


@router.message(TripOfferStates.from_city)
async def trip_offer_from_city_manual(
    message: Message,
    state: FSMContext,
):
    from_city = (message.text or "").strip()

    if not from_city:
        await message.answer("Введите город отправления.")
        return

    await state.update_data(from_city=normalize_city(from_city))
    await state.set_state(TripOfferStates.to_city)

    await message.answer(
        "🚗 Предлагаю поездку\n\n"
        "В какой город вы едете?",
        reply_markup=kb_trip_cities(exclude=from_city),
    )


@router.callback_query(
    TripOfferStates.to_city,
    F.data.startswith("trip_city:")
)
async def trip_offer_to_city_callback(
    callback: CallbackQuery,
    state: FSMContext,
):
    city = callback.data.split(":", 1)[1]

    if city == "other":
        await callback.message.edit_text(
            "🚗 Предлагаю поездку\n\n"
            "Введите город назначения:"
        )
        await callback.answer()
        return

    data = await state.get_data()
    from_city = data.get("from_city")

    if from_city and from_city.casefold() == city.casefold():
        await callback.answer(
            "Города отправления и назначения должны отличаться.",
            show_alert=True,
        )
        return

    await state.update_data(to_city=normalize_city(city))
    await state.set_state(TripOfferStates.trip_date)

    await callback.message.edit_text(
        "📅 На какую дату запланирована поездка?",
        reply_markup=kb_trip_calendar_current_week(),
    )
    await callback.answer()


@router.message(TripOfferStates.to_city)
async def trip_offer_to_city_manual(
    message: Message,
    state: FSMContext,
):
    to_city = (message.text or "").strip()

    if not to_city:
        await message.answer("Введите город назначения.")
        return

    data = await state.get_data()
    from_city = data.get("from_city")

    if from_city and from_city.casefold() == to_city.casefold():
        await message.answer(
            "Город отправления и назначения должны отличаться.\n"
            "Введите город назначения ещё раз."
        )
        return

    await state.update_data(to_city=normalize_city(to_city))
    await state.set_state(TripOfferStates.trip_date)
    await message.answer(
        "📅 На какую дату запланирована поездка?",
        reply_markup=kb_trip_calendar_current_week(),
    )




# =========================================================
# TRIP CALENDAR
# =========================================================

def kb_trip_calendar_current_week(
    min_date: date | None = None,
):
    b = InlineKeyboardBuilder()
    today = date.today()

    days_until_sunday = 6 - today.weekday()

    for i in range(days_until_sunday + 1):
        d = today + timedelta(days=i)

        if min_date and d < min_date:
            continue

        b.button(
            text=d.strftime("%d.%m"),
            callback_data=f"t_date:{d.isoformat()}",
        )

    b.button(
        text="➡️ Следующая неделя",
        callback_data="t_cal:next",
    )

    b.button(
        text="🐢 В течение месяца",
        callback_data="t_date:month",
    )

    b.button(
        text="✏️ Другая дата",
        callback_data="t_date:other",
    )

    b.adjust(3)
    return b.as_markup()


def kb_trip_calendar_next_week(
    min_date: date | None = None,
):
    b = InlineKeyboardBuilder()
    today = date.today()

    days_to_monday = (7 - today.weekday()) % 7 or 7
    start = today + timedelta(days=days_to_monday)

    for i in range(7):
        d = start + timedelta(days=i)

        if min_date and d < min_date:
            continue

        b.button(
            text=d.strftime("%d.%m"),
            callback_data=f"t_date:{d.isoformat()}",
        )

    b.button(
        text="⬅️ Назад",
        callback_data="t_cal:back",
    )

    b.button(
        text="🐢 В течение месяца",
        callback_data="t_date:month",
    )

    b.button(
        text="✏️ Другая дата",
        callback_data="t_date:other",
    )

    b.adjust(3)
    return b.as_markup()


def kb_trip_request_date_from_current_week():
    b = InlineKeyboardBuilder()
    today = date.today()
    days_until_sunday = 6 - today.weekday()

    for i in range(days_until_sunday + 1):
        d = today + timedelta(days=i)
        b.button(
            text=d.strftime("%d.%m"),
            callback_data=f"t_req_from:{d.isoformat()}",
        )

    b.button(
        text="➡️ Следующая неделя",
        callback_data="t_req_from_cal:next",
    )
    b.button(
        text="✏️ Другая дата",
        callback_data="t_req_from:other",
    )
    b.adjust(3)
    return b.as_markup()


def kb_trip_request_date_from_next_week():
    b = InlineKeyboardBuilder()
    today = date.today()
    days_to_monday = (7 - today.weekday()) % 7 or 7
    start = today + timedelta(days=days_to_monday)

    for i in range(7):
        d = start + timedelta(days=i)
        b.button(
            text=d.strftime("%d.%m"),
            callback_data=f"t_req_from:{d.isoformat()}",
        )

    b.button(
        text="⬅️ Назад",
        callback_data="t_req_from_cal:back",
    )
    b.button(
        text="✏️ Другая дата",
        callback_data="t_req_from:other",
    )
    b.adjust(3)
    return b.as_markup()


def kb_trip_request_date_to(
    min_date: date,
):
    b = InlineKeyboardBuilder()
    today = date.today()

    days_until_sunday = 6 - today.weekday()

    for i in range(days_until_sunday + 1):
        d = today + timedelta(days=i)

        if d < min_date:
            continue

        b.button(
            text=d.strftime("%d.%m"),
            callback_data=f"t_req_to:{d.isoformat()}",
        )

    b.button(
        text="📌 Только эта дата",
        callback_data="t_req_to:same",
    )

    b.button(
        text="➡️ Следующая неделя",
        callback_data="t_req_cal:next",
    )

    b.button(
        text="✏️ Другая дата",
        callback_data="t_req_to:other",
    )

    b.adjust(3)
    return b.as_markup()


def kb_trip_request_date_to_next_week(
    min_date: date,
):
    b = InlineKeyboardBuilder()
    today = date.today()

    days_to_monday = (7 - today.weekday()) % 7 or 7
    start = today + timedelta(days=days_to_monday)

    for i in range(7):
        d = start + timedelta(days=i)

        if d < min_date:
            continue

        b.button(
            text=d.strftime("%d.%m"),
            callback_data=f"t_req_to:{d.isoformat()}",
        )

    b.button(
        text="⬅️ Назад",
        callback_data="t_req_cal:back",
    )

    b.button(
        text="✏️ Другая дата",
        callback_data="t_req_to:other",
    )

    b.adjust(3)
    return b.as_markup()


async def trip_request_show_date_to(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()
    date_from = date.fromisoformat(data["date_from"])

    await callback.message.edit_text(
        f"📅 Начальная дата: {date_from.strftime('%d.%m.%Y')}\n\n"
        "До какой даты вы готовы ехать?",
        reply_markup=kb_trip_request_date_to(date_from),
    )


@router.callback_query(F.data == "t_cal:next")
async def trip_calendar_next(cq: CallbackQuery):
    await cq.answer()

    await cq.message.edit_reply_markup(
        reply_markup=kb_trip_calendar_next_week()
    )


@router.callback_query(F.data == "t_cal:back")
async def trip_calendar_back(cq: CallbackQuery):
    await cq.answer()

    await cq.message.edit_reply_markup(
        reply_markup=kb_trip_calendar_current_week()
    )


@router.callback_query(F.data == "t_date:other")
async def trip_calendar_other(
    cq: CallbackQuery,
    state: FSMContext,
):
    await state.set_state(TripOfferStates.trip_date)

    await cq.message.edit_text(
        "📅 На какую дату запланирована поездка?\n\n"
        "Введите дату в формате ДД.ММ.ГГГГ."
    )

    await cq.answer()


@router.callback_query(F.data.startswith("t_date:"))
async def trip_calendar_date(
    cq: CallbackQuery,
    state: FSMContext,
):
    value = cq.data.split(":", 1)[1]

    if value == "month":
        await cq.answer(
            "Введите конкретную дату в формате ДД.ММ.ГГГГ.",
            show_alert=True,
        )
        return

    try:
        selected_date = date.fromisoformat(value)
    except ValueError:
        await cq.answer("Некорректная дата.", show_alert=True)
        return

    if selected_date < date.today():
        await cq.answer(
            "Дата уже прошла.",
            show_alert=True,
        )
        return

    await state.update_data(
        trip_date=selected_date.isoformat()
    )
    await state.set_state(TripOfferStates.departure_time)

    await cq.message.edit_text(
        f"📅 Дата поездки: {selected_date.strftime("%d.%m.%Y")}\n\n"
        "🕐 Время отправления?",
        reply_markup=kb_trip_departure_time(),
    )

    await cq.answer()


@router.callback_query(F.data.startswith("t_req_cal:"))
async def trip_request_calendar_week(
    cq: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()
    date_from = date.fromisoformat(data["date_from"])

    action = cq.data.split(":", 1)[1]

    if action == "next":
        markup = kb_trip_request_date_to_next_week(date_from)
    else:
        markup = kb_trip_request_date_to(date_from)

    await cq.message.edit_reply_markup(
        reply_markup=markup
    )

    await cq.answer()


@router.callback_query(F.data == "t_req_to:other")
async def trip_request_date_to_other(
    cq: CallbackQuery,
    state: FSMContext,
):
    await state.set_state(TripRequestStates.date_to)

    await cq.message.edit_text(
        "📅 До какой даты вы готовы ехать?\n\n"
        "Введите дату в формате ДД.ММ.ГГГГ."
    )

    await cq.answer()


@router.callback_query(F.data == "t_req_to:same")
async def trip_request_date_to_same(
    cq: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()
    date_from = date.fromisoformat(data["date_from"])

    await state.update_data(
        date_to=date_from.isoformat()
    )
    await state.set_state(TripRequestStates.passengers)

    await cq.message.edit_text(
        f"📅 Дата поездки: {date_from.strftime('%d.%m.%Y')}\n\n"
        "👥 Сколько пассажиров?",
        reply_markup=kb_trip_passengers(),
    )

    await cq.answer()


@router.callback_query(F.data.startswith("t_req_to:"))
async def trip_request_date_to_selected(
    cq: CallbackQuery,
    state: FSMContext,
):
    value = cq.data.split(":", 1)[1]

    try:
        selected_date = date.fromisoformat(value)
    except ValueError:
        await cq.answer("Некорректная дата.", show_alert=True)
        return

    data = await state.get_data()
    date_from = date.fromisoformat(data["date_from"])

    if selected_date < date_from:
        await cq.answer(
            "Конечная дата не может быть раньше начальной.",
            show_alert=True,
        )
        return

    await state.update_data(
        date_to=selected_date.isoformat()
    )
    await state.set_state(TripRequestStates.passengers)

    await cq.message.edit_text(
        f"📅 Период: "
        f"{date_from.strftime('%d.%m.%Y')} — "
        f"{selected_date.strftime('%d.%m.%Y')}\n\n"
        "👥 Сколько пассажиров?",
        reply_markup=kb_trip_passengers(),
    )

    await cq.answer()


# =========================================================
# =========================================================
# TRIP OFFER DATE SELECTION
# =========================================================

@router.callback_query(F.data.startswith("t_date:"))
async def trip_offer_trip_calendar_date(
    callback: CallbackQuery,
    state: FSMContext,
):
    value = callback.data.split(":", 1)[1]

    if value in {"other", "month"}:
        if value == "month":
            await callback.answer(
                "Выберите конкретную дату выше или нажмите «Другая дата».",
                show_alert=True,
            )
            return

        await callback.message.edit_text(
            "📅 Введите дату поездки в формате ДД.ММ.ГГГГ."
        )
        await callback.answer()
        return

    try:
        selected_date = date.fromisoformat(value)
    except ValueError:
        await callback.answer("Некорректная дата.", show_alert=True)
        return

    if selected_date < date.today():
        await callback.answer(
            "Дата уже прошла.",
            show_alert=True,
        )
        return

    await state.update_data(trip_date=selected_date.isoformat())
    await state.set_state(TripOfferStates.departure_time)

    await callback.message.edit_text(
        f"📅 Дата поездки: {selected_date.strftime("%d.%m.%Y")}\n\n"
        "🕐 Время отправления?",
        reply_markup=kb_trip_departure_time(),
    )
    await callback.answer()


# USER
# =========================================================

async def get_user_by_tg_id(session, tg_user_id: int):
    result = await session.execute(
        select(User).where(User.tg_user_id == tg_user_id)
    )
    return result.scalar_one_or_none()


# =========================================================
# MENU
# =========================================================

@router.callback_query(F.data == "trip:menu")
async def trip_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    await callback.message.edit_text(
        "🚘 Поездки\n\n"
        "Здесь можно найти пассажира или водителя "
        "для поездки на автомобиле.",
        reply_markup=kb_trips(),
    )

    await callback.answer()


# =========================================================
# ИЩУ ПОЕЗДКУ
# =========================================================

@router.callback_query(F.data == "trip:req")
async def trip_request_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()
    await state.set_state(TripRequestStates.from_city)

    await callback.message.edit_text(
        "🔍 Ищу поездку\n\n"
        "Из какого города вы хотите поехать?",
        reply_markup=kb_trip_cities(),
    )

    await callback.answer()






@router.callback_query(
    TripRequestStates.date_from,
    F.data == "t_req_from_cal:next",
)
async def trip_request_date_from_next_week(
    callback: CallbackQuery,
    state: FSMContext,
):
    await callback.message.edit_reply_markup(
        reply_markup=kb_trip_request_date_from_next_week()
    )
    await callback.answer()


@router.callback_query(
    TripRequestStates.date_from,
    F.data == "t_req_from_cal:back",
)
async def trip_request_date_from_back(
    callback: CallbackQuery,
    state: FSMContext,
):
    await callback.message.edit_reply_markup(
        reply_markup=kb_trip_request_date_from_current_week()
    )
    await callback.answer()


@router.callback_query(
    TripRequestStates.date_from,
    F.data == "t_req_from:other",
)
async def trip_request_date_from_other(
    callback: CallbackQuery,
    state: FSMContext,
):
    await callback.message.edit_text(
        "📅 На какую дату вы ищете поездку?\n\n"
        "Введите дату в формате ДД.ММ.ГГГГ."
    )
    await callback.answer()


@router.callback_query(
    TripRequestStates.date_from,
    F.data.startswith("t_req_from:"),
)
async def trip_request_date_from_selected(
    callback: CallbackQuery,
    state: FSMContext,
):
    value = callback.data.split(":", 1)[1]

    try:
        selected_date = date.fromisoformat(value)
    except ValueError:
        await callback.answer(
            "Некорректная дата.",
            show_alert=True,
        )
        return

    if selected_date < date.today():
        await callback.answer(
            "Дата уже прошла.",
            show_alert=True,
        )
        return

    await state.update_data(
        date_from=selected_date.isoformat()
    )
    await state.set_state(TripRequestStates.date_to)

    await callback.message.edit_text(
        f"📅 Начальная дата: {selected_date.strftime('%d.%m.%Y')}\n\n"
        "До какой даты вы готовы ехать?",
        reply_markup=kb_trip_request_date_to(selected_date),
    )
    await callback.answer()


def parse_trip_date(value: str) -> date | None:
    value = value.strip()

    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    return None


@router.message(TripRequestStates.date_from)
async def trip_request_date_from(
    message: Message,
    state: FSMContext,
):
    parsed = parse_trip_date(message.text or "")

    if parsed is None:
        await message.answer(
            "Не удалось распознать дату.\n"
            "Введите её в формате ДД.ММ.ГГГГ, например 15.09.2026."
        )
        return

    if parsed < date.today():
        await message.answer(
            "Дата уже прошла.\n"
            "Введите будущую дату."
        )
        return

    await state.update_data(date_from=parsed.isoformat())
    await state.set_state(TripRequestStates.date_to)

    await message.answer(
        f"📅 Начальная дата: {parsed.strftime('%d.%m.%Y')}\n\n"
        "До какой даты вы готовы ехать?",
        reply_markup=kb_trip_request_date_to(parsed),
    )


@router.message(TripRequestStates.date_to)
async def trip_request_date_to(
    message: Message,
    state: FSMContext,
):
    parsed = parse_trip_date(message.text or "")

    if parsed is None:
        await message.answer(
            "Не удалось распознать дату.\n"
            "Введите её в формате ДД.ММ.ГГГГ."
        )
        return

    if parsed < date.today():
        await message.answer(
            "Дата уже прошла.\n"
            "Введите будущую дату."
        )
        return

    data = await state.get_data()

    date_from = date.fromisoformat(data["date_from"])

    if parsed < date_from:
        await message.answer(
            "Конечная дата не может быть раньше начальной.\n"
            "Введите дату ещё раз."
        )
        return

    await state.update_data(date_to=parsed.isoformat())
    await state.set_state(TripRequestStates.passengers)

    await message.answer(
        "👥 Сколько пассажиров?",
        reply_markup=kb_trip_passengers(),
    )


def kb_trip_passengers():
    b = InlineKeyboardBuilder()
    for i in range(1, 5):
        b.button(
            text=str(i),
            callback_data=f"trip_passengers:{i}",
        )
    b.button(
        text="5 или более",
        callback_data="trip_passengers:5",
    )
    b.adjust(4, 1)
    return b.as_markup()


def kb_trip_comment():
    b = InlineKeyboardBuilder()
    b.button(
        text="✏️ Добавить комментарий",
        callback_data="trip_comment:add",
    )
    b.button(
        text="⏭️ Без комментария",
        callback_data="trip_comment:none",
    )
    b.adjust(1)
    return b.as_markup()


async def save_trip_request(
    message: Message,
    state: FSMContext,
    comment: str | None,
    user_id: int,
):
    data = await state.get_data()

    if message.from_user is None:
        await message.answer(
            "Не удалось определить пользователя. "
            "Попробуйте снова через /start."
        )
        await state.clear()
        return

    async with get_session() as session:
        user = await get_user_by_tg_id(
            session,
            user_id,
        )

        if user is None:
            await message.answer(
                "Не удалось найти ваш профиль.\n\n"
                "Нажмите /start и попробуйте снова."
            )
            await state.clear()
            return

        trip_request = TripRequest(
            user_id=user.id,
            from_city=data["from_city"],
            to_city=data["to_city"],
            date_from=date.fromisoformat(data["date_from"]),
            date_to=date.fromisoformat(data["date_to"]),
            passengers=data["passengers"],
            comment=comment,
            status="active",
        )

        session.add(trip_request)
        await session.commit()
        await session.refresh(trip_request)

        matches = await find_matches_for_trip_request(
            session,
            trip_request.id,
        )

    if matches:
        await _notify_trip_matches(message, matches, "driver")

    date_from = date.fromisoformat(data["date_from"])
    date_to = date.fromisoformat(data["date_to"])

    if date_from == date_to:
        date_text = date_from.strftime("%d.%m.%Y")
    else:
        date_text = (
            f"{date_from.strftime('%d.%m.%Y')} — "
            f"{date_to.strftime('%d.%m.%Y')}"
        )

    passengers = data["passengers"]
    passengers_text = "5+" if passengers == 5 else str(passengers)

    await message.answer(
        "✅ Заявка на поездку создана!\n\n"
        f"🚗 {data['from_city']} → {data['to_city']}\n"
        f"📅 {date_text}\n"
        f"👥 Пассажиров: {passengers_text}"
        + (f"\n💬 {comment}" if comment else "")
    )

    await state.clear()


@router.callback_query(
    TripRequestStates.passengers,
    F.data.startswith("trip_passengers:"),
)
async def trip_request_passengers_selected(
    callback: CallbackQuery,
    state: FSMContext,
):
    value = callback.data.split(":", 1)[1]

    try:
        passengers = int(value)
    except ValueError:
        await callback.answer(
            "Некорректное количество.",
            show_alert=True,
        )
        return

    if passengers < 1 or passengers > 5:
        await callback.answer(
            "Некорректное количество.",
            show_alert=True,
        )
        return

    await state.update_data(passengers=passengers)
    await state.set_state(TripRequestStates.comment)

    await callback.message.edit_text(
        "💬 Хотите добавить комментарий к поездке?\n\n"
        "Например: багаж, животное, детское кресло "
        "или удобное время отправления.",
        reply_markup=kb_trip_comment(),
    )
    await callback.answer()


@router.message(TripRequestStates.passengers)
async def trip_request_passengers(
    message: Message,
    state: FSMContext,
):
    await message.answer(
        "👥 Выберите количество пассажиров кнопкой ниже.",
        reply_markup=kb_trip_passengers(),
    )


@router.callback_query(
    TripRequestStates.comment,
    F.data == "trip_comment:add",
)
async def trip_request_comment_add(
    callback: CallbackQuery,
    state: FSMContext,
):
    await callback.message.edit_text(
        "💬 Напишите комментарий к поездке."
    )
    await callback.answer()


@router.callback_query(
    TripRequestStates.comment,
    F.data == "trip_comment:none",
)
async def trip_request_comment_none(
    callback: CallbackQuery,
    state: FSMContext,
):
    await callback.answer()
    await save_trip_request(
        callback.message,
        state,
        None,
        callback.from_user.id,
    )



async def _trip_user_name(user: User) -> str:
    if user.tg_username:
        return f"@{user.tg_username.lstrip('@')}"
    if user.first_name:
        return user.first_name
    return "Пользователь"


def _trip_price_text(offer: TripOffer) -> str:
    if offer.price_mode == "free":
        return "бесплатно"
    if offer.price_mode == "fixed" and offer.price_amount is not None:
        currency = offer.price_currency or ""
        return f"{offer.price_amount:g} {currency}".strip()
    return "по договорённости"


def _trip_offer_text(offer: TripOffer) -> str:
    departure = f"\n🕐 Отправление: {offer.departure_time}" if offer.departure_time else ""
    return (
        f"🚗 Поездка: {offer.from_city} → {offer.to_city}\n"
        f"📅 Дата: {offer.trip_date.strftime('%d.%m.%Y')}"
        f"{departure}\n"
        f"💺 Мест: {offer.seats if offer.seats < 5 else '5+'}\n"
        f"💰 Цена: {_trip_price_text(offer)}"
    )


def _trip_request_text(request: TripRequest) -> str:
    if request.date_from == request.date_to:
        dates = request.date_from.strftime("%d.%m.%Y")
    else:
        dates = (
            f"{request.date_from.strftime('%d.%m.%Y')} — "
            f"{request.date_to.strftime('%d.%m.%Y')}"
        )

    return (
        f"🔍 Поездка: {request.from_city} → {request.to_city}\n"
        f"📅 Дата: {dates}\n"
        f"👥 Пассажиров: {request.passengers}"
    )


async def _load_trip_matches(session, match_ids: list[int]):
    if not match_ids:
        return []

    result = await session.execute(
        select(TripMatch)
        .where(TripMatch.id.in_(match_ids))
        .options(
            selectinload(TripMatch.request).selectinload(TripRequest.user),
            selectinload(TripMatch.offer).selectinload(TripOffer.user),
        )
    )
    return result.scalars().all()


async def _notify_trip_matches(message: Message, matches, target_role: str):
    match_ids = [match.id for match in matches if getattr(match, "id", None)]
    if not match_ids:
        return

    async with get_session() as session:
        loaded_matches = await _load_trip_matches(session, match_ids)

        for match in loaded_matches:
            try:
                if target_role == "driver":
                    target_user = match.offer.user
                    text = (
                        "✨ Нашлось совпадение по поездке!\\n\\n"
                        f"{_trip_request_text(match.request)}\\n\\n"
                        "Есть пассажирский запрос, подходящий под вашу поездку."
                    )
                else:
                    target_user = match.request.user
                    text = (
                        "✨ Нашлось совпадение по поездке!\\n\\n"
                        f"{_trip_offer_text(match.offer)}\\n\\n"
                        "Нашёлся водитель, подходящий под ваш запрос."
                    )

                await message.bot.send_message(
                    target_user.tg_user_id,
                    text,
                    reply_markup=kb_trip_match(match.id),
                )

                if target_role == "driver":
                    match.notified_driver = True
                else:
                    match.notified_requester = True

            except Exception:
                logger.exception(
                    "Ошибка уведомления по trip_match id=%s",
                    match.id,
                )

        await session.commit()


@router.message(TripRequestStates.comment)
async def trip_request_comment(
    message: Message,
    state: FSMContext,
):
    comment = (message.text or "").strip()

    if comment.casefold() in {"нет", "не", "-", "no"}:
        comment = None

    await save_trip_request(
        message,
        state,
        comment,
        message.from_user.id,
    )




# =========================================================
# ПРЕДЛАГАЮ ПОЕЗДКУ
# =========================================================

@router.callback_query(F.data == "trip:offer")
async def trip_offer_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()
    await state.set_state(TripOfferStates.from_city)
    await callback.message.edit_text(
        "🚗 Предлагаю поездку\n\n"
        "Из какого города вы едете?",
        reply_markup=kb_trip_cities(),
    )
    await callback.answer()








@router.message(TripOfferStates.trip_date)
async def trip_offer_date(
    message: Message,
    state: FSMContext,
):
    parsed = parse_trip_date(message.text or "")

    if parsed is None:
        await message.answer(
            "Не удалось распознать дату.\n"
            "Введите её в формате ДД.ММ.ГГГГ."
        )
        return

    if parsed < date.today():
        await message.answer(
            "Дата уже прошла.\n"
            "Введите будущую дату."
        )
        return

    await state.update_data(
        trip_date=parsed.isoformat()
    )
    await state.set_state(TripOfferStates.departure_time)

    await message.answer(
        "🕐 Время отправления?",
        reply_markup=kb_trip_departure_time(),
    )


@router.callback_query(F.data == "trip_departure_time:set")
async def trip_departure_time_set(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.set_state(TripOfferStates.departure_time)
    await callback.message.edit_text(
        "🕐 Введите время отправления в формате ЧЧ:ММ\n\n"
        "Например: 08:30"
    )
    await callback.answer()


@router.callback_query(F.data == "trip_departure_time:any")
async def trip_departure_time_any(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.update_data(departure_time=None)
    await state.set_state(TripOfferStates.seats)
    await callback.message.edit_text(
        "💺 Сколько свободных мест?",
        reply_markup=kb_trip_offer_seats(),
    )
    await callback.answer()


@router.message(TripOfferStates.departure_time)
async def trip_offer_departure_time(
    message: Message,
    state: FSMContext,
):
    value = (message.text or "").strip()

    if value.casefold() in {"нет", "-", "не знаю", "no"}:
        departure_time = None
    else:
        try:
            parsed_time = datetime.strptime(
                value,
                "%H:%M",
            )
            departure_time = parsed_time.strftime("%H:%M")
        except ValueError:
            await message.answer(
                "Введите время в формате ЧЧ:ММ, например 08:30,\n"
                "или напишите «нет»."
            )
            return

    await state.update_data(
        departure_time=departure_time
    )
    await state.set_state(TripOfferStates.seats)

    await message.answer(
        "💺 Сколько свободных мест?",
        reply_markup=kb_trip_offer_seats(),
    )


@router.callback_query(F.data.startswith("trip_offer_seats:"))
async def trip_offer_seats_button(
    callback: CallbackQuery,
    state: FSMContext,
):
    value = callback.data.split(":", 1)[1]

    try:
        seats = int(value)
    except ValueError:
        await callback.answer("Некорректное количество мест.", show_alert=True)
        return

    if seats < 1 or seats > 5:
        await callback.answer("Некорректное количество мест.", show_alert=True)
        return

    await state.update_data(seats=seats)
    await state.set_state(TripOfferStates.price_mode)

    await callback.message.edit_text(
        "💰 Какую оплату вы хотите?",
        reply_markup=kb_trip_price_mode(),
    )
    await callback.answer()


@router.message(TripOfferStates.seats)
async def trip_offer_seats(
    message: Message,
    state: FSMContext,
):
    value = (message.text or "").strip()

    try:
        seats = int(value)
    except ValueError:
        await message.answer(
            "Введите количество мест числом, например: 2"
        )
        return

    if seats < 1 or seats > 20:
        await message.answer(
            "Количество мест должно быть от 1 до 20."
        )
        return

    await state.update_data(seats=seats)
    await state.set_state(TripOfferStates.price_mode)

    await message.answer(
        "💰 Какую оплату вы хотите?\n\n"
        "Напишите один из вариантов:\n"
        "• бесплатно\n"
        "• пополам\n"
        "• фиксированная сумма\n"
        "• договорная"
    )


def normalize_price_mode(value: str) -> str | None:
    value = value.casefold().strip()

    if value in {
        "бесплатно",
        "бесплатная",
        "free",
        "0",
    }:
        return "free"

    if value in {
        "пополам",
        "половина",
        "split",
    }:
        return "split"

    if value in {
        "фиксированная сумма",
        "фиксированная",
        "сумма",
        "fixed",
    }:
        return "fixed"

    if value in {
        "договорная",
        "по договоренности",
        "договор",
        "negotiable",
    }:
        return "negotiable"

    return None


@router.callback_query(F.data == "trip_price:negotiable")
async def trip_price_negotiable(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.update_data(price_mode="negotiable")
    await state.set_state(TripOfferStates.comment)
    await callback.message.edit_text(
        "💬 Добавьте комментарий к поездке.\n\n"
        "Например: багаж, место для животного, удобное время отправления.\n\n"
        "Если комментарий не нужен — напишите «нет»."
    )
    await callback.answer()


@router.callback_query(F.data == "trip_price:fixed")
async def trip_price_fixed(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.update_data(price_mode="fixed")
    await state.set_state(TripOfferStates.price_amount)
    await callback.message.edit_text(
        "💰 Какая сумма?\n\n"
        "Например: 50"
    )
    await callback.answer()


@router.message(TripOfferStates.price_mode)
async def trip_offer_price_mode(
    message: Message,
    state: FSMContext,
):
    mode = normalize_price_mode(message.text or "")

    if mode is None:
        await message.answer(
            "Выберите вариант оплаты кнопкой выше "
            "или напишите:\n"
            "по договорённости\n"
            "фиксированная цена"
        )
        return

    await state.update_data(price_mode=mode)

    if mode == "fixed":
        await state.set_state(TripOfferStates.price_amount)

        await message.answer(
            "💰 Какая сумма?\n\n"
            "Например: 50"
        )
        return

    await state.set_state(TripOfferStates.comment)

    await message.answer(
        "💬 Добавьте комментарий к поездке.\n\n"
        "Например: багаж, место для животного, "
        "удобное время отправления.\n\n"
        "Если комментарий не нужен — напишите «нет»."
    )


@router.message(TripOfferStates.price_amount)
async def trip_offer_price_amount(
    message: Message,
    state: FSMContext,
):
    value = (message.text or "").strip().replace(",", ".")

    try:
        amount = float(value)
    except ValueError:
        await message.answer(
            "Введите сумму числом, например: 50"
        )
        return

    if amount <= 0:
        await message.answer(
            "Сумма должна быть больше нуля."
        )
        return

    await state.update_data(price_amount=amount)
    await state.set_state(TripOfferStates.price_currency)

    await message.answer(
        "💱 Выберите валюту:",
        reply_markup=kb_trip_currency(),
    )


@router.callback_query(F.data.startswith("trip_currency:"))
async def trip_currency_button(
    callback: CallbackQuery,
    state: FSMContext,
):
    currency = callback.data.split(":", 1)[1].upper()

    if currency == "OTHER":
        await state.set_state(TripOfferStates.price_currency)
        await callback.message.edit_text(
            "💱 Введите валюту вручную.\n\n"
            "Например: PLN, GBP или TRY."
        )
        await callback.answer()
        return

    if currency not in {"EUR", "CZK", "USD", "RUB"}:
        await callback.answer("Некорректная валюта.", show_alert=True)
        return

    await state.update_data(price_currency=currency)
    await state.set_state(TripOfferStates.comment)

    await callback.message.edit_text(
        "💬 Добавьте комментарий к поездке.\n\n"
        "Например: багаж, место для животного, удобное время отправления.\n\n"
        "Если комментарий не нужен — напишите «нет»."
    )
    await callback.answer()


@router.message(TripOfferStates.price_currency)
async def trip_offer_price_currency(
    message: Message,
    state: FSMContext,
):
    currency = (message.text or "").strip().upper()

    if not currency:
        await message.answer(
            "Введите валюту, например EUR."
        )
        return

    if len(currency) > 8:
        await message.answer(
            "Слишком длинное обозначение валюты."
        )
        return

    await state.update_data(
        price_currency=currency
    )
    await state.set_state(TripOfferStates.comment)

    await message.answer(
        "💬 Добавьте комментарий к поездке.\n\n"
        "Если комментарий не нужен — напишите «нет»."
    )


@router.message(TripOfferStates.comment)
async def trip_offer_comment(
    message: Message,
    state: FSMContext,
):
    comment = (message.text or "").strip()

    if comment.casefold() in {"нет", "не", "-", "no"}:
        comment = None

    data = await state.get_data()

    if message.from_user is None:
        await message.answer(
            "Не удалось определить пользователя. "
            "Попробуйте снова через /start."
        )
        await state.clear()
        return

    async with get_session() as session:
        user = await get_user_by_tg_id(
            session,
            message.from_user.id,
        )

        if user is None:
            await message.answer(
                "Не удалось найти ваш профиль.\n\n"
                "Нажмите /start и попробуйте снова."
            )
            await state.clear()
            return

        price_mode = data.get("price_mode", "negotiable")

        price_amount = None
        price_currency = None

        if price_mode == "fixed":
            price_amount = data.get("price_amount")
            price_currency = data.get("price_currency")

        trip_offer = TripOffer(
            user_id=user.id,
            from_city=data["from_city"],
            to_city=data["to_city"],
            trip_date=date.fromisoformat(data["trip_date"]),
            departure_time=data.get("departure_time"),
            seats=data["seats"],
            price_mode=price_mode,
            price_amount=price_amount,
            price_currency=price_currency,
            comment=comment,
            status="active",
        )

        session.add(trip_offer)
        await session.commit()
        await session.refresh(trip_offer)

        matches = await find_matches_for_trip_offer(
            session,
            trip_offer.id,
        )

    if matches:
        await _notify_trip_matches(message, matches, "requester")

    trip_date = date.fromisoformat(data["trip_date"])

    if price_mode == "free":
        price_text = "бесплатно"
    elif price_mode == "split":
        price_text = "пополам"
    elif price_mode == "fixed":
        price_text = (
            f"{data.get('price_amount')} "
            f"{data.get('price_currency')}"
        )
    else:
        price_text = "договорная"

    departure_time = data.get("departure_time")

    if departure_time:
        time_text = f"\n🕐 Отправление: {departure_time}"
    else:
        time_text = ""

    await state.clear()

    await message.answer(
        "✅ Поездка опубликована!\n\n"
        f"🚘 {data['from_city']} → {data['to_city']}\n"
        f"📅 {trip_date.strftime('%d.%m.%Y')}"
        f"{time_text}\n"
        f"💺 Свободных мест: {data['seats'] if data['seats'] < 5 else '5+'}\n"
        f"💰 Оплата: {price_text}\n\n"
        "Я буду искать подходящие запросы пассажиров.",
        reply_markup=kb_trip_back(),
    )


# =========================================================
# TRIP MATCHES — VIEW / CONTACT
# =========================================================

PAYWALL_TEXT = (
    "🔒 Доступ к контактам закрыт\n\n"
    "💳 Оформите подписку или купите доступ:\n"
    "/subscribe"
)


@router.callback_query(F.data.startswith("trip_match:view:"))
async def trip_match_view(callback: CallbackQuery):
    await callback.answer()

    try:
        match_id = int(callback.data.split(":")[-1])
    except (ValueError, AttributeError):
        await callback.message.answer("Не удалось открыть совпадение.")
        return

    async with get_session() as session:
        result = await session.execute(
            select(TripMatch)
            .where(TripMatch.id == match_id)
            .options(
                selectinload(TripMatch.request).selectinload(TripRequest.user),
                selectinload(TripMatch.offer).selectinload(TripOffer.user),
            )
        )
        match = result.scalar_one_or_none()

        if match is None:
            await callback.message.answer("Совпадение не найдено.")
            return

        current_user = await get_user_by_tg_id(
            session,
            callback.from_user.id,
        )

        if current_user is None:
            await callback.message.answer(
                "Не удалось найти ваш профиль.\n\n"
                "Нажмите /start и попробуйте снова."
            )
            return

        is_requester = match.request.user_id == current_user.id
        is_driver = match.offer.user_id == current_user.id

        if not is_requester and not is_driver:
            await callback.answer(
                "Это совпадение вам не принадлежит.",
                show_alert=True,
            )
            return

        if is_requester:
            text = (
                "✨ Подходящая поездка!\n\n"
                f"{_trip_offer_text(match.offer)}"
            )
            if match.offer.comment:
                text += f"\n💬 Комментарий: {match.offer.comment}"
        else:
            text = (
                "✨ Подходящий запрос пассажира!\n\n"
                f"{_trip_request_text(match.request)}"
            )
            if match.request.comment:
                text += f"\n💬 Комментарий: {match.request.comment}"

        await callback.message.answer(
            text,
            reply_markup=kb_trip_match(match.id),
        )


@router.callback_query(F.data.startswith("trip_match:contact:"))
async def trip_match_contact(callback: CallbackQuery):
    await callback.answer()

    try:
        match_id = int(callback.data.split(":")[-1])
    except (ValueError, AttributeError):
        await callback.message.answer("Не удалось открыть контакт.")
        return

    async with get_session() as session:
        result = await session.execute(
            select(TripMatch)
            .where(TripMatch.id == match_id)
            .with_for_update()
            .options(
                selectinload(TripMatch.request).selectinload(TripRequest.user),
                selectinload(TripMatch.offer).selectinload(TripOffer.user),
            )
        )
        match = result.scalar_one_or_none()

        if match is None:
            await callback.message.answer("Совпадение не найдено.")
            return

        current_user = await get_user_by_tg_id(
            session,
            callback.from_user.id,
        )

        if current_user is None:
            await callback.message.answer(
                "Не удалось найти ваш профиль.\n\n"
                "Нажмите /start и попробуйте снова."
            )
            return

        is_requester = match.request.user_id == current_user.id
        is_driver = match.offer.user_id == current_user.id

        if not is_requester and not is_driver:
            await callback.answer(
                "Это совпадение вам не принадлежит.",
                show_alert=True,
            )
            return

        # PAYWALL — та же логика, что и для посылок
        if not await can_access_contacts(session, current_user):
            await callback.answer(
                "Нужен доступ",
                show_alert=True,
            )
            await callback.message.answer(PAYWALL_TEXT)
            return

        # Списываем контакт только при первом открытии этого TripMatch
        # этим пользователем. Повторные открытия бесплатны.
        contact_open_res = await session.execute(
            select(TripMatchContactOpen).where(
                TripMatchContactOpen.trip_match_id == match.id,
                TripMatchContactOpen.user_id == current_user.id,
            )
        )
        contact_open = contact_open_res.scalar_one_or_none()

        if contact_open is None:
            session.add(
                TripMatchContactOpen(
                    trip_match_id=match.id,
                    user_id=current_user.id,
                )
            )
            await spend_contact_no_commit(session, current_user)
            await session.commit()

        other_user = (
            match.offer.user
            if is_requester
            else match.request.user
        )

        username = (
            f"@{other_user.tg_username.lstrip('@')}"
            if other_user.tg_username
            else None
        )

        if username:
            contact_text = (
                "📞 Контакт пользователя:\n\n"
                f"{username}"
            )
        else:
            contact_text = (
                "📞 Контакт пользователя:\n\n"
                f"👤 {other_user.first_name or 'Пользователь'}\n"
                "Telegram username не указан."
            )

        await callback.message.answer(contact_text)

        try:
            await callback.message.edit_reply_markup(
                reply_markup=None,
            )
        except Exception:
            logger.exception(
                "Не удалось убрать кнопку контакта "
                "для trip_match id=%s",
                match_id,
            )
