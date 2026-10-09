PLANS = {
    "single": {"title": "🥉 Single", "price_eur": "2", "yookassa_amount": "200.00", "currency": "RUB", "contacts": 5, "duration_days": 0, "priority": False, "benefit": "5 контактов"},
    "standard": {"title": "🥈 Standard", "price_eur": "5.55", "yookassa_amount": "555.00", "currency": "RUB", "contacts": 0, "duration_days": 14, "priority": False, "benefit": "14 дней доступа"},
    "pro": {"title": "🥇 Pro", "price_eur": "9", "yookassa_amount": "900.00", "currency": "RUB", "contacts": 0, "duration_days": 30, "priority": False, "benefit": "30 дней доступа"},
    "premium": {"title": "💎 Premium", "price_eur": "14.5", "yookassa_amount": "1450.00", "currency": "RUB", "contacts": 0, "duration_days": 30, "priority": True, "benefit": "30 дней + приоритет"},
}

def get_plan(plan_key):
    return PLANS.get(plan_key)

def format_plan_title(plan_key):
    plan = get_plan(plan_key)
    if plan is None:
        raise ValueError("Unknown plan: " + str(plan_key))
    return "{} — €{} ({})".format(plan["title"], plan["price_eur"], plan["benefit"])
