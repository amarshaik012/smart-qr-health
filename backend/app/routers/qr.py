from fastapi import APIRouter
from ..core.qr_utils import generate_qr_image

router = APIRouter(prefix="/qr", tags=["QR Generator"])

@router.get("/{uid}")
def get_qr(uid: str):
    """Generate QR dynamically — works both locally & on Render."""
    return generate_qr_image(uid)