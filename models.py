from sqlalchemy import Column, Integer, String, Boolean, Enum, Float, ForeignKey, Date, DateTime, Text, JSON, func, TIMESTAMP
from sqlalchemy.orm import relationship
from database import Base
import datetime
import enum


# ===== ENUMS =====
class Role(str, enum.Enum):
    farmer = "farmer"
    agronomist = "agronomist"
    donor = "donor"
    leader = "leader"
    finance = "finance"
    admin = "admin"


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
    chat_history = relationship("AIChatHistory", back_populates="user")
    
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
    location = Column(String(255), nullable=False)
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
    card_info = Column(JSON, nullable=True)
    mobile_number = Column(String, nullable=True)
    bank_details = Column(JSON, nullable=True)


class Field(Base):
    __tablename__ = "fields"

    id = Column(Integer, primary_key=True, index=True)
    farmer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    area = Column(Float, nullable=True)
    crop_type = Column(String, nullable=True)
    location = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Harvest(Base):
    __tablename__ = "harvests"

    id = Column(Integer, primary_key=True, index=True)
    farmer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    field_id = Column(Integer, ForeignKey("fields.id"), nullable=False)
    crop_type = Column(String, nullable=True)
    harvest_date = Column(Date, nullable=False)
    status = Column(String, default="upcoming")
    created_at = Column(DateTime, server_default=func.now())

    field = relationship("Field", backref="harvests")


class PestAlert(Base):
    __tablename__ = "pest_alerts"

    id = Column(Integer, primary_key=True, index=True)
    farmer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    field_id = Column(Integer, ForeignKey("fields.id"), nullable=False)
    pest_type = Column(String, nullable=False)
    severity = Column(String, nullable=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class ComplaintStatus(str, enum.Enum):
    Pending = "Pending"
    Resolved = "Resolved"
    OnHold = "On Hold"


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String, nullable=False)
    type = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    location = Column(String, nullable=False)

    image = Column(String)

    status = Column(
        Enum(ComplaintStatus, name="complaint_status"),
        default=ComplaintStatus.Pending
    )

    created_at = Column(TIMESTAMP, server_default=func.now())

    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)


class WeatherAlert(Base):
    __tablename__ = "weather_alerts"

    id = Column(Integer, primary_key=True, index=True)
    region = Column(String, nullable=False)
    alert_type = Column(String, nullable=False)
    message = Column(String, nullable=False)
    severity = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    created_by_admin_id = Column(Integer, ForeignKey("users.id"), nullable=False)


class AIChatHistory(Base):
    __tablename__ = "ai_chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    user_message = Column(Text, nullable=True)
    ai_response = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="chat_history")
