from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

router = Router()

ADMIN_ID = 497951218  # ← ВСТАВЬ СВОЙ TELEGRAM ID


# 🔹 FSM состояние
class FeedbackState(StatesGroup):
    waiting_text = State()


# 🔘 нажали кнопку "Обратная связь"
@router.callback_query(F.data == "feedback:start")
async def feedback_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "💬 Напишите ваше сообщение:\n\n"
        "• ошибка\n"
        "• идея\n"
        "• или отзыв"
    )
    await state.set_state(FeedbackState.waiting_text)
    await callback.answer()


# ✍️ пользователь пишет сообщение
@router.message(FeedbackState.waiting_text)
async def handle_feedback(message: Message, state: FSMContext):
    text = message.text

    if not text or len(text) < 3:
        await message.answer("Напишите чуть подробнее 🙏")
        return

    # отправляем тебе
    await message.bot.send_message(
        ADMIN_ID,
        f"💬 FEEDBACK\n\n"
        f"{text}\n\n"
        f"👤 user_id: {message.from_user.id}"
    )

    await message.answer("Спасибо! 🙌 Мы получили сообщение")

    # сбрасываем состояние
    await state.clear()


