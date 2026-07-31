from fastapi import APIRouter

from backend.api import editions, exports, plans, projects, reviews, sources

api_router = APIRouter()
api_router.include_router(projects.router)
api_router.include_router(sources.router)
api_router.include_router(plans.router)
api_router.include_router(editions.router)
api_router.include_router(reviews.router)
api_router.include_router(exports.router)
