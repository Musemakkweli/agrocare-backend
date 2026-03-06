from random import random
import uuid 
import os
import time
from fastapi.responses import JSONResponse   
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File,Form,Path, Request
from fastapi import Query 
from supabase import create_client, Client
from sqlalchemy.orm import Session
from sqlalchemy import and_
from fastapi.security import OAuth2PasswordBearer
from services.notification_service import NotificationService
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta, date
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import or_
from typing import List
from database import Base, engine, SessionLocal
import models
import schemas
import random
import httpx
from typing import Optional
from dotenv import load_dotenv
from models import AIChatHistory, Complaint, ComplaintStatus, Report, User
from services.activity_logger import log_activity
load_dotenv()  # load variables from .env

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BUCKET_NAME = os.getenv("BUCKET_NAME")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ======================
# Setup FastAPI app first
# ======================
app = FastAPI(title="AgroCare Backend 🚀")

# ======================
# CORS Configuration
# ======================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================
# Create tables
# ======================
Base.metadata.create_all(bind=engine)

# ======================
# Security config, endpoints, etc.
# ======================
SECRET_KEY = "supersecretkey123"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# CryptContext with argon2 as primary, bcrypt as deprecated for auto-migration
# Existing bcrypt hashes can be verified, new passwords use argon2
# On successful login with old bcrypt hash, it's automatically rehashed to argon2
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="bcrypt")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.environ.get("PORT", 8000))  # Use Render-assigned port
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)


# ======================
# Password Helpers
# ======================
# Note: Updated password functions are defined below (around line 160) with proper encoding handling

# Old implementations removed to prevent conflicts


# ======================
# Token Helpers
# ======================
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ======================
# DB Dependency
# ======================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ======================
# Get current logged user
# ======================
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):

    credentials_exception = HTTPException(401, "Invalid authentication")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise credentials_exception

    return user


# ======================
# Root
# ======================
@app.get("/")
def root():
    return {"message": "AgroCare Backend running 🚀"}

# ======================
# Password utilities
# ======================

def hash_password(password: str) -> str:
    # Hash password with argon2
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    # Verify password with argon2
    return pwd_context.verify(plain, hashed)


# ======================
# Register
# ======================
@app.post("/register", response_model=schemas.UserResponse)
def register_user(user: schemas.UserRegister, db: Session = Depends(get_db)):

    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing:
        raise HTTPException(400, "Email already registered")

    new_user = models.User(
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        password=hash_password(user.password),
        role=user.role,
        is_approved=False  # All new users need approval
    )

    db.add(new_user)
    db.flush()  # Get user ID before committing

    # ===== CREATE REGISTRATION NOTIFICATIONS =====
    try:
        from services.notification_service import NotificationService
        
        # 1. Send welcome notification to the new user (role-specific message)
        welcome_messages = {
            "farmer": "Thank you for joining as a Farmer. Start reporting your farm issues!",
            "agronomist": "Welcome Agronomist! You'll receive complaints to review and provide solutions.",
            "donor": "Thank you for your generosity! You'll be notified about farmers in need.",
            "leader": "Welcome Leader! You'll oversee community agricultural activities.",
            "finance": "Welcome to the Finance team! You'll handle transactions and budgeting.",
            "admin": "Welcome Admin! You have full system access."
        }
        
        welcome_message = welcome_messages.get(
            user.role, 
            f"Thank you for joining AgroCare as a {user.role}."
        )
        
        NotificationService.create_notification(
            db=db,
            user_id=new_user.id,
            role=new_user.role,
            title="🎉 Welcome to AgroCare!",
            message=f"Hello {new_user.full_name}! {welcome_message} Your account is pending approval.",
            type="welcome",
            priority="normal",
            action_url="/dashboard",
            extra_data={
                "user_id": new_user.id,
                "role": new_user.role,
                "needs_approval": True
            }
        )
        print(f"✅ Welcome notification sent to new {user.role}: {new_user.id}")
        
        # 2. Get all admin users (admins need to approve all registrations)
        admins = db.query(models.User).filter(models.User.role == "admin").all()
        
        # 3. Role-specific notification titles and priorities
        role_titles = {
            "farmer": "👨‍🌾 New Farmer Registration",
            "agronomist": "🌱 New Agronomist Registration",
            "donor": "💰 New Donor Registration",
            "leader": "⭐ New Leader Registration",
            "finance": "📊 New Finance Team Member",
            "admin": "🔐 New Admin Registration"
        }
        
        role_priorities = {
            "farmer": "normal",
            "agronomist": "high",  # Agronomists are important for complaints
            "donor": "normal",
            "leader": "high",      # Leaders need quick approval
            "finance": "normal",
            "admin": "critical"     # Admin registrations are highest priority
        }
        
        title = role_titles.get(user.role, "👤 New User Registration")
        priority = role_priorities.get(user.role, "normal")
        
        # 4. Notify admins about new registration
        admin_count = 0
        for admin in admins:
            # Skip if admin is the new user (rare case)
            if admin.id == new_user.id:
                continue
                
            # Custom message based on role
            role_messages = {
                "farmer": f"New farmer needs approval: {new_user.full_name} from {new_user.location if hasattr(new_user, 'location') else 'Unknown'}",
                "agronomist": f"New agronomist registered: {new_user.full_name}. They can now review complaints.",
                "donor": f"New donor registered: {new_user.full_name}. Ready to support farmers.",
                "leader": f"New community leader registered: {new_user.full_name}. Requires immediate review.",
                "finance": f"New finance team member: {new_user.full_name}. Needs access to financial tools.",
                "admin": f"⚠️ NEW ADMIN REGISTRATION: {new_user.full_name} ({new_user.email}). VERIFY IMMEDIATELY!"
            }
            
            message = role_messages.get(
                user.role, 
                f"New {user.role} registered: {new_user.full_name} ({new_user.email})"
            )
            
            NotificationService.create_notification(
                db=db,
                user_id=admin.id,
                role="admin",
                title=title,
                message=message,
                type="user_registered",
                related_id=new_user.id,
                priority=priority,
                action_url=f"/admin/users/{new_user.id}",
                extra_data={
                    "user_id": new_user.id,
                    "user_name": new_user.full_name,
                    "user_email": new_user.email,
                    "user_role": user.role,
                    "needs_approval": True,
                    "priority": priority
                }
            )
            admin_count += 1
        
        print(f"✅ Registration notifications sent to {admin_count} admins")
        
        # 5. For specific roles, notify other relevant users
        
        # If new agronomist registered, notify leaders too
        if user.role == "agronomist":
            leaders = db.query(models.User).filter(models.User.role == "leader").all()
            for leader in leaders:
                NotificationService.create_notification(
                    db=db,
                    user_id=leader.id,
                    role="leader",
                    title="🌱 New Agronomist Available",
                    message=f"New agronomist {new_user.full_name} has registered and will help with farm complaints.",
                    type="team_update",
                    related_id=new_user.id,
                    priority="normal",
                    action_url=f"/team/{new_user.id}"
                )
        
        # If new donor registered, notify finance team
        elif user.role == "donor":
            finance_team = db.query(models.User).filter(models.User.role == "finance").all()
            for finance in finance_team:
                NotificationService.create_notification(
                    db=db,
                    user_id=finance.id,
                    role="finance",
                    title="💰 New Donor Registered",
                    message=f"New donor {new_user.full_name} has registered. Ready for financial tracking.",
                    type="donor_update",
                    related_id=new_user.id,
                    priority="normal",
                    action_url=f"/donors/{new_user.id}"
                )
        
        # If new leader registered, notify all admins (already done) and agronomists
        elif user.role == "leader":
            agronomists = db.query(models.User).filter(models.User.role == "agronomist").all()
            for agronomist in agronomists:
                NotificationService.create_notification(
                    db=db,
                    user_id=agronomist.id,
                    role="agronomist",
                    title="⭐ New Community Leader",
                    message=f"New leader {new_user.full_name} has joined. They'll coordinate community efforts.",
                    type="team_update",
                    related_id=new_user.id,
                    priority="normal",
                    action_url=f"/leaders/{new_user.id}"
                )
        
    except Exception as e:
        print(f"⚠️ Failed to create registration notifications: {str(e)}")
        import traceback
        traceback.print_exc()
        # Don't fail the registration if notifications fail

    db.commit()
    db.refresh(new_user)

    return new_user
# ======================
# Login (email OR phone)
# ======================
@app.post("/login", response_model=schemas.LoginResponseWithMessage)
def login_user(
    user: schemas.UserLogin, 
    request: Request,  # To get IP
    db: Session = Depends(get_db)
):
    # Find user by email or phone
    db_user = db.query(models.User).filter(
        or_(
            models.User.email == user.identifier,
            models.User.phone == user.identifier
        )
    ).first()

    if not db_user or not verify_password(user.password, db_user.password):
        # Optionally log failed login attempts
        try:
            from services.activity_logger import log_activity
            log_activity(
                db=db,
                user_id=db_user.id if db_user else None,
                activity_type="login",
                description=f"Failed login attempt for identifier '{user.identifier}'",
                metadata={"ip": request.client.host if request.client else "Unknown"},
                status="failed"
            )
        except Exception:
            pass

        raise HTTPException(400, "Invalid email or phone or password")

    # Check approval status - Farmers don't need approval
    if not db_user.is_approved and db_user.role != "farmer":
        raise HTTPException(403, "User not approved yet")
    
    # Log warning for unapproved farmers (optional)
    if not db_user.is_approved and db_user.role == "farmer":
        try:
            from services.activity_logger import log_activity
            log_activity(
                db=db,
                user_id=db_user.id,
                activity_type="login",
                description=f"Farmer logged in without approval",
                metadata={"ip": request.client.host if request.client else "Unknown"},
                status="warning"
            )
        except Exception:
            pass

    # Automatically rehash old bcrypt passwords to argon2
    if pwd_context.needs_update(db_user.password):
        db_user.password = hash_password(user.password)
        db.commit()

    token = create_access_token({"id": db_user.id})

    # ===== LOG ACTIVITY =====
    try:
        from services.activity_logger import log_activity

        log_activity(
            db=db,
            user_id=db_user.id,
            activity_type="login",
            description="User logged in successfully",
            metadata={
                "ip": request.client.host if request.client else "Unknown",
                "user_agent": request.headers.get("user-agent", "Unknown")[:100]
            },
            status="success"
        )

    except Exception as e:
        print(f"⚠️ Activity logging error: {str(e)}")

    # ===== CREATE LOGIN NOTIFICATIONS =====
    try:
        from services.notification_service import NotificationService
        
        # Get client info
        client_ip = request.client.host if request.client else "Unknown"
        user_agent = request.headers.get("user-agent", "Unknown")[:100]
        login_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. Login notification
        NotificationService.create_notification(
            db=db,
            user_id=db_user.id,
            role=db_user.role,
            title="🔐 New Login",
            message=f"Logged in at {login_time} from {client_ip}",
            type="login_alert",
            priority="low",
            action_url="/dashboard",
            extra_data={
                "ip": client_ip,
                "time": login_time,
                "user_agent": user_agent
            }
        )
        
        # 2. Profile reminder
        if not db_user.is_profile_completed:
            NotificationService.create_notification(
                db=db,
                user_id=db_user.id,
                role=db_user.role,
                title="📝 Complete Your Profile",
                message="Please complete your profile to get the most out of AgroCare.",
                type="profile_reminder",
                priority="normal",
                action_url="/profile/edit"
            )
        
        # 3. Role-specific notifications
        if db_user.role == "admin":
            # For admin: show pending approvals (excluding farmers since they auto-approve)
            pending = db.query(models.User).filter(
                models.User.is_approved == False,
                models.User.role != "farmer"  # Exclude farmers from pending count
            ).count()
            
            if pending > 0:
                NotificationService.create_notification(
                    db=db,
                    user_id=db_user.id,
                    role="admin",
                    title="⏳ Pending Approvals",
                    message=f"You have {pending} users awaiting approval (farmers auto-approved).",
                    type="pending_approvals",
                    priority="high",
                    action_url="/admin/approvals"
                )
        
        elif db_user.role == "agronomist":
            pending_complaints = db.query(models.Complaint).filter(
                models.Complaint.status == "pending"
            ).count()
            
            if pending_complaints > 0:
                NotificationService.create_notification(
                    db=db,
                    user_id=db_user.id,
                    role="agronomist",
                    title="🌱 Pending Complaints",
                    message=f"{pending_complaints} complaints need your review.",
                    type="pending_complaints",
                    priority="high",
                    action_url="/complaints/pending"
                )
        
        elif db_user.role == "farmer" and not db_user.is_approved:
            # For unapproved farmers: notify them they're auto-approved
            NotificationService.create_notification(
                db=db,
                user_id=db_user.id,
                role="farmer",
                title="✅ Auto-Approved Account",
                message="Your farmer account is automatically approved. You can start using AgroCare immediately!",
                type="account_approved",
                priority="normal",
                action_url="/dashboard"
            )
            
            # Optionally auto-approve farmers
            db_user.is_approved = True
            db.commit()
        
    except Exception as e:
        print(f"⚠️ Login notification error: {str(e)}")
        import traceback
        traceback.print_exc()

    return {
        "message": "Successfully logged in",
        "access_token": token,
        "token_type": "bearer",
        "user": db_user,
        "is_profile_completed": db_user.is_profile_completed
    }
# ======================
# Helper function
# ======================
def update_profile(user_id: int, profile, db: Session):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    # Update fields from the request
    for field, value in profile.dict(exclude_unset=True).items():
        setattr(user, field, value)

    # ✅ Mark profile as completed
    user.is_profile_completed = True

    db.commit()
    db.refresh(user)
    return user

# ======================
# Profile Routes (updated response)
# ======================

@app.put("/profile/farmer/{user_id}", response_model=schemas.FarmerProfileResponse)
def farmer_profile(user_id: int, profile: schemas.FarmerProfile, db: Session = Depends(get_db)):
    user = update_profile(user_id, profile, db)
    return schemas.FarmerProfileResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        is_approved=user.is_approved,
        is_profile_completed=user.is_profile_completed,  # ✅ include this
        farm_location=user.farm_location,
        crop_type=user.crop_type,
        phone=user.phone
    )
# Add this GET endpoint to fetch farmer profile
@app.get("/profile/farmer/{user_id}", response_model=schemas.FarmerProfileResponse)
def get_farmer_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return schemas.FarmerProfileResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        is_approved=user.is_approved,
        is_profile_completed=user.is_profile_completed,
        farm_location=user.farm_location,
        crop_type=user.crop_type,
        phone=user.phone
    )

# ---------------------
# Agronomist

@app.put("/profile/agronomist/{user_id}", response_model=schemas.AgronomistProfile)
def agronomist_profile(user_id: int, profile: schemas.AgronomistProfile, db: Session = Depends(get_db)):
    user = update_profile(user_id, profile, db)
    return schemas.AgronomistProfile(
        expertise=user.expertise,
        license=user.license,
        phone=user.phone
    )

# ---------------------
# Donor
@app.put("/profile/donor/{user_id}", response_model=schemas.DonorProfile)
def donor_profile(user_id: int, profile: schemas.DonorProfile, db: Session = Depends(get_db)):
    # Normalize donor_type to lowercase to match DB enum
    if profile.donor_type:
        profile.donor_type = profile.donor_type.lower()

    try:
        # Use the helper to update fields AND mark profile_completed
        user = update_profile(user_id, profile, db)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ✅ Include profile_completed in the response if you want frontend to update localStorage
    return schemas.DonorProfile(
        donor_type=user.donor_type,
        org_name=user.org_name,
        funding=user.funding,
        phone=user.phone
    )

# ---------------------
# Leader
@app.put("/profile/leader/{user_id}", response_model=schemas.LeaderProfile)
def leader_profile(user_id: int, profile: schemas.LeaderProfile, db: Session = Depends(get_db)):
    user = update_profile(user_id, profile, db)
    return schemas.LeaderProfile(
        leader_title=user.leader_title,
        district=user.district,
        phone=user.phone
    )

# ---------------------
# Finance
@app.put("/profile/finance/{user_id}", response_model=schemas.FinanceProfile)
def finance_profile(user_id: int, profile: schemas.FinanceProfile, db: Session = Depends(get_db)):
    user = update_profile(user_id, profile, db)
    return schemas.FinanceProfile(
        department=user.department,
        phone=user.phone
    )

# ======================
# Admin
# ======================
@app.get("/users", response_model=list[schemas.UserResponse])
def get_users(db: Session = Depends(get_db)):
    return db.query(models.User).all()


@app.put("/users/approve/{user_id}", response_model=schemas.UserResponse)
def approve_user(user_id: int, db: Session = Depends(get_db)):

    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(404, "User not found")

    user.is_approved = True

    db.commit()
    db.refresh(user)

    return user

# PROGRAMS API
# =====================================

# GET all programs
@app.get("/api/programs", response_model=list[schemas.ProgramOut])
def get_programs(db: Session = Depends(get_db)):
    return db.query(models.Program).all()


# GET one program
@app.get("/api/programs/{program_id}", response_model=schemas.ProgramOut)
def get_program(program_id: int, db: Session = Depends(get_db)):
    program = db.query(models.Program).filter(models.Program.id == program_id).first()

    if not program:
        raise HTTPException(404, "Program not found")

    return program


# CREATE program
@app.post("/api/programs", response_model=schemas.ProgramOut)
def create_program(program: schemas.ProgramCreate, db: Session = Depends(get_db)):
    # Convert to dict
    program_data = program.dict()
    
    # Calculate initial progress
    if program_data.get('goal', 0) > 0 and program_data.get('raised', 0) > 0:
        program_data['progress'] = min(int((program_data['raised'] / program_data['goal']) * 100), 100)
    else:
        program_data['progress'] = 0
    
    # Set default icon if not provided
    if not program_data.get('icon'):
        program_data['icon'] = 'seedling'
    
    # Set default status if not provided
    if not program_data.get('status'):
        program_data['status'] = 'Funding Open'
    
    new_program = models.Program(**program_data)

    db.add(new_program)
    db.commit()
    db.refresh(new_program)

    return new_program



# UPDATE program
@app.put("/api/programs/{program_id}", response_model=schemas.ProgramOut)
def update_program(program_id: int, data: schemas.ProgramCreate, db: Session = Depends(get_db)):
    program = db.query(models.Program).filter(models.Program.id == program_id).first()

    if not program:
        raise HTTPException(404, "Program not found")

    for key, value in data.dict().items():
        setattr(program, key, value)

    db.commit()
    db.refresh(program)

    return program


# DELETE program
@app.delete("/api/programs/{program_id}")
def delete_program(program_id: int, db: Session = Depends(get_db)):
    program = db.query(models.Program).filter(models.Program.id == program_id).first()

    if not program:
        raise HTTPException(404, "Program not found")

    db.delete(program)
    db.commit()

    return {"message": "Program deleted"}

# -------------------------
# Get program by ID

@app.get("/api/programs/{program_id}", response_model=schemas.ProgramOut)
def get_program(program_id: int, db: Session = Depends(get_db)):
    program = db.query(models.Program).filter(models.Program.id == program_id).first()
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")
    return program


# -------------------------
# Card donation
# -------------------------
@app.post("/api/donations/card", response_model=schemas.DonationOut)
def donate_card(donation: schemas.DonationCard, db: Session = Depends(get_db)):
    program = db.query(models.Program).filter(
        models.Program.id == donation.program_id
    ).first()
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")

    new_donation = models.Donation(
        program_id=donation.program_id,
        donor_name=donation.donor_name,
        amount=donation.amount,
        payment_method="card",
        card_info=donation.card_info.dict(),  # ✅ convert Pydantic model to dict
    )

    db.add(new_donation)
    program.raised += donation.amount
    db.commit()
    db.refresh(new_donation)
    db.refresh(program)
    return new_donation


# -------------------------
# Mobile donation
# -------------------------
@app.post("/api/donations/mobile", response_model=schemas.DonationOut)
def donate_mobile(donation: schemas.DonationMobile, db: Session = Depends(get_db)):
    program = db.query(models.Program).filter(
        models.Program.id == donation.program_id
    ).first()
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")

    new_donation = models.Donation(
        program_id=donation.program_id,
        donor_name=donation.donor_name,
        amount=donation.amount,
        payment_method="mobile",
        mobile_number=donation.mobile_number,
    )

    db.add(new_donation)
    program.raised += donation.amount
    db.commit()
    db.refresh(new_donation)
    db.refresh(program)
    return new_donation


# -------------------------
# Bank donation
# -------------------------
@app.post("/api/donations/bank", response_model=schemas.DonationOut)
def donate_bank(donation: schemas.DonationBank, db: Session = Depends(get_db)):
    program = db.query(models.Program).filter(
        models.Program.id == donation.program_id
    ).first()
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")

    new_donation = models.Donation(
        program_id=donation.program_id,
        donor_name=donation.donor_name,
        amount=donation.amount,
        payment_method="bank",
        bank_details=donation.bank_details.dict(),  # ✅ convert Pydantic model to dict
    )

    db.add(new_donation)
    program.raised += donation.amount
    db.commit()
    db.refresh(new_donation)
    db.refresh(program)
    return new_donation


# Get all donations
# -------------------------
@app.get("/api/donations", response_model=list[schemas.DonationOut])
def get_all_donations(db: Session = Depends(get_db)):
    donations = db.query(models.Donation).all()
    return donations

# -------------------------
# Get donations by program
@app.get("/api/donations/by-program", response_model=list[schemas.DonationOut])
def get_donations_by_program(program_id: int, db: Session = Depends(get_db)):
    donations = db.query(models.Donation).filter(models.Donation.program_id == program_id).all()
    return donations

from datetime import date
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

# Farmer stats endpoint
@app.get("/farmer/{user_id}/stats")
def get_farmer_stats(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    total_fields = (
        db.query(models.Field)
        .filter(models.Field.farmer_id == user_id)
        .count()
    )

    upcoming_harvests = (
        db.query(models.Harvest)
        .filter(
            models.Harvest.farmer_id == user_id,
            models.Harvest.harvest_date > date.today()
        )
        .count()
    )

    pest_alerts = (
        db.query(models.Alert)
        .filter(
            models.Alert.farmer_id == user_id,
            models.Alert.type == "pest"
        )
        .count()
    )

    weather_alerts = (
        db.query(models.Alert)
        .filter(
            models.Alert.farmer_id == user_id,
            models.Alert.type == "weather"
        )
        .count()
    )

    return {
        "total_fields": total_fields,
        "upcoming_harvests": upcoming_harvests,
        "pest_alerts": pest_alerts,
        "weather_alerts": weather_alerts
    }

# Example crop health data (replace with real logic)

@app.get("/farmer/{user_id}/crop-health")
def get_crop_health(user_id: int, db: Session = Depends(get_db)):
    # Example: last 5 weeks
    data = []
    for i in range(1, 6):
        # Replace with actual computation per week
        data.append({"week": f"W{i}", "health": random.randint(50, 90)})
    return data

# complaints 
@app.post("/complaints", response_model=schemas.ComplaintOut)
def create_complaint(
    user_id: int = Form(...),
    title: str = Form(...),
    type: str = Form(...),
    description: str = Form(...),
    location: str = Form(...),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    image_url = None
    if image and image.filename:  # Check if image exists and has filename
        filename = f"{int(time.time())}_{image.filename}"
        content = image.file.read()

        try:
            supabase.storage.from_(BUCKET_NAME).upload(filename, content)
            image_url = supabase.storage.from_(BUCKET_NAME).get_public_url(filename)
        except Exception as e:
            # Log error but don't fail the complaint creation
            print(f"⚠️ Image upload failed: {str(e)}")
            # Continue without image

    # Create complaint
    complaint = models.Complaint(
        title=title,
        type=type,
        description=description,
        location=location,
        image=image_url,
        status=models.ComplaintStatus.Pending,
        created_by=user_id
    )

    db.add(complaint)
    db.flush()  # Get complaint.id before committing

    # ===== CREATE NOTIFICATIONS =====
    try:
        from services.notification_service import NotificationService
        
        # 1. Notify the user who created the complaint
        NotificationService.create_notification(
            db=db,
            user_id=user_id,
            role="farmer",
            title="✅ Complaint Submitted Successfully",
            message=f"Your complaint '{title}' has been submitted and is pending review.",
            type="complaint_created",
            related_id=complaint.id,
            priority="normal",
            action_url=f"/complaint/{complaint.id}",
            extra_data={"status": "pending", "complaint_type": type}
        )
        
        # 2. Get all admin users
        admins = db.query(models.User).filter(models.User.role == "admin").all()
        
        # 3. Notify all admins
        for admin in admins:
            # Determine priority based on complaint type
            priority = "high" if type in ["Pest Attack", "Theft", "Weather Damage"] else "normal"
            
            NotificationService.create_notification(
                db=db,
                user_id=admin.id,
                role="admin",
                title="🚨 New Complaint Requires Review",
                message=f"New {type} complaint: '{title}' from User #{user_id} at {location}",
                type="admin_alert",
                related_id=complaint.id,
                priority=priority,
                action_url=f"/admin/complaint/{complaint.id}",
                extra_data={
                    "complaint_type": type, 
                    "user_id": user_id,
                    "location": location
                }
            )
        
        # 4. If urgent, create high-priority notification for user
        if type in ["Pest Attack", "Theft"]:
            NotificationService.create_notification(
                db=db,
                user_id=user_id,
                role="farmer",
                title="⚠️ Urgent: Action Required",
                message=f"Your '{type}' complaint has been flagged as urgent. An officer will contact you soon.",
                type="urgent_alert",
                related_id=complaint.id,
                priority="high",
                action_url=f"/complaint/{complaint.id}",
                extra_data={"urgent": True, "complaint_type": type}
            )
        
        print(f"✅ Notifications created for complaint {complaint.id}")
        
    except Exception as e:
        # Log notification error but don't fail the complaint creation
        print(f"⚠️ Failed to create notifications: {str(e)}")
        import traceback
        traceback.print_exc()

    # Commit everything
    db.commit()
    db.refresh(complaint)
    
    return complaint

# Get complaints by user

@app.get("/complaints/user/{user_id}", response_model=List[schemas.ComplaintOut])
def get_complaints_by_user(user_id: int, db: Session = Depends(get_db)):
    # Query complaints for this user
    complaints = db.query(models.Complaint).filter(models.Complaint.created_by == user_id).all()
    
    if not complaints:
        raise HTTPException(status_code=404, detail="No complaints found for this user")
    
    return complaints

# Get all complaints (for admin)
@app.get("/complaints", response_model=List[schemas.ComplaintOut])
def get_all_complaints(db: Session = Depends(get_db)):
    complaints = db.query(models.Complaint).all()
    
    if not complaints:
        raise HTTPException(status_code=404, detail="No complaints found")
    
    return complaints

# Update complaint status 
@app.put("/complaints/{complaint_id}", response_model=schemas.ComplaintOut)
def update_complaint(
    complaint_id: int,
    user_id: int = Query(..., description="ID of the user updating the complaint"),  # Add this
    title: Optional[str] = Form(None),
    type: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    complaint = db.query(models.Complaint).filter(models.Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")

    # Store old values for notification
    old_values = {
        "title": complaint.title,
        "type": complaint.type,
        "description": complaint.description,
        "location": complaint.location,
        "image": complaint.image
    }
    
    # Track what changed
    changes = []
    
    # Update fields if provided
    if title is not None and title != complaint.title:
        complaint.title = title
        changes.append(f"title changed to '{title}'")
    
    if type is not None and type != complaint.type:
        complaint.type = type
        changes.append(f"type changed to '{type}'")
    
    if description is not None and description != complaint.description:
        complaint.description = description
        changes.append("description updated")
    
    if location is not None and location != complaint.location:
        complaint.location = location
        changes.append(f"location changed to '{location}'")

    # Handle image update
    image_updated = False
    if image and image.filename:
        try:
            filename = f"{int(time.time())}_{image.filename}"
            content = image.file.read()
            supabase.storage.from_(BUCKET_NAME).upload(filename, content)
            complaint.image = supabase.storage.from_(BUCKET_NAME).get_public_url(filename)
            changes.append("image updated")
            image_updated = True
        except Exception as e:
            print(f"⚠️ Image upload failed: {e}")

    db.flush()

    # ===== CREATE UPDATE NOTIFICATIONS =====
    try:
        from services.notification_service import NotificationService
        
        # Only send notification if something actually changed
        if changes:
            changes_text = ", ".join(changes)
            
            # 1. Always notify the complaint owner (if different from updater)
            if complaint.created_by != user_id:
                NotificationService.create_notification(
                    db=db,
                    user_id=complaint.created_by,
                    role="farmer",
                    title="📝 Complaint Updated",
                    message=f"Your complaint '{complaint.title}' was updated: {changes_text}",
                    type="complaint_updated",
                    related_id=complaint.id,
                    priority="normal",
                    action_url=f"/complaint/{complaint.id}",
                    extra_data={
                        "updated_by": user_id,
                        "changes": changes,
                        "old_values": old_values
                    }
                )
                print(f"✅ Update notification sent to complaint owner (User {complaint.created_by})")
            
            # 2. If the owner is the one updating, send them a confirmation
            else:
                NotificationService.create_notification(
                    db=db,
                    user_id=user_id,
                    role="farmer",
                    title="✅ Complaint Updated Successfully",
                    message=f"You updated your complaint: {changes_text}",
                    type="complaint_self_updated",
                    related_id=complaint.id,
                    priority="normal",
                    action_url=f"/complaint/{complaint.id}",
                    extra_data={"changes": changes}
                )
                print(f"✅ Self-update confirmation sent to User {user_id}")
            
            # 3. Notify admins about the update (except the updater if they're an admin)
            admins = db.query(models.User).filter(models.User.role == "admin").all()
            admin_count = 0
            for admin in admins:
                if admin.id != user_id:  # Don't notify the admin who made the update
                    NotificationService.create_notification(
                        db=db,
                        user_id=admin.id,
                        role="admin",
                        title="🔄 Complaint Updated",
                        message=f"Complaint '{complaint.title}' was updated by User #{user_id}: {changes_text}",
                        type="admin_alert",
                        related_id=complaint.id,
                        priority="normal",
                        action_url=f"/admin/complaint/{complaint.id}",
                        extra_data={
                            "updated_by": user_id,
                            "complaint_id": complaint.id,
                            "changes": changes
                        }
                    )
                    admin_count += 1
            
            print(f"✅ Update notifications sent to {admin_count} admins")
        
        else:
            print("ℹ️ No changes detected - no notifications sent")
            
    except Exception as e:
        print(f"⚠️ Failed to create update notifications: {str(e)}")
        import traceback
        traceback.print_exc()

    db.commit()
    db.refresh(complaint)
    return complaint

#Delete complaint 
@app.delete("/complaints/{complaint_id}", response_model=dict)
def delete_complaint(
    complaint_id: int, 
    user_id: int = Query(..., description="ID of the user deleting the complaint"),
    db: Session = Depends(get_db)
):
    complaint = db.query(models.Complaint).filter(models.Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    # Store complaint info
    complaint_info = {
        "id": complaint.id,
        "title": complaint.title,
        "created_by": complaint.created_by,
        "type": complaint.type,
        "location": complaint.location
    }
    
    # Delete the complaint
    db.delete(complaint)
    db.flush()

    # ===== FIXED NOTIFICATIONS =====
    try:
        from services.notification_service import NotificationService
        
        # FIX 1: ALWAYS notify the complaint owner (even if they deleted it themselves)
        NotificationService.create_notification(
            db=db,
            user_id=complaint_info["created_by"],
            role="farmer",
            title="🗑️ Complaint Deleted",
            message=f"Your complaint '{complaint_info['title']}' has been deleted." + 
                   (f" (Deleted by you)" if complaint_info["created_by"] == user_id else f" (Deleted by User #{user_id})"),
            type="complaint_deleted",
            related_id=complaint_info["id"],
            priority="normal",
            action_url=None,
            extra_data={
                "deleted_by": user_id,
                "deleted_by_self": complaint_info["created_by"] == user_id,
                "complaint_type": complaint_info["type"],
                "complaint_title": complaint_info["title"]
            }
        )
        print(f"✅ Deletion notification sent to complaint owner (User {complaint_info['created_by']})")
        
        # 2. Notify admins about deletion (except the deleter if they're an admin)
        admins = db.query(models.User).filter(models.User.role == "admin").all()
        admin_count = 0
        for admin in admins:
            if admin.id != user_id:  # Don't notify the admin who deleted
                NotificationService.create_notification(
                    db=db,
                    user_id=admin.id,
                    role="admin",
                    title="🗑️ Complaint Deleted",
                    message=f"Complaint '{complaint_info['title']}' was deleted by User #{user_id}",
                    type="admin_alert",
                    related_id=complaint_info["id"],
                    priority="normal",
                    action_url=None,
                    extra_data={
                        "deleted_by": user_id,
                        "complaint_title": complaint_info["title"],
                        "complaint_type": complaint_info["type"],
                        "location": complaint_info["location"]
                    }
                )
                admin_count += 1
        
        print(f"✅ Deletion notifications sent to {admin_count} admins")
        
    except Exception as e:
        print(f"⚠️ Failed to create deletion notifications: {str(e)}")
        import traceback
        traceback.print_exc()

    db.commit()

    return {
        "message": f"Complaint with ID {complaint_id} has been deleted successfully.",
        "notifications_sent": {
            "owner_notified": True,  # Always true now
            "admin_count": admin_count if 'admin_count' in locals() else 0
        }
    }

# Add a new field
@app.post("/fields", response_model=schemas.FieldOut)
def create_field(field: schemas.FieldCreate, db: Session = Depends(get_db)):
    new_field = models.Field(
        farmer_id=field.user_id,
        name=field.name,
        area=field.area,
        crop_type=field.crop_type,
        location=field.location  # ✅ added location
    )
    db.add(new_field)
    db.commit()
    db.refresh(new_field)
    return new_field

@app.get("/fields/user/{user_id}")
def get_fields(user_id: int, db: Session = Depends(get_db)):
    fields = db.query(models.Field).filter(models.Field.farmer_id == user_id).all()
    return fields
# delete a field

@app.delete("/fields/{field_id}")
def delete_field(field_id: int, db: Session = Depends(get_db)):
    try:
        # Fetch the field
        field = db.query(Field).filter(Field.id == field_id).first()
        if not field:
            raise HTTPException(status_code=404, detail="Field not found")

        # Delete the field
        db.delete(field)
        db.commit()
        return {"message": f"Field {field_id} deleted successfully"}

    except SQLAlchemyError as e:
        # Rollback if anything goes wrong
        db.rollback()
        # Optional: log the error for debugging
        print(f"Error deleting field: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    # update a field
@app.put("/fields/{field_id}")
def update_field(field_id: int, updated_field: schemas.FieldCreate, db: Session = Depends(get_db)):
    field = db.query(Field).filter(Field.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    for key, value in updated_field.dict(exclude_unset=True).items():
        setattr(field, key, value)
    db.commit()
    db.refresh(field)
    return field
# Get all fields (admin)
@app.get("/fields", response_model=List[schemas.FieldOut])
def get_all_fields(db: Session = Depends(get_db)):
    fields = db.query(models.Field).all()
    return fields


# Create a new harvest
# -------------------
@app.post("/harvests", response_model=schemas.HarvestOut)
def create_harvest(harvest: schemas.HarvestCreate, db: Session = Depends(get_db)):
    # Optional: check if field exists for this farmer
    field = db.query(models.Field).filter(
        models.Field.id == harvest.field_id,
        models.Field.farmer_id == harvest.farmer_id
    ).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found for this farmer")

    new_harvest = models.Harvest(
        farmer_id=harvest.farmer_id,
        field_id=harvest.field_id,
        crop_type=harvest.crop_type,
        harvest_date=harvest.harvest_date,
        status=harvest.status
    )
    db.add(new_harvest)
    db.commit()
    db.refresh(new_harvest)
    return new_harvest


# -------------------
# Get harvests for a specific user
# -------------------
@app.get("/harvests/user/{farmer_id}", response_model=List[schemas.HarvestOut])
def get_harvests_by_user(farmer_id: int, db: Session = Depends(get_db)):
    harvests = db.query(models.Harvest).filter(models.Harvest.farmer_id == farmer_id).all()
    if not harvests:
        raise HTTPException(status_code=404, detail="No harvests found for this user")
    return harvests


# -------------------
# Get all harvests (admin)
# -------------------
@app.get("/harvests", response_model=List[schemas.HarvestOut])
def get_all_harvests(db: Session = Depends(get_db)):
    harvests = db.query(models.Harvest).all()
    if not harvests:
        raise HTTPException(status_code=404, detail="No harvests found")
    return harvests

# Update an existing harvest
# ======================
@app.put("/harvests/{harvest_id}", response_model=schemas.HarvestOut)
def update_harvest(harvest_id: int, updated_harvest: schemas.HarvestCreate, db: Session = Depends(get_db)):
    harvest = db.query(models.Harvest).filter(models.Harvest.id == harvest_id).first()
    if not harvest:
        raise HTTPException(status_code=404, detail="Harvest not found")
    for key, value in updated_harvest.dict(exclude_unset=True).items():
        setattr(harvest, key, value)
    db.commit()
    db.refresh(harvest)
    return harvest
# Delete a harvest
# ======================
@app.delete("/harvests/{harvest_id}")
def delete_harvest(harvest_id: int, db: Session = Depends(get_db)):
    harvest = db.query(models.Harvest).filter(models.Harvest.id == harvest_id).first()
    if not harvest:
        raise HTTPException(status_code=404, detail="Harvest not found")
    db.delete(harvest)
    db.commit()
    return {"detail": "Harvest deleted successfully"}

# Create a pest alert
@app.post("/pest-alerts", response_model=schemas.PestAlertOut)
def create_pest_alert(alert: schemas.PestAlertCreate, db: Session = Depends(get_db)):
    new_alert = models.PestAlert(**alert.dict())
    db.add(new_alert)
    db.commit()
    db.refresh(new_alert)
    return new_alert

# Get all pest alerts for a farmer
@app.get("/pest-alerts/user/{farmer_id}", response_model=List[schemas.PestAlertOut])
def get_pest_alerts(farmer_id: int, db: Session = Depends(get_db)):
    alerts = db.query(models.PestAlert).filter(models.PestAlert.farmer_id == farmer_id).all()
    return alerts

# Update a pest alert
# =====================
@app.put("/pest-alerts/{pest_id}", response_model=schemas.PestAlertOut)
def update_pest_alert(pest_id: int, updated_pest: schemas.PestAlertBase, db: Session = Depends(get_db)):
    pest = db.query(models.PestAlert).filter(models.PestAlert.id == pest_id).first()
    if not pest:
        raise HTTPException(status_code=404, detail="Pest alert not found")
    
    # Update only the fields that are provided
    for key, value in updated_pest.dict(exclude_unset=True).items():
        setattr(pest, key, value)

    db.commit()
    db.refresh(pest)
    return pest

# =====================
# Delete a pest alert
# =====================
@app.delete("/pest-alerts/{pest_id}")
def delete_pest_alert(pest_id: int, db: Session = Depends(get_db)):
    pest = db.query(models.PestAlert).filter(models.PestAlert.id == pest_id).first()
    if not pest:
        raise HTTPException(status_code=404, detail="Pest alert not found")
    
    db.delete(pest)
    db.commit()
    return {"detail": "Pest alert deleted successfully"}
# =====================
# Get all pest alerts
# =====================
@app.get("/pest-alerts", response_model=list[schemas.PestAlertOut])
def get_all_pests(db: Session = Depends(get_db)):
    pests = db.query(models.PestAlert).all()
    return pests


# Admin creates weather alert
# ========================
@app.post("/weather-alerts", response_model=schemas.WeatherAlertOut)
def create_weather_alert(alert: schemas.WeatherAlertCreate, db: Session = Depends(get_db)):
    new_alert = models.WeatherAlert(**alert.dict())
    db.add(new_alert)
    db.commit()
    db.refresh(new_alert)
    return new_alert


# ========================
# Get all weather alerts
# ========================
@app.get("/weather-alerts", response_model=List[schemas.WeatherAlertOut])
def get_all_weather_alerts(db: Session = Depends(get_db)):
    alerts = db.query(models.WeatherAlert).all()
    return alerts

# ========================
# Get alerts for a specific region
# ========================
from sqlalchemy import func  # make sure this is imported

@app.get("/weather-alerts/region/{region}", response_model=List[schemas.WeatherAlertOut])
def get_weather_alerts_by_region(region: str, db: Session = Depends(get_db)):
    # Trim whitespace and make it lowercase for matching
    cleaned_region = region.strip().lower()

    # Case-insensitive search in the DB
    alerts = db.query(models.WeatherAlert).filter(
        func.lower(models.WeatherAlert.region) == cleaned_region
    ).all()

    return alerts
# =========================
# Change user role (no auth)
# =========================
from models import Role  # import the Role enum from your models

@app.put("/users/{user_id}/role", response_model=schemas.UserResponse)
def update_user_role(user_id: int, new_role: Role, db: Session = Depends(get_db)):
    """
    Update a user's role and mark their profile as completed.
    new_role must be a valid Role enum value (farmer, agronomist, donor, leader, finance, admin)
    """
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    db_user.role = new_role.value  # store the string value in the DB
    db_user.is_profile_completed = True  # mark profile as completed

    db.commit()
    db.refresh(db_user)
    return db_user
    


from datetime import date, timedelta
from sqlalchemy import func
from models import Field, Harvest, Complaint
@app.get("/farmer/{farmer_id}/daily-activity")
def get_daily_activity(farmer_id: int, db: Session = Depends(get_db)):
    """
    Returns number of farmer actions per day (last 7 days)
    """

    today = date.today()
    week_ago = today - timedelta(days=6)

    activity_map = {}

    # -------- Fields --------
    fields = (
        db.query(
            func.date(Field.created_at).label("day"),
            func.count(Field.id).label("count")
        )
        .filter(Field.farmer_id == farmer_id)
        .filter(Field.created_at >= week_ago)
        .group_by("day")
        .all()
    )

    # -------- Harvests --------
    harvests = (
        db.query(
            func.date(Harvest.created_at).label("day"),
            func.count(Harvest.id).label("count")
        )
        .filter(Harvest.farmer_id == farmer_id)
        .filter(Harvest.created_at >= week_ago)
        .group_by("day")
        .all()
    )

    # -------- Complaints --------
    complaints = (
        db.query(
            func.date(Complaint.created_at).label("day"),
            func.count(Complaint.id).label("count")
        )
        .filter(Complaint.created_by == farmer_id)
        .filter(Complaint.created_at >= week_ago)
        .group_by("day")
        .all()
    )

    # -------- Merge counts --------
    for dataset in (fields, harvests, complaints):
        for day, count in dataset:
            activity_map[day] = activity_map.get(day, 0) + count

    # -------- Build last 7 days --------
    result = []
    for i in range(7):
        current_day = week_ago + timedelta(days=i)
        result.append({
            "day": current_day.strftime("%a"),  # Mon Tue Wed
            "value": activity_map.get(current_day, 0)
        })

    return {
        "success": True,
        "message": "Daily activity fetched successfully",
        "data": result
    }


# ======================
# AI chat (Deepseek)
# ======================
@app.post("/ai-chat")
async def ai_chat(req: schemas.ChatRequest, request: Request):
    message = req.message
    model = request.query_params.get("model")
    if not message:
        raise HTTPException(status_code=400, detail="Missing 'message' in request body. Send JSON like {'message':'hi'}")

    # Prefer Hugging Face Router if token present
    hf_token = os.getenv("HUGGINGFACE_API_TOKEN") or os.getenv("HF_TOKEN")
    if hf_token:
        hf_model = model or os.getenv("HUGGINGFACE_MODEL", "deepseek-ai/DeepSeek-V3.2")
        hf_url = "https://router.huggingface.co/v1/chat/completions"
        headers = {"Authorization": f"Bearer {hf_token}", "Content-Type": "application/json"}
        payload = {"model": hf_model, "messages": [{"role": "user", "content": message}]}

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(hf_url, json=payload, headers=headers)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=str(e))

        if resp.status_code == 401:
            raise HTTPException(status_code=502, detail="Hugging Face authentication failed (check token)")

        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise HTTPException(status_code=502, detail={"huggingface_error": detail})

        try:
            jr = resp.json()
        except Exception:
            return {"reply": resp.text}

        # try chat-completion style
        try:
            choices = jr.get("choices") if isinstance(jr, dict) else None
            if choices and len(choices) > 0:
                message_obj = choices[0].get("message") or choices[0].get("delta") or {}
                if isinstance(message_obj, dict):
                    content = message_obj.get("content")
                    if content:
                        return {"reply": content}
        except Exception:
            pass

        # fallbacks
        if isinstance(jr, list) and jr and isinstance(jr[0], dict):
            txt = jr[0].get("generated_text") or jr[0].get("summary_text") or jr[0].get("text")
            if txt:
                return {"reply": txt}

        if isinstance(jr, dict):
            txt = jr.get("generated_text") or jr.get("summary_text") or jr.get("text")
            if txt:
                return {"reply": txt}

        return {"reply": jr}

    # Otherwise fall back to Deepseek-style flow (existing logic)
    # allow forcing mock responses for development
    use_mock = os.environ.get("USE_DEEPSEEK_MOCK", "false").lower() in ("1", "true", "yes")
    if use_mock:
        return {"reply": f"Hi, hello — how can I help you with '{message}'?", "mock": True}

    opa_key = os.environ.get("OPA_API_KEY")
    deepeek_url = os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.ai/v1/chat")

    # If no API key configured, return a helpful mock response
    if not opa_key:
        return {"reply": f"Hi, hello — how can I help you with '{message}'? (local mock; set OPA_API_KEY to enable Deepseek)", "mock": True}

    headers = {
        "Authorization": f"Bearer {opa_key}",
        "Content-Type": "application/json",
    }

    # Compose a payload that includes common fields Deepseek-like services accept.
    body = {
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek"),
        "input": message,
        "message": message,
        "text": message,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(deepeek_url, json=body, headers=headers)
    except httpx.RequestError as e:
        return {"reply": f"(fallback) Deepseek unreachable (network error): {str(e)}", "mock": True}
    except Exception as e:
        return {"reply": f"(fallback) Unexpected error contacting Deepseek: {str(e)}", "mock": True}

    # If upstream returns non-2xx, provide safe fallback with details
    if resp.status_code >= 400:
        text = resp.text
        return {"reply": f"(fallback) Deepseek API error {resp.status_code}: {text}", "mock": True}

    # Parse response JSON and attempt to extract a user-facing reply
    try:
        j = resp.json()
    except Exception:
        return {"reply": resp.text}

    def extract_reply(obj):
        if not obj:
            return None
        if isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            # common top-level keys
            for k in ("reply", "response", "output", "text", "message"):
                if k in obj and isinstance(obj[k], str):
                    return obj[k]
            # OpenAI / choices style
            if "choices" in obj and isinstance(obj["choices"], list) and obj["choices"]:
                c = obj["choices"][0]
                if isinstance(c, dict):
                    for k in ("text", "message", "content"):
                        if k in c and isinstance(c[k], str):
                            return c[k]
            # nested fields
            for v in obj.values():
                r = extract_reply(v)
                if r:
                    return r
        if isinstance(obj, list):
            for item in obj:
                r = extract_reply(item)
                if r:
                    return r
        return None

    reply = extract_reply(j)
    if not reply:
        # fallback: return the whole JSON as string
        return {"reply": j}

    return {"reply": reply}

# ----------------- GET CHAT HISTORY FOR USER -----------------
@app.get("/ai/chat/{user_id}", response_model=list[schemas.AIChatHistoryOut])
def get_ai_chats(user_id: int, db: Session = Depends(get_db)):
    chats = db.query(AIChatHistory).filter(AIChatHistory.user_id == user_id).order_by(AIChatHistory.created_at.desc()).all()
    return chats
@app.on_event("startup")
async def warmup_ai():
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                "http://localhost:8000/ai-chat",
                json={"message": "warmup"}
            )
    except:
        pass

# ======================
# Public Complaint (No Login Required)
# ======================
@app.post("/public-complaint", response_model=schemas.PublicComplaintOut)
def create_public_complaint(
    name: str = Form(...),
    phone: str = Form(...),
    email: Optional[str] = Form(None),
    title: str = Form(...),
    type: str = Form(...),
    description: str = Form(...),
    location: str = Form(...),
    urgent: bool = Form(False),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    image_url = None
    
    # Upload image to Supabase if provided
    if image:
        # Create unique filename
        filename = f"public_complaint_{int(time.time())}_{image.filename}"
        content = image.file.read()
        
        try:
            # Upload to Supabase
            supabase.storage.from_(BUCKET_NAME).upload(filename, content)
            # Get public URL
            image_url = supabase.storage.from_(BUCKET_NAME).get_public_url(filename)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Supabase upload failed: {str(e)}")

    # Create complaint in database
    complaint = models.PublicComplaint(
        name=name,
        phone=phone,
        email=email,
        title=title,
        type=type,
        description=description,
        location=location,
        urgent=urgent,
        image=image_url,
        status=models.ComplaintStatus.Pending  # Reuse your existing enum
    )

    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    
    return complaint

# ======================
# Get Public Complaint by ID
# ======================
@app.get("/public-complaint/{complaint_id}", response_model=schemas.PublicComplaintOut)
def get_public_complaint_comlaintid(
    complaint_id: int,
    db: Session = Depends(get_db)
):
    complaint = db.query(models.PublicComplaint).filter(models.PublicComplaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint

# ======================
# Get All Public Complaints (with filters)
# ======================
@app.get("/public-complaints", response_model=List[schemas.PublicComplaintOut])
def get_public_complaints_filter(
    skip: int = 0,
    limit: int = 100,
    type: Optional[str] = None,
    urgent: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.PublicComplaint)
    
    if type:
        query = query.filter(models.PublicComplaint.type == type)
    if urgent is not None:
        query = query.filter(models.PublicComplaint.urgent == urgent)
    
    complaints = query.order_by(models.PublicComplaint.created_at.desc()).offset(skip).limit(limit).all()
    return complaints

    # ======================
# Get All Public Complaints (with filters)
# ======================
@app.get("/public-complaints", response_model=List[schemas.PublicComplaintOut])
def get_ALL_public_complaints(
    skip: int = 0,
    limit: int = 100,
    type: Optional[str] = None,
    status: Optional[str] = None,
    urgent: Optional[bool] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
    # Add admin authentication here if needed
):
    """
    Get all public complaints with optional filters.
    
    - skip: Number of records to skip (pagination)
    - limit: Maximum number of records to return
    - type: Filter by complaint type (e.g., crop_disease, pest_infestation)
    - status: Filter by status (pending, reviewed, resolved)
    - urgent: Filter by urgent flag (true/false)
    - start_date: Filter by created date (YYYY-MM-DD)
    - end_date: Filter by created date (YYYY-MM-DD)
    - search: Search in title, description, name, phone, location
    """
    query = db.query(models.PublicComplaint)
    
    # Apply filters
    if type:
        query = query.filter(models.PublicComplaint.type == type)
    
    if status:
        query = query.filter(models.PublicComplaint.status == status)
    
    if urgent is not None:
        query = query.filter(models.PublicComplaint.urgent == urgent)
    
    if start_date:
        query = query.filter(models.PublicComplaint.created_at >= start_date)
    
    if end_date:
        query = query.filter(models.PublicComplaint.created_at <= end_date)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                models.PublicComplaint.title.ilike(search_term),
                models.PublicComplaint.description.ilike(search_term),
                models.PublicComplaint.name.ilike(search_term),
                models.PublicComplaint.phone.ilike(search_term),
                models.PublicComplaint.location.ilike(search_term)
            )
        )
    
    # Order by most recent first
    query = query.order_by(models.PublicComplaint.created_at.desc())
    
    # Apply pagination
    complaints = query.offset(skip).limit(limit).all()
    
    return complaints

# ======================
# Get User Profile
# ======================
@app.get("/users/profile/{user_id}", response_model=schemas.UserProfileResponse)
def get_user_profile(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Get user profile by ID
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Base profile data
    profile_data = {
        "id": user.id,
        "fullname": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role.value if user.role else None,
        "is_approved": user.is_approved,
        "is_profile_completed": user.is_profile_completed,
        "profile_picture": user.profile_picture, 
    }
    
    # Add role-specific fields
    if user.role == models.Role.farmer:
        profile_data.update({
            "farm_location": user.farm_location,
            "crop_type": user.crop_type,
            "district": user.district,
        })
    
    elif user.role == models.Role.agronomist:
        profile_data.update({
            "expertise": user.expertise,
            "license": user.license,
        })
    
    elif user.role == models.Role.donor:
        profile_data.update({
            "org_name": user.org_name,
            "funding": user.funding,
            "donor_type": user.donor_type.value if user.donor_type else None,
        })
    
    elif user.role == models.Role.leader:
        profile_data.update({
            "leader_title": user.leader_title,
            "district": user.district,
        })
    
    elif user.role == models.Role.finance:
        profile_data.update({
            "department": user.department,
        })
    
    elif user.role == models.Role.admin:
        profile_data.update({
            # Add admin-specific fields if any
        })
    
    return profile_data


# ======================
# Update User Profile
# ======================
@app.put("/users/profile/{user_id}", response_model=schemas.ProfileUpdateResponse)
def update_user_profile(
    user_id: int,
    profile_data: schemas.ProfileUpdate,
    db: Session = Depends(get_db)
):
    """
    Update user profile information
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update common fields
    if profile_data.fullname is not None:
        user.full_name = profile_data.fullname
    if profile_data.phone is not None:
        user.phone = profile_data.phone
    
    # Update role-specific fields based on user role
    if user.role == models.Role.farmer:
        if profile_data.farm_location is not None:
            user.farm_location = profile_data.farm_location
        if profile_data.crop_type is not None:
            user.crop_type = profile_data.crop_type
        if profile_data.district is not None:
            user.district = profile_data.district
    
    elif user.role == models.Role.agronomist:
        if profile_data.expertise is not None:
            user.expertise = profile_data.expertise
        if profile_data.license is not None:
            user.license = profile_data.license
    
    elif user.role == models.Role.donor:
        if profile_data.org_name is not None:
            user.org_name = profile_data.org_name
        if profile_data.funding is not None:
            user.funding = profile_data.funding
        if profile_data.donor_type is not None:
            user.donor_type = profile_data.donor_type
    
    elif user.role == models.Role.leader:
        if profile_data.leader_title is not None:
            user.leader_title = profile_data.leader_title
        if profile_data.district is not None:
            user.district = profile_data.district
    
    elif user.role == models.Role.finance:
        if profile_data.department is not None:
            user.department = profile_data.department
    
    # Mark profile as completed if all required fields are filled
    if not user.is_profile_completed:
        if user.role == models.Role.farmer:
            if user.farm_location and user.crop_type and user.phone:
                user.is_profile_completed = True
        elif user.role == models.Role.agronomist:
            if user.expertise and user.license and user.phone:
                user.is_profile_completed = True
        elif user.role == models.Role.donor:
            if user.org_name and user.funding and user.phone:
                user.is_profile_completed = True
        elif user.role == models.Role.leader:
            if user.leader_title and user.district and user.phone:
                user.is_profile_completed = True
        elif user.role == models.Role.finance:
            if user.department and user.phone:
                user.is_profile_completed = True
    
    db.commit()
    
    return {
        "message": "Profile updated successfully",
        "is_profile_completed": user.is_profile_completed
    }

# ======================
# Upload Profile Picture
# ======================
BUCKET_NAME = os.getenv("BUCKET_NAME", "images")

@app.post("/users/{user_id}/profile-picture")
async def upload_profile_picture(
    user_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload profile picture to Supabase storage and save URL in DB
    """
    # Validate file type
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Validate file size (max 5MB)
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")
    
    # Get user
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    try:
        import uuid
        import os

        # Read file content
        content = await file.read()

        # Generate unique filename
        file_extension = os.path.splitext(file.filename)[1]
        filename = f"profile_{user_id}_{uuid.uuid4()}{file_extension}"

        # Upload to Supabase
        supabase.storage.from_(BUCKET_NAME).upload(filename, content)

        # Get public URL
        image_url = supabase.storage.from_(BUCKET_NAME).get_public_url(filename)

        # ✅ Save URL in DB
        user.profile_picture = image_url
        db.commit()

        return {
            "message": "Profile picture uploaded successfully",
            "imageUrl": image_url
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase upload failed: {str(e)}")
# ======================
# Get User Statistics
# ======================
@app.get("/users/{user_id}/stats")
def get_user_statistics(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Get user statistics based on role
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    stats = {
        "total_complaints": 0,
        "pending_complaints": 0,
        "resolved_complaints": 0,
    }
    
    # Get complaint statistics
    complaints = db.query(models.Complaint).filter(models.Complaint.created_by == user_id).all()
    stats["total_complaints"] = len(complaints)
    stats["pending_complaints"] = len([c for c in complaints if c.status == models.ComplaintStatus.Pending])
    stats["resolved_complaints"] = len([c for c in complaints if c.status == models.ComplaintStatus.Resolved])
    
    # Role-specific statistics
    if user.role == models.Role.farmer:
        fields = db.query(models.Field).filter(models.Field.farmer_id == user_id).all()
        harvests = db.query(models.Harvest).filter(models.Harvest.farmer_id == user_id).all()
        pest_alerts = db.query(models.PestAlert).filter(models.PestAlert.farmer_id == user_id).all()
        
        stats.update({
            "total_fields": len(fields),
            "total_harvests": len(harvests),
            "upcoming_harvests": len([h for h in harvests if h.status == "upcoming"]),
            "total_pest_alerts": len(pest_alerts),
            "critical_pests": len([p for p in pest_alerts if p.severity == "critical"]),
        })
    
    elif user.role == models.Role.donor:
        donations = db.query(models.Donation).filter(models.Donation.donor_name == user.full_name).all()
        stats.update({
            "total_donations": len(donations),
            "total_amount": sum([d.amount for d in donations]),
        })
    
    return stats

@app.post("/api/support", response_model=schemas.SupportRequestOut)
def create_support_request(
    payload: schemas.SupportRequestCreate,
    db: Session = Depends(get_db)
):
    data = payload.model_dump()

    # Default donor to name
    if not data.get("donor"):
        data["donor"] = data["name"]

    new_request = models.SupportRequest(**data)

    db.add(new_request)
    db.commit()
    db.refresh(new_request)

    return new_request
@app.get("/api/support/{request_id}", response_model=schemas.SingleSupportResponse)
def get_support_request(
    request_id: int,
    db: Session = Depends(get_db)
):
    request = db.query(models.SupportRequest)\
        .filter(models.SupportRequest.id == request_id)\
        .first()

    if not request:
        raise HTTPException(status_code=404, detail="Support request not found")

    return {
        "success": True,
        "data": request
    }
# ==============================
# GET ALL SUPPORT REQUESTS (no filters)
# ==============================

@app.get("/api/support", response_model=schemas.PaginatedSupportResponse)
def get_all_supports(db: Session = Depends(get_db)):
    supports = db.query(models.SupportRequest)\
                 .order_by(models.SupportRequest.created_at.desc())\
                 .all()

    total = len(supports)

    return {
        "success": True,
        "count": total,
        "total": total,
        "page": 1,
        "pages": 1,
        "data": supports
    }

# ======================
# Active Complaints Count (All)
# ======================
@app.get("/admin/complaints/active")
def get_active_complaints(db: Session = Depends(get_db)):

    user_complaints = db.query(models.Complaint).filter(
        models.Complaint.status != models.ComplaintStatus.Resolved
    ).count()

    public_complaints = db.query(models.PublicComplaint).filter(
        models.PublicComplaint.status != models.ComplaintStatus.Resolved
    ).count()

    total_active = user_complaints + public_complaints

    return {
        "active_complaints": total_active,
        "user_complaints_active": user_complaints,
        "public_complaints_active": public_complaints
    }
# ======================
# Total Users Count
# ======================
@app.get("/admin/users/total")
def get_total_users(db: Session = Depends(get_db)):

    total_users = db.query(models.User).count()

    return {
        "total_users": total_users
    }
# ======================
# Complaint Resolution Rate
# ======================
@app.get("/admin/complaints/resolution-rate")
def get_resolution_rate(db: Session = Depends(get_db)):

    # Total complaints
    total_user = db.query(models.Complaint).count()
    total_public = db.query(models.PublicComplaint).count()
    total_complaints = total_user + total_public

    # Resolved complaints
    resolved_user = db.query(models.Complaint).filter(
        models.Complaint.status == models.ComplaintStatus.Resolved
    ).count()

    resolved_public = db.query(models.PublicComplaint).filter(
        models.PublicComplaint.status == models.ComplaintStatus.Resolved
    ).count()

    total_resolved = resolved_user + resolved_public

    # Avoid division by zero
    if total_complaints == 0:
        resolution_rate = 0
    else:
        resolution_rate = round((total_resolved / total_complaints) * 100, 2)

    return {
        "resolution_rate": resolution_rate,
        "total_complaints": total_complaints,
        "resolved_complaints": total_resolved
    }
# ======================
# Admin Update Complaint Status
# ======================
@app.put("/admin/complaints/{complaint_id}/status")
def update_complaint_status(
    complaint_id: int,
    status: models.ComplaintStatus,
    is_public: bool = False,
    db: Session = Depends(get_db)
):

    if is_public:
        complaint = db.query(models.PublicComplaint).filter(
            models.PublicComplaint.id == complaint_id
        ).first()
    else:
        complaint = db.query(models.Complaint).filter(
            models.Complaint.id == complaint_id
        ).first()

    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")

    complaint.status = status

    db.commit()
    db.refresh(complaint)

    return {
        "message": "Complaint status updated successfully",
        "complaint_id": complaint.id,
        "new_status": complaint.status
    }
from sqlalchemy import func

# ======================
# Total Donation Amount
# ======================
@app.get("/admin/donations/total-amount")
def get_total_donation_amount(db: Session = Depends(get_db)):

    total_amount = db.query(
        func.coalesce(func.sum(models.Donation.amount), 0)
    ).scalar()

    return {
        "total_amount": float(total_amount)
    }
from sqlalchemy import func, case
from datetime import datetime, timedelta

@app.get("/admin/complaints/trend/daily")
def daily_complaints_trend(days: int = 30, db: Session = Depends(get_db)):
    start_date = datetime.utcnow() - timedelta(days=days)

    complaints = (
        db.query(
            func.date(models.Complaint.created_at).label("date"),
            func.count(models.Complaint.id).label("complaints"),
            func.sum(
                case(
                    (models.Complaint.status == models.ComplaintStatus.Resolved, 1),
                    else_=0
                )
            ).label("resolved")
        )
        .filter(models.Complaint.created_at >= start_date)
        .group_by(func.date(models.Complaint.created_at))
        .order_by(func.date(models.Complaint.created_at))
        .all()
    )

    trend = [
        {"date": str(c.date), "complaints": c.complaints, "resolved": c.resolved}
        for c in complaints
    ]

    return trend


# ======================
# Complaint Status Endpoint
# ======================
@app.get("/admin/complaints/status", response_model=List[schemas.ComplaintStatusOut])
def complaint_status(db: Session = Depends(get_db)):

    # Query user complaints
    user_counts = (
        db.query(models.Complaint.status, func.count(models.Complaint.id))
        .group_by(models.Complaint.status)
        .all()
    )

    # Query public complaints
    public_counts = (
        db.query(models.PublicComplaint.status, func.count(models.PublicComplaint.id))
        .group_by(models.PublicComplaint.status)
        .all()
    )

    # Combine counts
    combined = {}
    for status, count in user_counts + public_counts:
        combined[status] = combined.get(status, 0) + count

    # Map to frontend format with colors
    color_map = {
        "Resolved": "#16A34A",
        "Pending": "#B45309",
        "InProgress": "#CA8A04"
    }

    result = [
        {
            "name": status,
            "value": combined[status],
            "color": color_map.get(status, "#6B7280")  # default gray if missing
        }
        for status in combined
    ]

    return JSONResponse(content=result)


@app.get("/notifications/{user_id}", response_model=list[schemas.NotificationOut])
def fetch_notifications(user_id: int, db: Session = Depends(get_db)):
    """
    Fetch all notifications for a user.
    Unread notifications appear first, newest on top.
    This acts as the "automatic notification fetch" endpoint.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    notifications = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == user_id)
        .order_by(models.Notification.is_read.asc(), models.Notification.created_at.desc())
        .all()
    )

    return notifications

# request password change OTP
@app.post("/request-password-otp")
def request_password_otp_simple(
    identifier: str,  # email or phone
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        or_(models.User.email == identifier, models.User.phone == identifier)
    ).first()

    if not user:
        raise HTTPException(404, "User not found")

    otp = str(random.randint(100000, 999999))

    otp_record = models.PasswordChangeOTP(
        user_id=user.id,
        otp_code=otp,
        expires_at=datetime.utcnow() + timedelta(minutes=10),
        is_used=False
    )

    db.add(otp_record)
    db.commit()
    db.refresh(otp_record)

    return {"success": True, "message": "OTP generated", "otp_for_testing": otp}

# change password using OTP
@app.post("/change-password")
def change_password(
    data: schemas.ChangePasswordRequest,
    db: Session = Depends(get_db)
):
    # 1️⃣ Find the user by email or phone
    user = db.query(models.User).filter(
        or_(
            models.User.email == data.identifier,
           models.User.phone == data.identifier
        )
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2️⃣ Check OTP
    otp_record = db.query(models.PasswordChangeOTP).filter(
        models.PasswordChangeOTP.user_id == user.id,
        models.PasswordChangeOTP.otp_code == data.otp_code,
        models.PasswordChangeOTP.is_used == False
    ).order_by(models.PasswordChangeOTP.created_at.desc()).first()

    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    if otp_record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP has expired")

    # 3️⃣ Check new password confirmation
    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    # 4️⃣ Prevent reusing the same password
    if pwd_context.verify(data.new_password, user.password):
        raise HTTPException(status_code=400, detail="New password cannot be same as old password")

    # 5️⃣ Update password
    user.password = pwd_context.hash(data.new_password)

    # 6️⃣ Mark OTP as used
    otp_record.is_used = True

    db.commit()

    return {
        "success": True,
        "message": "Password changed successfully. You can now login with your new password."
    }


# GET User Activities
# ----------------------
@app.get("/activities/user/{user_id}", response_model=List[schemas.ActivityResponse])
def get_user_activities(user_id: int, db: Session = Depends(get_db)):

    activities = db.query(models.ActivityHistory).filter(
        models.ActivityHistory.user_id == user_id
    ).order_by(models.ActivityHistory.created_at.desc()).all()

    if not activities:
        return []  # or raise HTTPException(404, "No activities found") if you prefer

    return activities

@app.post("/reports", response_model=schemas.ReportResponse)
def create_report(report: schemas.ReportCreate, db: Session = Depends(get_db)):

    new_report = Report(
        program=report.program,
        type=report.type,
        description=report.description,
        priority=report.priority,
        status="pending",
        user_id=report.user_id   
    )

    db.add(new_report)
    db.commit()
    db.refresh(new_report)

    return new_report
# reports (admin endpoint with filters)

@app.get("/reports", response_model=List[schemas.ReportResponse])
def get_reports(
    skip: int = 0, 
    limit: int = 100, 
    type: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Report)
    
    # Apply filters
    if type:
        query = query.filter(Report.type == type)
    if status:
        query = query.filter(Report.status == status)
    if start_date:
        query = query.filter(Report.created_at >= start_date)
    if end_date:
        query = query.filter(Report.created_at <= end_date)
    
    reports = query.offset(skip).limit(limit).all()
    return reports
from sqlalchemy import func
from sqlalchemy.orm import aliased

@app.get("/farmers", response_model=List[schemas.FarmerResponse])
def get_farmers(
    skip: int = 0, 
    limit: int = 100, 
    search: Optional[str] = None,
    district: Optional[str] = None,
    db: Session = Depends(get_db)
):
    # Query farmers with their complaint counts
    farmers = db.query(
        User.id,
        User.full_name.label('name'),
        User.phone,
        User.district.label('location'),
        User.is_approved.label('status'),
        func.count(Complaint.id).label('complaints')
    ).outerjoin(
        Complaint, 
        Complaint.created_by == User.id  # Using created_by as the foreign key
    ).filter(
        User.role == 'farmer'
    ).group_by(
        User.id
    )
    
    # Apply search filter
    if search:
        search_filter = f"%{search}%"
        farmers = farmers.filter(
            (User.full_name.ilike(search_filter)) |
            (User.phone.ilike(search_filter)) |
            (User.district.ilike(search_filter))
        )
    
    # Apply district filter
    if district:
        farmers = farmers.filter(User.district == district)
    
    # Apply pagination
    farmers = farmers.offset(skip).limit(limit).all()
    
    # Convert to response format
    result = []
    for farmer in farmers:
        result.append({
            "id": farmer.id,
            "name": farmer.name,
            "phone": farmer.phone or "",  # Handle None
            "location": farmer.location or "",  # Handle None
            "status": "Active" if farmer.status else "Inactive",
            "complaints": farmer.complaints or 0  # Handle None
        })
    
    return result
from fastapi import HTTPException, status
# assigning complaints to agronomists
from services.notification_service import NotificationService
from datetime import datetime

@app.post("/complaints/assign", response_model=schemas.ComplaintAssignResponse)
def assign_complaint(
    assignment: schemas.ComplaintAssignRequest,
    db: Session = Depends(get_db)
):
    # 1. Check if complaint exists
    complaint = db.query(Complaint).filter(Complaint.id == assignment.complaint_id).first()
    if not complaint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Complaint with id {assignment.complaint_id} not found"
        )
    
    # 2. Check if agronomist exists and has the correct role
    agronomist = db.query(User).filter(
        User.id == assignment.agronomist_id,
        User.role == 'agronomist'
    ).first()
    
    if not agronomist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Agronomist with id {assignment.agronomist_id} not found"
        )
    
    # 3. Check if complaint is already assigned
    reassigned = False
    previous_agronomist_name = None
    if complaint.assigned_to is not None:
        previous_agronomist = db.query(User).filter(User.id == complaint.assigned_to).first()
        if previous_agronomist:
            previous_agronomist_name = previous_agronomist.full_name
            reassigned = True
            print(f"Reassigning complaint from {previous_agronomist.full_name} to {agronomist.full_name}")
    
    # 4. Assign the complaint to the agronomist with timestamp
    complaint.assigned_to = assignment.agronomist_id
    complaint.assigned_at = datetime.now()  # Add timestamp if you have this field
    
    # 5. Save to database
    db.commit()
    db.refresh(complaint)

    # 6. ========== CREATE NOTIFICATIONS ==========
    
    # 6.1 Notify the NEW agronomist
    NotificationService.create_notification(
        db=db,
        user_id=assignment.agronomist_id,
        role="agronomist",
        title="📋 New Complaint Assigned",
        message=f"A new complaint '{complaint.title}' has been assigned to you. Please review and take action.",
        type="complaint_assigned",
        related_id=complaint.id,
        priority="high",
        action_url=f"/agronomist/complaints/{complaint.id}",
        extra_data={
            "complaint_id": complaint.id,
            "complaint_title": complaint.title,
            "complaint_type": complaint.type,
            "location": complaint.location,
            "assigned_by": "Leader"  # You can get the actual leader name if available
        }
    )

    # 6.2 Notify the FARMER who created the complaint
    farmer = db.query(User).filter(User.id == complaint.created_by).first()
    if farmer:
        notification_message = f"Your complaint '{complaint.title}' has been assigned to Agronomist {agronomist.full_name}"
        if reassigned:
            notification_message = f"Your complaint '{complaint.title}' has been reassigned from {previous_agronomist_name} to Agronomist {agronomist.full_name}"
        
        NotificationService.create_notification(
            db=db,
            user_id=complaint.created_by,
            role=farmer.role,
            title="👨‍🌾 Complaint Assignment Update",
            message=notification_message,
            type="complaint_assigned",
            related_id=complaint.id,
            priority="normal",
            action_url=f"/farmer/complaints/{complaint.id}",
            extra_data={
                "complaint_id": complaint.id,
                "complaint_title": complaint.title,
                "agronomist_name": agronomist.full_name,
                "reassigned": reassigned
            }
        )

    # 6.3 If this is a reassignment, notify the PREVIOUS agronomist (if any)
    if reassigned and previous_agronomist:
        NotificationService.create_notification(
            db=db,
            user_id=complaint.assigned_to,  # This is the previous agronomist's ID
            role="agronomist",
            title="🔄 Complaint Reassigned",
            message=f"Complaint '{complaint.title}' has been reassigned to {agronomist.full_name}",
            type="complaint_reassigned",
            related_id=complaint.id,
            priority="normal",
            action_url=f"/agronomist/complaints",
            extra_data={
                "complaint_id": complaint.id,
                "complaint_title": complaint.title,
                "new_agronomist": agronomist.full_name
            }
        )

    # 6.4 Notify all ADMINS about the assignment (optional)
    admins = db.query(User).filter(User.role == "admin").all()
    for admin in admins:
        NotificationService.create_notification(
            db=db,
            user_id=admin.id,
            role="admin",
            title="📢 Complaint Assignment",
            message=f"Complaint '{complaint.title}' has been assigned to Agronomist {agronomist.full_name}",
            type="admin_alert",
            related_id=complaint.id,
            priority="low",
            action_url=f"/admin/complaints/{complaint.id}",
            extra_data={
                "complaint_id": complaint.id,
                "complaint_title": complaint.title,
                "agronomist_name": agronomist.full_name,
                "farmer_name": farmer.full_name if farmer else "Unknown"
            }
        )

    # 7. Return success message
    response_message = "Complaint assigned successfully"
    if reassigned:
        response_message = f"Complaint reassigned from {previous_agronomist_name} to {agronomist.full_name}"
    
    return schemas.ComplaintAssignResponse(
        message=response_message,
        complaint_id=complaint.id,
        assigned_to=agronomist.full_name,
        status=complaint.status
    )
# assigned complaints for agronomists with farmer inf
@app.get("/agronomists", response_model=List[schemas.AgronomistResponse])
def get_agronomists(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    district: Optional[str] = None,
    db: Session = Depends(get_db)
):
    # Query users with role 'agronomist'
    query = db.query(User).filter(User.role == 'agronomist')
    
    # Apply filters
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (User.full_name.ilike(search_filter)) |
            (User.email.ilike(search_filter)) |
            (User.phone.ilike(search_filter)) |
            (User.district.ilike(search_filter)) |
            (User.expertise.ilike(search_filter))
        )
    
    if district:
        query = query.filter(User.district == district)
    
    # Get paginated agronomists
    agronomists = query.offset(skip).limit(limit).all()
    
    result = []
    for agronomist in agronomists:
        # Get all complaints assigned to this agronomist
        assigned_complaints = db.query(Complaint).filter(
            Complaint.assigned_to == agronomist.id
        ).all()
        
        # Calculate statistics
        total_assigned = len(assigned_complaints)
        resolved = sum(1 for c in assigned_complaints if c.status == "Resolved")
        pending = sum(1 for c in assigned_complaints if c.status in ["Pending", "On Hold"])
        
        # Format assigned complaints with farmer info
        complaints_list = []
        for complaint in assigned_complaints:
            # Get farmer who created the complaint
            farmer = db.query(User).filter(User.id == complaint.created_by).first()
            complaints_list.append({
                "id": complaint.id,
                "title": complaint.title,
                "type": complaint.type,
                "location": complaint.location,
                "status": complaint.status,
                "created_at": complaint.created_at,
                "farmer_name": farmer.full_name if farmer else "Unknown",
                "farmer_phone": farmer.phone if farmer else None
            })
        
        # Build agronomist response
        agronomist_data = {
            "id": agronomist.id,
            "name": agronomist.full_name,
            "email": agronomist.email,
            "phone": agronomist.phone or "",
            "district": agronomist.district or "",
            "expertise": agronomist.expertise or "",
            "license": agronomist.license or "",
            "is_approved": agronomist.is_approved,
            "total_assigned_complaints": total_assigned,
            "resolved_complaints": resolved,
            "pending_complaints": pending,
            "assigned_complaints": complaints_list
        }
        result.append(agronomist_data)
    
    return result
@app.put("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db)
):
    """Mark a single notification as read"""
    notification = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    notification.is_read = True
    db.commit()
    
    return {"message": "Notification marked as read"}

@app.post("/notifications/mark-all-read")
def mark_all_notifications_read(
    request: dict,
    db: Session = Depends(get_db)
):
    """Mark all notifications as read for a user"""
    user_id = request.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    
    db.query(models.Notification).filter(
        models.Notification.user_id == user_id,
        models.Notification.is_read == False
    ).update({"is_read": True})
    
    db.commit()
    
    return {"message": "All notifications marked as read"}



@app.post("/farmer/send-followup")
async def send_farmer_followup(
    complaint_id: int = Form(...),
    farmer_id: int = Form(...),
    message: str = Form(None),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    """
    Endpoint for farmer to send a follow-up message with optional image
    """
    try:
        # 1. Verify complaint exists and belongs to this farmer
        complaint = db.query(models.Complaint).filter(
            models.Complaint.id == complaint_id,
            models.Complaint.created_by == farmer_id
        ).first()
        
        if not complaint:
            raise HTTPException(
                status_code=404,
                detail="Complaint not found or you don't have permission"
            )
        
        # 2. Check if complaint is assigned to an agronomist
        if not complaint.assigned_to:
            raise HTTPException(
                status_code=400,
                detail="Complaint not assigned to any agronomist yet"
            )
        
        # 3. Upload image to Supabase if provided
        image_url = None
        if image:
            # Read image file
            image_content = await image.read()
            
            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            filename = f"followups/{farmer_id}/{complaint_id}/{timestamp}_{unique_id}.jpg"
            
            # Upload to Supabase
            supabase.storage.from_(BUCKET_NAME).upload(
                path=filename,
                file=image_content,
                file_options={"content-type": image.content_type}
            )
            
            # Get public URL
            image_url = supabase.storage.from_(BUCKET_NAME).get_public_url(filename)
        
        # 4. Save follow-up to database - USE 'image' INSTEAD OF 'image_url'
        followup = models.FollowUpMessage(
            complaint_id=complaint_id,
            farmer_id=farmer_id,
            agronomist_id=complaint.assigned_to,
            message=message,
            image=image_url,  # Changed from image_url to image
            status="pending"
        )
        
        db.add(followup)
        db.commit()
        db.refresh(followup)
        
        # 5. Get farmer name for notification
        farmer = db.query(models.User).filter(models.User.id == farmer_id).first()
        farmer_name = farmer.full_name if farmer else f"Farmer #{farmer_id}"
        
        # 6. Create notification for agronomist
        NotificationService.create_notification(
            db=db,
            user_id=complaint.assigned_to,
            role="agronomist",
            title="📨 New Follow-up from Farmer",
            message=f"Farmer {farmer_name} sent a follow-up about '{complaint.title}'",
            type="followup_received",
            related_id=complaint.id,
            priority="high",
            action_url=f"/agronomist/complaints/{complaint.id}",
            extra_data={
                "complaint_id": complaint.id,
                "complaint_title": complaint.title,
                "farmer_name": farmer_name,
                "has_image": image_url is not None,
                "followup_id": followup.id
            }
        )
        
        # 7. Return success response
        return {
            "success": True,
            "message": "Follow-up sent successfully",
            "data": {
                "followup_id": followup.id,
                "complaint_id": complaint_id,
                "complaint_title": complaint.title,
                "farmer_id": farmer_id,
                "farmer_name": farmer_name,
                "agronomist_id": complaint.assigned_to,
                "message": message,
                "image_url": image_url,  # Keep as image_url in response
                "status": "pending",
                "created_at": followup.created_at.isoformat()
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send follow-up: {str(e)}"
        )
# ================= GET FOLLOW-UP ENDPOINTS =================

@app.get("/followup/agronomist/{agronomist_id}", response_model=List[schemas.FollowUpMessageResponse])
def get_agronomist_followups(
    agronomist_id: int,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get all follow-ups for a specific agronomist"""
    # Verify agronomist exists
    agronomist = db.query(models.User).filter(
        models.User.id == agronomist_id,
        models.User.role == 'agronomist'
    ).first()
    
    if not agronomist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agronomist not found"
        )
    
    # Query follow-ups
    query = db.query(models.FollowUpMessage).filter(
        models.FollowUpMessage.agronomist_id == agronomist_id
    )
    
    if status:
        query = query.filter(models.FollowUpMessage.status == status)
    
    followups = query.order_by(
        models.FollowUpMessage.status == 'pending',
        models.FollowUpMessage.created_at.desc()
    ).offset(skip).limit(limit).all()
    
    # Enhance with farmer and complaint info
    result = []
    for f in followups:
        farmer = db.query(models.User).filter(models.User.id == f.farmer_id).first()
        complaint = db.query(models.Complaint).filter(models.Complaint.id == f.complaint_id).first()
        result.append({
            "id": f.id,
            "complaint_id": f.complaint_id,
            "farmer_id": f.farmer_id,
            "agronomist_id": f.agronomist_id,
            "farmer_name": farmer.full_name if farmer else "Unknown Farmer",
            "complaint_title": complaint.title if complaint else "Unknown Complaint",
            "message": f.message,
            "image_url": f.image,  # CHANGED: from f.image_url to f.image
            "status": f.status,
            "created_at": f.created_at,
            "read_at": f.read_at
        })
    
    return result
@app.get("/followup/farmer/{farmer_id}", response_model=List[schemas.FollowUpMessageResponse])
def get_farmer_followups(
    farmer_id: int,
    db: Session = Depends(get_db)
):
    """Get all follow-ups sent by a farmer"""
    farmer = db.query(models.User).filter(
        models.User.id == farmer_id,
        models.User.role == 'farmer'
    ).first()
    
    if not farmer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Farmer not found"
        )
    
    followups = db.query(models.FollowUpMessage).filter(
        models.FollowUpMessage.farmer_id == farmer_id
    ).order_by(models.FollowUpMessage.created_at.desc()).all()
    
    result = []
    for f in followups:
        complaint = db.query(models.Complaint).filter(models.Complaint.id == f.complaint_id).first()
        agronomist = db.query(models.User).filter(models.User.id == f.agronomist_id).first()
        result.append({
            "id": f.id,
            "complaint_id": f.complaint_id,
            "farmer_id": f.farmer_id,
            "agronomist_id": f.agronomist_id,
            "farmer_name": farmer.full_name,
            "agronomist_name": agronomist.full_name if agronomist else "Unknown Agronomist",
            "complaint_title": complaint.title if complaint else "Unknown Complaint",
            "message": f.message,
            "image_url": f.image,  # CHANGED: from f.image_url to f.image
            "status": f.status,
            "created_at": f.created_at,
            "read_at": f.read_at
        })
    
    return result

@app.get("/agronomists/{agronomist_id}/complaints")
def get_agronomist_complaints(
    agronomist_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    # Check if agronomist exists
    agronomist = db.query(User).filter(
        User.id == agronomist_id,
        User.role == 'agronomist'
    ).first()
    
    if not agronomist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agronomist not found"
        )
    
    # Query complaints assigned to this agronomist
    query = db.query(Complaint).filter(Complaint.assigned_to == agronomist_id)
    
    # Filter by status if provided
    if status:
        query = query.filter(Complaint.status == status)
    
    complaints = query.all()
    
    # Format complaints with farmer info
    result = []
    for complaint in complaints:
        farmer = db.query(User).filter(User.id == complaint.created_by).first()
        result.append({
            "id": complaint.id,
            "title": complaint.title,
            "type": complaint.type,
            "description": complaint.description,
            "location": complaint.location,
            "status": complaint.status,
            "created_at": complaint.created_at,
            # "assigned_at": complaint.assigned_at,  # REMOVE THIS LINE
            "image": complaint.image,
            "farmer_name": farmer.full_name if farmer else "Unknown",
            "farmer_phone": farmer.phone if farmer else None,
            "farmer_district": farmer.district if farmer else None
        })
    
    return result

# Get single donation by ID
@app.get("/api/donations/{donation_id}", response_model=schemas.DonationOut)
def get_donation(donation_id: int, db: Session = Depends(get_db)):
    donation = db.query(models.Donation).filter(models.Donation.id == donation_id).first()
    if not donation:
        raise HTTPException(status_code=404, detail="Donation not found")
    return donation

# GET all programs
@app.get("/api/programs", response_model=list[schemas.ProgramOut])
def get_programs(db: Session = Depends(get_db)):
    return db.query(models.Program).all()

@app.get("/api/donors/{donor_id}/impact/programs", response_model=List[schemas.ProgramImpactOut])
def get_donor_program_impact(donor_id: int, db: Session = Depends(get_db)):
    """
    Get impact data for all programs a donor has supported
    """
    # First check if donor exists
    donor = db.query(models.User).filter(models.User.id == donor_id).first()
    print(f"Donor exists: {donor is not None}")
    if donor:
        print(f"Donor found: {donor.id} - {donor.full_name}")
    
    # Get all program impacts to see what's in the table
    all_impacts = db.query(models.ProgramImpact).all()
    print(f"Total impacts in table: {len(all_impacts)}")
    for imp in all_impacts:
        print(f"Impact: id={imp.id}, donor_id={imp.donor_id}, program={imp.program_name}")
    
    # Get impacts for this specific donor
    program_impacts = db.query(models.ProgramImpact).filter(
        models.ProgramImpact.donor_id == donor_id
    ).all()
    print(f"Impacts for donor {donor_id}: {len(program_impacts)}")
    
    return program_impacts

# Create or update program impact for a donor
@app.post("/api/donors/{donor_id}/impact/programs", response_model=schemas.ProgramImpactOut)
def create_or_update_program_impact(
    donor_id: int, 
    impact_data: schemas.ProgramImpactCreate, 
    db: Session = Depends(get_db)
):
    """
    Create or update program impact for a donor
    This would be called when a donation is made
    """
    # Check if donor exists
    donor = db.query(models.User).filter(models.User.id == donor_id).first()
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found")
    
    # Check if program exists
    program = db.query(models.Program).filter(models.Program.id == impact_data.program_id).first()
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")
    
    # Check if there's already an impact record for this donor and program
    existing_impact = db.query(models.ProgramImpact).filter(
        models.ProgramImpact.donor_id == donor_id,
        models.ProgramImpact.program_id == impact_data.program_id
    ).first()
    
    if existing_impact:
        # Update existing record
        existing_impact.beneficiaries = impact_data.beneficiaries
        existing_impact.amount += impact_data.amount  # Add to existing amount
        existing_impact.impact_metrics = impact_data.impact_metrics
        existing_impact.success_stories = impact_data.success_stories
        existing_impact.status = impact_data.status
        existing_impact.updated_at = func.now()
        
        db.commit()
        db.refresh(existing_impact)
        return existing_impact
    else:
        # Create new record
        new_impact = models.ProgramImpact(
            donor_id=donor_id,
            program_id=impact_data.program_id,
            program_name=impact_data.program_name,
            beneficiaries=impact_data.beneficiaries,
            amount=impact_data.amount,
            impact_metrics=impact_data.impact_metrics,
            success_stories=impact_data.success_stories,
            status=impact_data.status
        )
        
        db.add(new_impact)
        db.commit()
        db.refresh(new_impact)
        return new_impact
    
@app.post("/api/donors/{donor_id}/impact/metrics", response_model=schemas.ImpactMetricOut)
def create_or_update_impact_metric(
    donor_id: int,
    metric: schemas.ImpactMetricCreate,
    db: Session = Depends(get_db)
):
    """
    Create or update an impact metric for a donor
    """
    # Check if donor exists
    donor = db.query(models.User).filter(models.User.id == donor_id).first()
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found")
    
    # Check if metric already exists for this donor, category, and year
    existing = db.query(models.ImpactMetric).filter(
        models.ImpactMetric.donor_id == donor_id,
        models.ImpactMetric.category == metric.category,
        models.ImpactMetric.year == metric.year
    ).first()
    
    if existing:
        # Update existing
        existing.value = metric.value
        existing.change = metric.change
        existing.target = metric.target
        existing.color = metric.color
        db.commit()
        db.refresh(existing)
        return existing
    else:
        # Create new
        new_metric = models.ImpactMetric(
            donor_id=donor_id,
            category=metric.category,
            value=metric.value,
            change=metric.change,
            target=metric.target,
            color=metric.color,
            year=metric.year
        )
        db.add(new_metric)
        db.commit()
        db.refresh(new_metric)
        return new_metric
    
    #
@app.get("/api/donors/{donor_id}/impact/metrics", response_model=List[schemas.ImpactMetricOut])
def get_donor_impact_metrics(
    donor_id: int, 
    timeframe: str = "year",  # year, quarter, month
    db: Session = Depends(get_db)
):
    """
    Get key metrics for a donor:
    - Food Security
    - Income Growth
    - Sustainable Practices
    - Women Empowerment
    """
    # Check if donor exists
    donor = db.query(models.User).filter(models.User.id == donor_id).first()
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found")
    
    # Get current year
    from datetime import datetime
    current_year = datetime.now().year
    
    # Adjust year based on timeframe
    if timeframe == "year":
        year = current_year
    elif timeframe == "quarter":
        year = current_year  # You might want to adjust this logic
    elif timeframe == "month":
        year = current_year  # You might want to adjust this logic
    else:  # all time - get most recent
        year = current_year
    
    # Get metrics for this donor and year
    metrics = db.query(models.ImpactMetric).filter(
        models.ImpactMetric.donor_id == donor_id,
        models.ImpactMetric.year == year
    ).all()
    
    return metrics
#
@app.post("/api/donors/{donor_id}/impact/yearly", response_model=schemas.YearlyImpactOut)
def create_or_update_yearly_impact(
    donor_id: int,
    yearly_data: schemas.YearlyImpactCreate,
    db: Session = Depends(get_db)
):
    """
    Create or update yearly impact data for a donor
    """
    # Check if donor exists
    donor = db.query(models.User).filter(models.User.id == donor_id).first()
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found")
    
    # Check if record already exists for this donor and year
    existing = db.query(models.YearlyImpact).filter(
        models.YearlyImpact.donor_id == donor_id,
        models.YearlyImpact.year == yearly_data.year
    ).first()
    
    if existing:
        # Update existing
        existing.beneficiaries = yearly_data.beneficiaries
        existing.programs = yearly_data.programs
        existing.donations = yearly_data.donations
        existing.yield_increase = yearly_data.yield_increase
        db.commit()
        db.refresh(existing)
        return existing
    else:
        # Create new
        new_yearly = models.YearlyImpact(
            donor_id=donor_id,
            year=yearly_data.year,
            beneficiaries=yearly_data.beneficiaries,
            programs=yearly_data.programs,
            donations=yearly_data.donations,
            yield_increase=yearly_data.yield_increase
        )
        db.add(new_yearly)
        db.commit()
        db.refresh(new_yearly)
        return new_yearly
#
@app.post("/api/donors/{donor_id}/impact/yearly", response_model=schemas.YearlyImpactOut)
def create_or_update_yearly_impact(
    donor_id: int,
    yearly_data: schemas.YearlyImpactCreate,
    db: Session = Depends(get_db)
):
    """
    Create or update yearly impact data for a donor
    """
    # Check if donor exists
    donor = db.query(models.User).filter(models.User.id == donor_id).first()
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found")
    
    # Check if record already exists for this donor and year
    existing = db.query(models.YearlyImpact).filter(
        models.YearlyImpact.donor_id == donor_id,
        models.YearlyImpact.year == yearly_data.year
    ).first()
    
    if existing:
        # Update existing
        existing.beneficiaries = yearly_data.beneficiaries
        existing.programs = yearly_data.programs
        existing.donations = yearly_data.donations
        existing.yield_increase = yearly_data.yield_increase
        db.commit()
        db.refresh(existing)
        return existing
    else:
        # Create new
        new_yearly = models.YearlyImpact(
            donor_id=donor_id,
            year=yearly_data.year,
            beneficiaries=yearly_data.beneficiaries,
            programs=yearly_data.programs,
            donations=yearly_data.donations,
            yield_increase=yearly_data.yield_increase
        )
        db.add(new_yearly)
        db.commit()
        db.refresh(new_yearly)
        return new_yearly