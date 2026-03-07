from enum import StrEnum


class Category(StrEnum):
    docs = "docs"
    clothes = "clothes"
    cosmetics = "cosmetics"
    tech = "tech"
    other = "other"


class WeightBand(StrEnum):
    lt1 = "lt1"
    w1_3 = "1_3"
    w3_5 = "3_5"
    gt5 = "gt5"


class CarryType(StrEnum):
    hand_only = "hand_only"
    luggage_ok = "luggage_ok"
    any = "any"


class BaggageType(StrEnum):
    hand = "hand"
    luggage = "luggage"
    both = "both"


class RewardMode(StrEnum):
    discuss = "discuss"
    fixed = "fixed"
    per_kg = "per_kg"


class RowStatus(StrEnum):
    active = "active"
    matched = "matched"
    paused = "paused"
    closed = "closed"
    canceled = "canceled"


class MatchStatus(StrEnum):
    proposed = "proposed"
    requested = "requested"   # заказчик отправил предложение путешественнику
    accepted = "accepted"
    rejected = "rejected"
    chat_created = "chat_created"
    expired = "expired"