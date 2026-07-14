from fastapi import APIRouter

from app.api.v1 import (
    accounts,
    activities,
    ai,
    assistant,
    auth,
    contacts,
    contracts,
    dashboard,
    discovery,
    knowledge,
    leads,
    notifications,
    opportunities,
    scripts,
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
api_router.include_router(scripts.router)
api_router.include_router(knowledge.router)
api_router.include_router(discovery.router)
api_router.include_router(assistant.router)
api_router.include_router(contracts.router)
