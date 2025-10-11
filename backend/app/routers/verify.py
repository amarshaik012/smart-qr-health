from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from ..core.otp_utils import generate_otp, verify_otp

router = APIRouter(prefix="/p", tags=["Patient Verification"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/verify", response_class=HTMLResponse)
def verify_number_page(request: Request):
    return templates.TemplateResponse("verify_number.html", {"request": request})

@router.post("/send-otp", response_class=HTMLResponse)
def send_otp(request: Request, phone: str = Form(...)):
    generate_otp(phone)
    return templates.TemplateResponse(
        "verify_otp.html", {"request": request, "phone": phone, "message": "OTP sent successfully!"}
    )

@router.post("/verify-otp", response_class=HTMLResponse)
def verify_otp_page(request: Request, phone: str = Form(...), otp: str = Form(...)):
    if verify_otp(phone, otp):
        return RedirectResponse(url=f"/p/{phone}/details", status_code=303)
    return templates.TemplateResponse(
        "verify_otp.html", {"request": request, "phone": phone, "error": "Invalid OTP. Try again!"}
    )