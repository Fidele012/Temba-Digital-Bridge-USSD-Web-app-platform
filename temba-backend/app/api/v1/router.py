from fastapi import APIRouter

from app.api.v1.endpoints import (
    analytics,
    appointments,
    auth,
    chatbot,
    events,
    notifications,
    providers,
    reports,
    service_requests,
    track,
    ussd,
    users,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(providers.router)
api_router.include_router(reports.router)
api_router.include_router(service_requests.router)
api_router.include_router(appointments.router)
api_router.include_router(notifications.router)
api_router.include_router(analytics.router)
api_router.include_router(ussd.router)
api_router.include_router(track.router)
api_router.include_router(events.router)
api_router.include_router(chatbot.router)
