from pydantic import BaseModel, EmailStr
from typing import Optional

# ===== BASE =====
class BaseUser(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role: str  # Role is selected during registration
    phone: Optional[str] = None

    class Config:
        from_attributes = True

# ===== USER REGISTRATION SCHEMA =====
class UserRegister(BaseUser):
    pass  # Only basic info at registration

# ===== USER RESPONSE SCHEMA =====
class UserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: str
    is_approved: bool

    class Config:
        from_attributes = True

# ===== PROFILE COMPLETION SCHEMAS =====
# Farmer
class FarmerProfile(BaseModel):
    farm_location: str
    crop_type: str
    phone: Optional[str] = None

    class Config:
        from_attributes = True

# Agronomist
class AgronomistProfile(BaseModel):
    expertise: str
    license: str
    phone: Optional[str] = None

    class Config:
        from_attributes = True

# Donor
class DonorProfile(BaseModel):
    donor_type: str
    org_name: Optional[str] = None
    funding: Optional[str] = None
    phone: Optional[str] = None

    class Config:
        from_attributes = True

# Leader
class LeaderProfile(BaseModel):
    leader_title: str
    district: str
    phone: Optional[str] = None

    class Config:
        from_attributes = True

# Finance
class FinanceProfile(BaseModel):
    department: str
    phone: Optional[str] = None

    class Config:
        from_attributes = True

# ===== LOGIN =====
class UserLogin(BaseModel):
    email: EmailStr
    password: str

# ===== TOKEN =====
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

# ===== LOGIN RESPONSE WITH MESSAGE =====
class LoginResponseWithMessage(BaseModel):
    message: str
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class ProgramBase(BaseModel):
    title: str
    description: str
    location: str   
    district: str
    goal: float
    raised: float
    status: str



class ProgramCreate(ProgramBase):
    pass


class ProgramOut(ProgramBase):
    id: int

    class Config:
        from_attributes = True   # FastAPI modern (instead of orm_mode)
