from aiogram.utils.keyboard import InlineKeyboardBuilder


def kb_main():
    b = InlineKeyboardBuilder()
    b.button(text="📦 Отправить товар", callback_data="go:req")
    b.button(text="✈️ Планирую поездку и могу взять", callback_data="go:off")
    b.button(text="👤 Профиль", callback_data="go:profile")
    b.button(text="💳 Подписка", callback_data="go:subscribe")
    b.adjust(1)
    return b.as_markup()


def kb_request_suggest(match_id: int):
    b = InlineKeyboardBuilder()
    b.button(
        text="💬 Предложить сделку",
        callback_data=f"match:propose:{match_id}",
    )
    b.adjust(1)
    return b.as_markup()


def kb_offer_match_actions(match_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Принять", callback_data=f"m:acc:{match_id}")
    b.button(text="❌ Отказаться", callback_data=f"m:rej:{match_id}")
    b.adjust(2)
    return b.as_markup()