from fastapi import APIRouter

from app.routers import conversations, message_receipt_router
from app.routers.auth import router as auth_router
from app.routers.message_router import router as message_router
from app.routers.presence_router import router as presence_router
from app.routers.user_router import router as user_router
from app.routers.websocket_router import router as websocket_router
from app.routers.websocket_ticket_router import (
    router as websocket_ticket_router,
)

router = APIRouter(prefix="/api/v1")

router.include_router(auth_router)
router.include_router(user_router)
router.include_router(conversations.router)
router.include_router(message_router)
router.include_router(message_receipt_router.router)
router.include_router(message_receipt_router.conversation_router)
router.include_router(websocket_ticket_router)
router.include_router(websocket_router)
router.include_router(presence_router)
