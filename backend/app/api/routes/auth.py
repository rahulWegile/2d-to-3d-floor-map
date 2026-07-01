import bcrypt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.database import users_collection
from app.core.security import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

class UserSignup(BaseModel):
    email: str
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

@router.post("/signup")
async def signup(user: UserSignup):
    normalized_username = user.username.lower()
    normalized_email = user.email.lower()

    db_user = await users_collection.find_one({"username": normalized_username})
    if db_user:
        raise HTTPException(status_code=400, detail="Username already exists")
    db_email = await users_collection.find_one({"email": normalized_email})
    if db_email:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    new_user = {"email": normalized_email, "username": normalized_username, "password": hashed_password}
    result = await users_collection.insert_one(new_user)
    
    user_id_str = str(result.inserted_id)
    token = create_access_token({"sub": user_id_str})
    return {"success": True, "token": token, "user_id": user_id_str, "username": normalized_username}

@router.post("/login")
async def login(user: UserLogin):
    normalized_username = user.username.lower()
    db_user = await users_collection.find_one({
        "$or": [
            {"username": normalized_username},
            {"email": normalized_username}
        ]
    })
    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not bcrypt.checkpw(user.password.encode('utf-8'), db_user["password"].encode('utf-8')):
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    user_id_str = str(db_user["_id"])
    token = create_access_token({"sub": user_id_str})
    return {"success": True, "token": token, "user_id": user_id_str, "username": user.username}

@router.post("/logout")
async def logout():
    return {"success": True}
