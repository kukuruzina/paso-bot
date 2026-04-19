from aiogram.utils.keyboard import InlineKeyboardBuilder


# =========================================================
# MAIN MENU
# =========================================================

def kb_main(is_admin: bool = False):
    b = InlineKeyboardBuilder()
    b.button(text="📦 Отправить товар", callback_data="go:req")
    b.button(text="✈️ Планирую поездку и могу взять", callback_data="go:off")
    b.button(text="👤 Профиль", callback_data="go:profile")
    b.button(text="💳 Подписка", callback_data="go:subscribe")

    if is_admin:
       b.button(text="📊 Admin stats", callback_data="go:stats")

    # 🔥 новая кнопка (рефералка)
    b.button(text="🎁 Пригласить", callback_data="ref:menu")

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

    # 💸 основная кнопка (монетизация)
    b.button(
        text="🔓 Открыть контакт",
        callback_data=f"match:contact:{match_id}"
    )

    # 👤 доверие → повышает оплату
    b.button(
        text="👤 Профиль",
        callback_data=f"match:profile:{match_id}"
    )

    b.adjust(1)

    return b.as_markup()



