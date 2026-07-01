import os
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
