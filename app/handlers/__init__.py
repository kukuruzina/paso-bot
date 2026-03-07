from .start import router as start_router
from .subscription_flow import router as subscription_router
from .admin_subs import router as admin_subs_router
from .request_flow import router as request_router
from .offer_flow import router as offer_router
from .match_flow import router as match_router
from .admin import router as admin_router
from .profile import router as profile_router


def all_routers():
    return [
        start_router,
        subscription_router,
        admin_subs_router,
        request_router,
        offer_router,
        match_router,
        profile_router,
        admin_router,   # если используешь
    ]