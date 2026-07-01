import os

def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

config_code = """import os

PIPELINE_VERSION = 'v4'
SECRET_KEY = "archtransform_super_secret_key_123"
ALGORITHM = "HS256"
import os
MONGO_URI = os.environ.get("MONGO_URI", "")
"""

database_code = """from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import MONGO_URI

client = AsyncIOMotorClient(MONGO_URI)
db = client.floor23d
users_collection = db.users
projects_collection = db.projects
"""

security_code = """import jwt
from datetime import datetime, timedelta
from fastapi import Header, HTTPException
from app.core.config import SECRET_KEY, ALGORITHM

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def get_current_user_optional(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except Exception:
        return None
"""

auth_code = """import bcrypt
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
"""

projects_code = """import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from bson import ObjectId
from app.core.database import projects_collection
from app.core.security import get_current_user

router = APIRouter(prefix="/projects", tags=["projects"])

class ProjectSave(BaseModel):
    user_id: str
    project_id: Optional[str] = None
    name: str
    rawBackendData: list
    settings: Optional[dict] = None

@router.post("/save")
async def save_project(proj: ProjectSave, current_user: str = Depends(get_current_user)):
    if proj.user_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to save for this user")

    project_data = {
        "user_id": proj.user_id,
        "name": proj.name,
        "rawBackendData": proj.rawBackendData,
        "settings": proj.settings or {},
        "lastModified": time.time()
    }
    
    if proj.project_id:
        await projects_collection.update_one(
            {"_id": ObjectId(proj.project_id)},
            {"$set": project_data}
        )
        return {"project_id": proj.project_id}
    else:
        result = await projects_collection.insert_one(project_data)
        return {"project_id": str(result.inserted_id)}

@router.get("/{user_id}")
async def get_projects(user_id: str, current_user: str = Depends(get_current_user)):
    if user_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to view these projects")
        
    cursor = projects_collection.find({"user_id": user_id}).sort("lastModified", -1)
    projects = []
    async for p in cursor:
        projects.append({
            "project_id": str(p["_id"]),
            "name": p.get("name", "Untitled Project"),
            "rawBackendData": p.get("rawBackendData", []),
            "settings": p.get("settings", {}),
            "lastModified": p.get("lastModified", 0)
        })
    return {"projects": projects}

@router.patch("/{project_id}/rename")
async def rename_project(project_id: str, body: dict, current_user: str = Depends(get_current_user)):
    project = await projects_collection.find_one({"_id": ObjectId(project_id)})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.get("user_id") != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to rename this project")
    new_name = body.get("name", "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    await projects_collection.update_one(
        {"_id": ObjectId(project_id)},
        {"$set": {"name": new_name, "lastModified": time.time()}}
    )
    return {"renamed": True}

@router.delete("/{project_id}")
async def delete_project(project_id: str, current_user: str = Depends(get_current_user)):
    project = await projects_collection.find_one({"_id": ObjectId(project_id)})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.get("user_id") != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to delete this project")
    await projects_collection.delete_one({"_id": ObjectId(project_id)})
    return {"deleted": True}
"""

# I will extract the algorithms from the original main.py
with open("main.py", "r", encoding="utf-8") as f:
    main_content = f.read()

import re

# Extract _extract_rooms
extract_rooms_match = re.search(r"def _extract_rooms\(.*?\n\n\n", main_content, re.DOTALL)
extract_rooms_code = extract_rooms_match.group(0) if extract_rooms_match else ""

# Extract _expand_rooms_v1
v1_match = re.search(r"def _expand_rooms_v1\(.*?\n\ndef _expand", main_content, re.DOTALL)
v1_code = v1_match.group(0).replace("def _expand", "") if v1_match else ""

# Extract _expand_rooms_v4
v4_match = re.search(r"def _expand_rooms_v4\(.*?\n\ndef _expand", main_content, re.DOTALL)
v4_code = v4_match.group(0).replace("def _expand", "") if v4_match else ""

# Extract _expand_rooms_v3
v3_match = re.search(r"def _expand_rooms_v3\(.*?\n\ndef process_image", main_content, re.DOTALL)
v3_code = v3_match.group(0).replace("def process_image", "") if v3_match else ""

# Extract process_image
process_image_match = re.search(r"def process_image\(.*?\n\n@app", main_content, re.DOTALL)
process_image_code = process_image_match.group(0).replace("@app", "") if process_image_match else ""

# Replace imports in pipeline
pipeline_imports = "import cv2\nimport numpy as np\nimport math\nfrom app.core.config import PIPELINE_VERSION\nfrom app.services.vision.algorithms import _expand_rooms_v1, _expand_rooms_v3, _expand_rooms_v4\nfrom app.services.vision.core import _extract_rooms\n\n"

# In main.py the reader was global
core_imports = "import re\nimport easyocr\nreader = easyocr.Reader(['en'], gpu=False, verbose=False)\n\n"

# Write vision/core.py
write_file("app/services/vision/core.py", core_imports + extract_rooms_code)

# Write vision/algorithms.py
algorithms_imports = "import cv2\nimport os\n"
write_file("app/services/vision/algorithms.py", algorithms_imports + v1_code + v4_code + v3_code)

# Write vision/pipeline.py
write_file("app/services/vision/pipeline.py", pipeline_imports + process_image_code)

upload_code = """import os
import time
import fitz
from typing import List
from fastapi import APIRouter, File, UploadFile, HTTPException
from app.services.vision.pipeline import process_image

router = APIRouter(prefix="/upload", tags=["upload"])

@router.post("/")
async def upload_files(files: List[UploadFile] = File(...)):
    os.makedirs("uploads", exist_ok=True)
    results = []
    last_error = "unknown"

    for file_idx, file in enumerate(files):
        contents = await file.read()
        try:
            if file.filename.lower().endswith(".pdf"):
                doc = fitz.open(stream=contents, filetype="pdf")
                if len(doc) == 0:
                    continue
                for page_idx in range(len(doc)):
                    page     = doc.load_page(page_idx)
                    pix      = page.get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("png")
                    fname    = f"floor_pdf_{file_idx}_{page_idx}_{int(time.time()*1000)}.png"
                    fpath    = f"uploads/{fname}"
                    with open(fpath, "wb") as f:
                        f.write(img_bytes)
                    walls, rooms, w, h = process_image(img_bytes)
                    results.append({
                        "walls": walls, "rooms": rooms,
                        "imageUrl": f"/{fpath}?t={time.time()}",
                        "width": w, "height": h,
                    })
            else:
                fname = f"floor_img_{file_idx}_{int(time.time()*1000)}.png"
                fpath = f"uploads/{fname}"
                with open(fpath, "wb") as f:
                    f.write(contents)
                walls, rooms, w, h = process_image(contents)
                results.append({
                    "walls": walls, "rooms": rooms,
                    "imageUrl": f"/{fpath}?t={time.time()}",
                    "width": w, "height": h,
                })
        except Exception as e:
            import traceback
            err_detail = traceback.format_exc()
            print(f"[ERROR] processing {file.filename}: {err_detail}")
            last_error = str(e)
            continue

    if not results:
        raise HTTPException(
            status_code=400,
            detail=f"Could not process any floors. Last error: {last_error}"
        )

    return {"floors": results}
"""

main_app_code = """import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, projects, upload

# Create uploads dir if it doesn't exist
os.makedirs("uploads/debug", exist_ok=True)

app = FastAPI(title="ArchTransform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(upload.router)

@app.get("/")
async def root():
    return {"message": "ArchTransform API is running professionally modularized!"}
"""

write_file("app/core/config.py", config_code)
write_file("app/core/database.py", database_code)
write_file("app/core/security.py", security_code)
write_file("app/api/routes/auth.py", auth_code)
write_file("app/api/routes/projects.py", projects_code)
write_file("app/api/routes/upload.py", upload_code)
write_file("app/main.py", main_app_code)

# create __init__.py files
write_file("app/__init__.py", "")
write_file("app/core/__init__.py", "")
write_file("app/api/__init__.py", "")
write_file("app/api/routes/__init__.py", "")
write_file("app/services/__init__.py", "")
write_file("app/services/vision/__init__.py", "")

print("Refactoring complete.")
