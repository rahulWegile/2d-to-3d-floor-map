import os

PIPELINE_VERSION = 'v7'
import os
SECRET_KEY = os.environ.get("SECRET_KEY", "archtransform_super_secret_key_123")
ALGORITHM = "HS256"
MONGO_URI = os.environ.get("MONGO_URI", "")
