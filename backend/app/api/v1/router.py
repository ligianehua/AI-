from fastapi import APIRouter

from app.api.v1 import (
    accounts,
    activities,
    ai,
    auth,
    contacts,
    dashboard,
    leads,
    notifications,
    opportunities,
    teams,
    users,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(teams.router)
api_router.include_router(dashboard.router)
api_router.include_router(ai.router)
api_router.include_router(leads.router)
api_router.include_router(accounts.router)
api_router.include_router(contacts.router)
api_router.include_router(opportunities.router)
api_router.include_router(activities.router)
api_router.include_router(notifications.router)
