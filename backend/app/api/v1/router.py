from fastapi import APIRouter

from app.api.v1 import ai, auth, dashboard, leads, teams, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(teams.router)
api_router.include_router(dashboard.router)
api_router.include_router(ai.router)
api_router.include_router(leads.router)
