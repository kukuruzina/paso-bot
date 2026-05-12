from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

# =========================================================
# POPULAR CITIES INLINE
# =========================================================

POPULAR_CITIES = [
    "Прага",
    "Стамбул",
    "Анталья",
    "Тбилиси",
    "Москва",
    "Алматы",
]


def kb_popular_cities_INLINE(exclude: str | None = None):

    kb = InlineKeyboardBuilder()

    for city in POPULAR_CITIES:

        if exclude and city == exclude:
            continue

        kb.button(
            text=city,
            callback_data=f"city:{city}"
        )

    kb.adjust(2)

    return kb.as_markup()


# =========================================================
# MAIN MENU
# =========================================================

def kb_main(is_admin: bool = False):
    b = InlineKeyboardBuilder()
    b.button(text="📦 Отправить посылку", callback_data="go:req")
    b.button(text="🧳 Взять заказ в поездку", callback_data="go:off")
    b.button(text="👤 Профиль", callback_data="go:profile")
    b.button(text="💳 Подписка", callback_data="go:subscribe")

    if is_admin:
        b.button(text="📊 Admin stats", callback_data="go:stats")

    # 🎁 рефералка
    b.button(text="🎁 Пригласить", callback_data="ref:menu")

    # 💬 feedback
    b.button(text="💬 Обратная связь", callback_data="feedback:start")

    b.adjust(1)
    return b.as_markup()


# =========================================================
# REQUEST → OFFER (отправитель предлагает сделку)
# =========================================================

def kb_request_suggest(match_id: int):
    b = InlineKeyboardBuilder()
    b.button(
        text="💬 Предложить сделку",
        callback_data=f"match:propose:{match_id}",
    )
    b.adjust(1)
    return b.as_markup()


# =========================================================
# OFFER → REQUEST (перевозчик принимает / отклоняет)
# =========================================================

def kb_offer_match_actions(match_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Принять", callback_data=f"m:acc:{match_id}")
    b.button(text="❌ Отказаться", callback_data=f"m:rej:{match_id}")
    b.adjust(2)
    return b.as_markup()


# =========================================================
# 🔥 MATCH CARD (САМОЕ ВАЖНОЕ — ДЕНЬГИ)
# =========================================================

def match_keyboard(match_id: int):
    b = InlineKeyboardBuilder()

    # 💸 монетизация
    b.button(
        text="🔓 Открыть контакт",
        callback_data=f"match:contact:{match_id}"
    )

    # 👤 профиль
    b.button(
        text="👤 Профиль",
        callback_data=f"match:profile:{match_id}"
    )

    b.adjust(1)
    return b.as_markup()


# =========================================================
# 🔥 ПОСЛЕ ОТКРЫТИЯ КОНТАКТА (НОВОЕ)
# =========================================================

def kb_deal_result(match_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Договорились",
                callback_data=f"deal:ok:{match_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Не договорились",
                callback_data=f"deal:fail:{match_id}"
            )
        ]
    ])


# =========================================================
# ⭐ РЕЙТИНГ (НОВОЕ)
# =========================================================

def kb_rating(match_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐1", callback_data=f"rate:1:{match_id}"),
            InlineKeyboardButton(text="⭐2", callback_data=f"rate:2:{match_id}"),
            InlineKeyboardButton(text="⭐3", callback_data=f"rate:3:{match_id}"),
            InlineKeyboardButton(text="⭐4", callback_data=f"rate:4:{match_id}"),
            InlineKeyboardButton(text="⭐5", callback_data=f"rate:5:{match_id}"),
        ]
    ])


# =========================================================
# ❌ ПРИЧИНЫ ОТКАЗА (НОВОЕ)
# =========================================================

def kb_fail_reasons(match_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💰 Дорого",
                callback_data=f"fail:price:{match_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="📅 Не совпали даты",
                callback_data=f"fail:date:{match_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🤷 Передумал(а)",
                callback_data=f"fail:change:{match_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="✍️ Другое",
                callback_data=f"fail:other:{match_id}"
            )
        ],
    ])


