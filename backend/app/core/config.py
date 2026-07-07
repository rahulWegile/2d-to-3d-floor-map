import os

# Extremely simple .env parser so we don't need python-dotenv
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k, v = k.strip(), v.strip(' "\'')
            # Real environment variables win; empty .env values are ignored.
            if v and k not in os.environ:
                os.environ[k] = v

PIPELINE_VERSION = 'v7'

# Legacy secret for tokens issued by this service's own /auth endpoints.
SECRET_KEY = os.environ.get("SECRET_KEY", "archtransform_super_secret_key_123")
ALGORITHM = "HS256"

# Secret used by the CompleTech auth service to sign the admin session JWT
# (ct_access_token). Must match the auth service's JWT signing secret so this
# backend can verify tokens sent by completech-admin-web. When unset, only
# legacy self-issued tokens are accepted.
AUTH_JWT_SECRET = os.environ.get("AUTH_JWT_SECRET", "")
# Comma-separated list, e.g. "HS256" or "HS256,RS256".
AUTH_JWT_ALGORITHMS = [
    a.strip() for a in os.environ.get("AUTH_JWT_ALGORITHMS", "HS256").split(",") if a.strip()
]

# Base URL of the CompleTech auth service. When AUTH_JWT_SECRET is not set (or
# doesn't match), tokens are validated by calling this service's /auth/refresh
# endpoint instead (introspection). Results are cached per token.
AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "").rstrip("/")

MONGO_URI = os.environ.get("MONGO_URI", "")
