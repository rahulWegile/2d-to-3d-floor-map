from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import MONGO_URI

client = AsyncIOMotorClient(MONGO_URI)
db = client.floor23d
users_collection = db.users
projects_collection = db.projects
