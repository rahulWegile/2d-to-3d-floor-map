import os

# Extremely simple .env parser so we don't need python-dotenv
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ[k] = v.strip(' "\'')

PIPELINE_VERSION = 'v7'
SECRET_KEY = os.environ.get("SECRET_KEY", "archtransform_super_secret_key_123")
ALGORITHM = "HS256"
MONGO_URI = os.environ.get("MONGO_URI", "")
