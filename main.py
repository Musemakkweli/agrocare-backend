from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta

from database import Base, engine, SessionLocal
import models, schemas


# ======================
# Setup
# ======================
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AgroCare Backend 🚀")


# ======================
# Security Config
# ======================
SECRET_KEY = "supersecretkey123"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


# ======================
# Password Helpers
# ======================
def hash_password(password: str):
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
        email=user.email,
        password=hash_password(user.password),
        role=user.role,
        is_approved=False
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


# ======================
# Login  ✅ NEW
# ======================
@app.post("/login", response_model=schemas.LoginResponseWithMessage)
def login_user(user: schemas.UserLogin, db: Session = Depends(get_db)):

    db_user = db.query(models.User).filter(models.User.email == user.email).first()

    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(400, "Invalid email or password")

    if not db_user.is_approved:
        raise HTTPException(403, "User not approved yet")

    token = create_access_token({"id": db_user.id})

    return {
        "message": "Successfully logged in",
        "access_token": token,
        "token_type": "bearer",
        "user": db_user
    }
# ======================
# Helper function
# ======================
def update_profile(user_id: int, profile, db: Session):
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(404, "User not found")

    for field, value in profile.dict(exclude_unset=True).items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user


# ======================
# Profile Routes (updated response)
# ======================

@app.put("/profile/farmer/{user_id}", response_model=schemas.FarmerProfile)
def farmer_profile(user_id: int, profile: schemas.FarmerProfile, db: Session = Depends(get_db)):
    user = update_profile(user_id, profile, db)
    return schemas.FarmerProfileResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        is_approved=user.is_approved,
        farm_location=user.farm_location,
        crop_type=user.crop_type,
        phone=user.phone
    )


@app.put("/profile/agronomist/{user_id}", response_model=schemas.AgronomistProfile)
def agronomist_profile(user_id: int, profile: schemas.AgronomistProfile, db: Session = Depends(get_db)):
    user = update_profile(user_id, profile, db)
    return schemas.AgronomistProfile(
        expertise=user.expertise,
        license=user.license,
        phone=user.phone
    )


@app.put("/profile/donor/{user_id}", response_model=schemas.DonorProfile)
def donor_profile(user_id: int, profile: schemas.DonorProfile, db: Session = Depends(get_db)):
    user = update_profile(user_id, profile, db)
    return schemas.DonorProfile(
        donor_type=user.donor_type,
        org_name=user.org_name,
        funding=user.funding,
        phone=user.phone
    )


@app.put("/profile/leader/{user_id}", response_model=schemas.LeaderProfile)
def leader_profile(user_id: int, profile: schemas.LeaderProfile, db: Session = Depends(get_db)):
    user = update_profile(user_id, profile, db)
    return schemas.LeaderProfile(
        leader_title=user.leader_title,
        district=user.district,
        phone=user.phone
    )


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