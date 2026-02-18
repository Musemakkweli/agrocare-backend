from random import random
import os
import time
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File,Form,Path, Request
from supabase import create_client, Client
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer
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
from models import AIChatHistory, Complaint, ComplaintStatus
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

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.environ.get("PORT", 8000))  # Use Render-assigned port
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)


# ======================
# Password Helpers
# ======================
def hash_password(password: str):
    # bcrypt has a maximum input of 72 bytes. Validate and return a clear error
    # so callers (HTTP endpoints) can return a proper 400 instead of a 500.
    if isinstance(password, str):
        b = password.encode("utf-8")
    else:
        b = bytes(password)

    if len(b) > 72:
        raise HTTPException(status_code=400, detail="Password too long; maximum is 72 bytes")

    return pwd_context.hash(password)


def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)


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
        is_approved=False
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user



# ======================
# Login (email OR phone)
# ======================
@app.post("/login", response_model=schemas.LoginResponseWithMessage)
def login_user(user: schemas.UserLogin, db: Session = Depends(get_db)):

    db_user = db.query(models.User).filter(
        or_(
            models.User.email == user.identifier,
            models.User.phone == user.identifier
        )
    ).first()

    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(400, "Invalid email or phone or password")

    if not db_user.is_approved:
        raise HTTPException(403, "User not approved yet")

    token = create_access_token({"id": db_user.id})

    return {
        "message": "Successfully logged in",
        "access_token": token,
        "token_type": "bearer",

        # ✅ send full user
        "user": db_user,

        # ✅ send profile status
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
 # =====================================
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
    new_program = models.Program(**program.dict())

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

# complaints endpoints
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
    if image:
        filename = f"{int(time.time())}_{image.filename}"
        content = image.file.read()

        # Remove the invalid res.error check
        try:
            supabase.storage.from_(BUCKET_NAME).upload(filename, content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Supabase upload failed: {str(e)}")

        # get_public_url returns a string directly — no .public_url
        image_url = supabase.storage.from_(BUCKET_NAME).get_public_url(filename)

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
# Update complaint status (admin)
@app.put("/complaints/{complaint_id}", response_model=schemas.ComplaintOut)
def update_complaint(
    complaint_id: int,
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

    if title is not None:
        complaint.title = title
    if type is not None:
        complaint.type = type
    if description is not None:
        complaint.description = description
    if location is not None:
        complaint.location = location

    if image:
        filename = f"{int(time.time())}_{image.filename}"
        content = image.file.read()
        supabase.storage.from_(BUCKET_NAME).upload(filename, content)

        # ✅ Get public URL directly
        complaint.image = supabase.storage.from_(BUCKET_NAME).get_public_url(filename)

    db.commit()
    db.refresh(complaint)
    return complaint
#Delete complaint (admin)
    
@app.delete("/complaints/{complaint_id}", response_model=dict)
def delete_complaint(complaint_id: int, db: Session = Depends(get_db)):
    complaint = db.query(models.Complaint).filter(models.Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    db.delete(complaint)
    db.commit()

    return {"message": f"Complaint with ID {complaint_id} has been deleted successfully."}

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