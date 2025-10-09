from pydantic import BaseModel, EmailStr
from typing import Optional

class PatientBase(BaseModel):
    name: str
    phone: str
    email: EmailStr
    gender: Optional[str] = None
    dob: Optional[str] = None  # ✅ add this

class PatientCreate(PatientBase):
    pass

class PatientResponse(PatientBase):
    id: int
    patient_uid: str
    qr_url: str

    class Config:
        orm_mode = True