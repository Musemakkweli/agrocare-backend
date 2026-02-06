from sqlalchemy import Column, Integer, String, Enum, Boolean, Text, Float, JSON
from database import Base
import enum

# ===== ENUMS =====
class Role(str, enum.Enum):
    farmer = "farmer"
    agronomist = "agronomist"
    donor = "donor"
    leader = "leader"
    finance = "finance"

class DonorType(str, enum.Enum):
    person = "person"
    organization = "organization"

# ===== USER MODEL =====
class User(Base):
    __tablename__ = "users"

    # ===== General fields =====
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)  # Store hashed passwords in production
    role = Column(Enum(Role), nullable=False)
    
    # ===== Profile completion & approval =====
    is_approved = Column(Boolean, default=False)   # Admin approves the user
    is_profile_completed = Column(Boolean, default=False)  # User completes profile after login

    # ===== Role-specific fields =====
    farm_location = Column(String, nullable=True)    # farmer
    crop_type = Column(String, nullable=True)        # farmer
    expertise = Column(String, nullable=True)        # agronomist
    license = Column(String, nullable=True)          # agronomist
    phone = Column(String, nullable=True)            # all roles
    org_name = Column(String, nullable=True)         # donor organization
    funding = Column(String, nullable=True)          # donor organization
    donor_type = Column(Enum(DonorType), nullable=True)  # donor
    leader_title = Column(String, nullable=True)     # leader
    district = Column(String, nullable=True)         # leader
    department = Column(String, nullable=True)       # finance


class Program(Base):
    __tablename__ = "programs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    location = Column(String(255), nullable=False)  # <-- necessary
    district = Column(String(255), nullable=False)
    goal = Column(Float, default=0)
    raised = Column(Float, default=0)
    status = Column(String(100))

    

class Donation(Base):
    __tablename__ = "donations"

    id = Column(Integer, primary_key=True, index=True)
    program_id = Column(Integer, nullable=False)
    donor_name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    payment_method = Column(String, nullable=False)
    card_info = Column(JSON, nullable=True)        # For Visa/Mastercard
    mobile_number = Column(String, nullable=True)  # For MTN/Airtel
    bank_details = Column(JSON, nullable=True)     # For Bank transfers
