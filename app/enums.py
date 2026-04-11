from enum import Enum


class Category(str, Enum):
    clothes = "clothes"
    cosmetics = "cosmetics"
    docs = "docs"
    tech = "tech"
    other = "other"


class WeightBand(str, Enum):
    lt1 = "lt1"
    w1_3 = "w1_3"
    w3_5 = "w3_5"
    gt5 = "gt5"


class CarryType(str, Enum):
    hand_only = "hand_only"
    luggage_ok = "luggage_ok"
    any = "any"


class RowStatus(str, Enum):
    draft = "draft"
    active = "active"
    archived = "archived"


class MatchStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"

