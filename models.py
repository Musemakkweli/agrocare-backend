from sqlalchemy import Column, Integer, String, Boolean, Enum, Float, ForeignKey, Date, DateTime, Text, JSON, func, TIMESTAMP,Index 
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
    password = Column(String, nullable=False)
    role = Column(Enum(Role), nullable=False)
    chat_history = relationship("AIChatHistory", back_populates="user")

    # ===== Profile picture =====
    profile_picture = Column(String, nullable=True)

    # ===== Profile completion & approval =====
    is_approved = Column(Boolean, default=False)
    is_profile_completed = Column(Boolean, default=False)

    # ===== Role-specific fields =====
    farm_location = Column(String, nullable=True)
    crop_type = Column(String, nullable=True)
    expertise = Column(String, nullable=True)
    license = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    org_name = Column(String, nullable=True)
    funding = Column(String, nullable=True)
    donor_type = Column(Enum(DonorType), nullable=True)
    leader_title = Column(String, nullable=True)
    district = Column(String, nullable=True)
    department = Column(String, nullable=True)

    # ===== Notifications relationship =====
    notifications = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan"
    )
        # Relationship with ActivityHistory
    activities = relationship(
        "ActivityHistory",
        back_populates="user",
        cascade="all, delete"
    )

class Program(Base):
    __tablename__ = "programs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    location = Column(String(255), nullable=False)
    district = Column(String(255), nullable=False)
    goal = Column(Float, default=0)
    raised = Column(Float, default=0)
    status = Column(String(100), default="Funding Open")
    
    # New fields that match your ALTER TABLE statements
    icon = Column(String(50), default="seedling")
    start_date = Column(String(50), nullable=True)
    end_date = Column(String(50), nullable=True)
    farmers = Column(Integer, default=0)
    progress = Column(Integer, default=0)
    
    # Timestamp fields matching your SQL
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
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

class PublicComplaint(Base):
    __tablename__ = "public_complaints"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    email = Column(String(100), nullable=True)
    title = Column(String(200), nullable=False)
    type = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)
    location = Column(String(200), nullable=False)
    image = Column(String(500), nullable=True)  # Supabase URL
    urgent = Column(Boolean, default=False)
    status = Column(Enum(ComplaintStatus), default=ComplaintStatus.Pending)
    
    # Tracking
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<PublicComplaint {self.id} - {self.name}>"
    
# Add these enums with your other enums
class SupportCategory(str, enum.Enum):
    tools = "tools"
    fertilizer = "fertilizer"
    seeds = "seeds"
    irrigation = "irrigation"
    other = "other"

class SupportStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"

# Add this model with your other models
class SupportRequest(Base):
    __tablename__ = "support_requests"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    donor = Column(String(100), nullable=False)
    amount = Column(Float, nullable=False)
    message = Column(Text, nullable=False)
    name = Column(String(100), nullable=False)
    contact = Column(String(100), nullable=False)
    category = Column(Enum(SupportCategory), nullable=False, default=SupportCategory.other)
    status = Column(Enum(SupportStatus), nullable=False, default=SupportStatus.pending)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Optional: if user is logged in
    
    # Tracking
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<SupportRequest {self.id} - {self.title}>"

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), nullable=False)  # 'farmer', 'admin', etc.
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50), nullable=False)  # 'complaint_update', 'system_alert', etc.
    related_id = Column(Integer, nullable=True)
    is_read = Column(Boolean, default=False)
    priority = Column(String(20), default='normal')
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    action_url = Column(String(255), nullable=True)
    extra_data = Column(JSON, nullable=True)  # renamed from 'metadata'

    user = relationship("User", back_populates="notifications")


class PasswordChangeOTP(Base):
    __tablename__ = "password_change_otps"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    otp_code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ActivityType(str, enum.Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    PROFILE_UPDATE = "profile_update"
    PASSWORD_CHANGE = "password_change"
    HARVEST_ADDED = "harvest_added"
    HARVEST_UPDATED = "harvest_updated"
    HARVEST_DELETED = "harvest_deleted"
    PEST_REPORT_ADDED = "pest_report_added"
    PEST_REPORT_UPDATED = "pest_report_updated"
    COMPLAINT_ADDED = "complaint_added"
    COMPLAINT_UPDATED = "complaint_updated"
    SETTINGS_CHANGED = "settings_changed"
    LANGUAGE_CHANGED = "language_changed"
    THEME_CHANGED = "theme_changed"


class ActivityStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
# =========================
# ACTIVITY HISTORY MODEL
# =========================
class ActivityHistory(Base):
    __tablename__ = "activity_history"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    activity_type = Column(String(50), nullable=False, index=True)
    description = Column(Text, nullable=False)

    # ✅ FIXED HERE
    activity_metadata = Column(JSON, default=dict)

    status = Column(String(20), default="success")

    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    device = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True),
                        server_default=func.now(),
                        nullable=False,
                        index=True)

    updated_at = Column(DateTime(timezone=True),
                        onupdate=func.now())

    user = relationship("User", back_populates="activities")

    __table_args__ = (
        Index('idx_user_activity_created',
              'user_id',
              'activity_type',
              'created_at'),
        Index('idx_user_created',
              'user_id',
              'created_at'),
    )

class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    program = Column(String(255))
    type = Column(String(50))  # complaint, feedback, incident
    description = Column(Text)
    status = Column(String(50), default="pending")  # pending, resolved, rejected
    priority = Column(String(50), default="normal")  # low, normal, high, critical
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationship
    user_id = Column(Integer, ForeignKey("users.id"))
    submitted_by = relationship("User")