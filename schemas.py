from pydantic import BaseModel, EmailStr,  root_validator
from typing import Optional
from datetime import datetime
from models import ComplaintStatus

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
    phone: str | None  
    role: str
    is_approved: bool
    is_profile_completed: bool 

    class Config:
        from_attributes = True

# ===== PROFILE COMPLETION SCHEMAS =====

# Existing FarmerProfile (used for input)
class FarmerProfile(BaseModel):
    farm_location: Optional[str]
    crop_type: Optional[str]
    phone: Optional[str]

# ✅ New response schema
class FarmerProfileResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    is_approved: bool
    is_profile_completed: bool 
    farm_location: Optional[str]
    crop_type: Optional[str]
    phone: Optional[str]

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

    # Optional: normalize donor_type to lowercase automatically
    @root_validator(pre=True)
    def normalize_donor_type(cls, values):
        donor_type = values.get("donor_type")
        if donor_type:
            values["donor_type"] = donor_type.lower()  # converts ORGANIZATION → organization
        return values

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

class UserLogin(BaseModel):
    identifier: str
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
    description: Optional[str] = None
    location: Optional[str] = None
    district: Optional[str] = None
    goal: float
    raised: float = 0
    status: Optional[str] = "active"


class ProgramCreate(ProgramBase):
    pass


class ProgramOut(ProgramBase):
    id: int

    class Config:
        from_attributes = True


# -------------------------
# Base donation info
# -------------------------
class DonationBase(BaseModel):
    program_id: int
    donor_name: str
    amount: float


# -------------------------
# Card payment
# -------------------------
class CardInfo(BaseModel):
    number: str
    name: str
    expiry: str


class DonationCard(DonationBase):
    payment_method: str = "card"
    card_info: CardInfo


# -------------------------
# Mobile payment (MoMo)
# -------------------------
class DonationMobile(DonationBase):
    payment_method: str = "mobile"
    mobile_number: str


# -------------------------
# Bank payment
# -------------------------
class BankDetails(BaseModel):
    bank_name: str
    account_name: str
    account_number: str


class DonationBank(DonationBase):
    payment_method: str = "bank"
    bank_details: BankDetails


# -------------------------
# Output schema
# -------------------------
class DonationOut(DonationBase):
    id: int
    payment_method: str
    card_info: CardInfo | None = None
    mobile_number: str | None = None
    bank_details: BankDetails | None = None

    class Config:
        from_attributes = True


class ComplaintBase(BaseModel):
    title: str
    type: str
    description: str
    location: str


class ComplaintCreate(ComplaintBase):
    created_by: int
    status: ComplaintStatus = ComplaintStatus.Pending


class ComplaintUpdate(ComplaintBase):
    status: ComplaintStatus


class ComplaintOut(ComplaintBase):
    id: int
    image: Optional[str]
    status: ComplaintStatus
    created_at: datetime
    created_by: int

    class Config:
        from_attributes = True