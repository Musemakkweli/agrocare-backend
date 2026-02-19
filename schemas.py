from pydantic import BaseModel, EmailStr, root_validator,Field, field_validator
from typing import Any, Optional, List
from datetime import datetime, date
from models import ComplaintStatus
from datetime import datetime
from enum import Enum   # ✅ ADD THIS



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


class ChatRequest(BaseModel):
    message: str


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


class FieldBase(BaseModel):
    name: str
    area: Optional[float] = None
    crop_type: Optional[str] = None
    location: Optional[str] = None  # ✅ added location


class FieldCreate(FieldBase):
    user_id: int  # corresponds to farmer_id in DB


class FieldOut(FieldBase):
    id: int
    farmer_id: int

    class Config:
        from_attributes = True


class HarvestBase(BaseModel):
    farmer_id: int
    field_id: int
    crop_type: Optional[str]
    harvest_date: date
    status: Optional[str] = "upcoming"


# Schema for creating a new harvest
class HarvestCreate(HarvestBase):
    pass


# Schema for reading/output
class HarvestOut(HarvestBase):
    id: int

    class Config:
        from_attributes = True 


class PestAlertBase(BaseModel):
    farmer_id: int
    field_id: int
    pest_type: str
    severity: Optional[str] = None
    description: Optional[str] = None


class PestAlertCreate(PestAlertBase):
    pass


class PestAlertOut(PestAlertBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Base schema
class WeatherAlertBase(BaseModel):
    region: str
    alert_type: str
    message: str
    severity: Optional[str] = None


# For creating new alert (admin input)
class WeatherAlertCreate(WeatherAlertBase):
    created_by_admin_id: int  # admin ID


# For output/response
class WeatherAlertOut(WeatherAlertBase):
    id: int
    created_at: datetime
    created_by_admin_id: int

    class Config:
        from_attributes = True


class UserRoleUpdate(BaseModel):
    role: str  # "admin", "farmer", "leader", "donor", etc.

    class Config:
        from_attributes = True


class APIResponse(BaseModel):
    success: bool
    message: str
    data: Any
    

class AIChatHistoryCreate(BaseModel):
    user_id: int
    user_message: str
    ai_response: str
    image_url: Optional[str] = None


class AIChatHistoryOut(BaseModel):
    id: int
    user_id: int
    user_message: str
    ai_response: str
    image_url: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
# Public Complaint Schemas
class PublicComplaintBase(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    title: str
    type: str
    description: str
    location: str
    urgent: bool = False

class PublicComplaintCreate(PublicComplaintBase):
    pass

class PublicComplaintOut(PublicComplaintBase):
    id: int
    image: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
# Add to your schemas.py

class ProfileUpdate(BaseModel):
    # Common fields
    fullname: Optional[str] = None
    phone: Optional[str] = None
    
    # Farmer fields
    farm_location: Optional[str] = None
    crop_type: Optional[str] = None
    district: Optional[str] = None
    
    # Agronomist fields
    expertise: Optional[str] = None
    license: Optional[str] = None
    
    # Donor fields
    org_name: Optional[str] = None
    funding: Optional[str] = None
    donor_type: Optional[str] = None
    
    # Leader fields
    leader_title: Optional[str] = None
    
    # Finance fields
    department: Optional[str] = None

class ProfileUpdateResponse(BaseModel):
    message: str
    is_profile_completed: bool

class UserProfileResponse(BaseModel):
    id: int
    fullname: str
    email: str
    phone: Optional[str] = None
    role: str
    is_approved: bool
    is_profile_completed: bool
    
    # Optional role-specific fields
    farm_location: Optional[str] = None
    crop_type: Optional[str] = None
    district: Optional[str] = None
    expertise: Optional[str] = None
    license: Optional[str] = None
    org_name: Optional[str] = None
    funding: Optional[str] = None
    donor_type: Optional[str] = None
    leader_title: Optional[str] = None
    department: Optional[str] = None

    class Config:
        from_attributes = True



# Enums for schemas (match your model enums)
class SupportCategory(str, Enum):
    tools = "tools"
    fertilizer = "fertilizer"
    seeds = "seeds"
    irrigation = "irrigation"
    other = "other"


class SupportStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# Base Support Request Schema
class SupportRequestBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    donor: Optional[str] = None
    amount: float = Field(..., gt=0)
    message: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    contact: str = Field(..., min_length=1)
    category: SupportCategory = SupportCategory.other

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError("Amount must be greater than 0")
        return v


# Schema for creating support request (without image)
class SupportRequestCreate(SupportRequestBase):
    user_id: Optional[int] = None


# Schema for creating support request with image
class SupportRequestCreateWithImage(SupportRequestCreate):
    image_url: Optional[str] = None


# Schema for updating support request
class SupportRequestUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    donor: Optional[str] = None
    amount: Optional[float] = Field(None, gt=0)
    message: Optional[str] = Field(None, min_length=1)
    name: Optional[str] = Field(None, min_length=1)
    contact: Optional[str] = Field(None, min_length=1)
    category: Optional[SupportCategory] = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Amount must be greater than 0")
        return v


# Schema for updating status only
class SupportRequestStatusUpdate(BaseModel):
    status: SupportStatus


# Schema for response (output)
class SupportRequestOut(BaseModel):
    id: int
    title: str
    donor: Optional[str] = None
    amount: float
    message: str
    name: str
    contact: str
    category: SupportCategory
    status: SupportStatus
    user_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


# Schema for paginated response
class PaginatedSupportResponse(BaseModel):
    success: bool
    count: int
    total: int
    page: int
    pages: int
    data: List[SupportRequestOut]


# Schema for single response
class SingleSupportResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    data: Optional[SupportRequestOut] = None


# Schema for delete response
class DeleteResponse(BaseModel):
    success: bool
    message: str


# Category stats schema
class CategoryStats(BaseModel):
    category: SupportCategory
    count: int
    total_amount: float


# Overview stats schema
class OverviewStats(BaseModel):
    total_requests: int
    total_amount: float
    pending: int
    approved: int
    rejected: int


# Recent request schema
class RecentRequest(BaseModel):
    id: int
    title: str
    amount: float
    status: SupportStatus
    created_at: Optional[datetime] = None


# Statistics response schema
class SupportStatsResponse(BaseModel):
    success: bool
    data: dict
