from fastapi import APIRouter
from .endpoints import (
    notebooks_router,
    cells_router,
    websocket_router,
    chat_router
)

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(notebooks_router, prefix="/notebooks", tags=["notebooks"])
api_router.include_router(cells_router, tags=["cells"])  # Already includes /notebooks prefix in routes
api_router.include_router(websocket_router, tags=["websocket"])
api_router.include_router(chat_router, prefix="/chat", tags=["chat"])

