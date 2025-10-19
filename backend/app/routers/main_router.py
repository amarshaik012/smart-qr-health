from fastapi import APIRouter
from .pharmadesk import auth, dashboard, inventory, prescription, assistant

router = APIRouter(prefix="/pharmadesk", tags=["PharmaDesk"])
router.include_router(auth.router)
router.include_router(dashboard.router)
router.include_router(inventory.router)
router.include_router(prescription.router)
router.include_router(assistant.router)
