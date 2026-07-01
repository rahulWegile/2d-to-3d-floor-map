import time
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
