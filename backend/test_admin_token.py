"""Diagnose admin-JWT verification.

Usage:
    python test_admin_token.py <ct_access_token>

Paste the token from the admin app: browser DevTools -> Application ->
Local Storage -> ct_access_token.

Prints the token header (algorithm), the unverified claims, whether the
configured secrets verify it, and which user id would be extracted.
"""
import sys
import json
import base64

import jwt
from app.core.config import SECRET_KEY, ALGORITHM, AUTH_JWT_SECRET, AUTH_JWT_ALGORITHMS
from app.core.security import _decode_token, _extract_user_id


def b64json(segment: str):
    segment += "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(segment))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    token = sys.argv[1].strip().removeprefix("Bearer ").strip()

    header = b64json(token.split(".")[0])
    claims = b64json(token.split(".")[1])
    print(f"header    : {header}")
    print(f"claims    : {claims}")
    print(f"user claim: {_extract_user_id(claims)!r}")
    print()

    if not AUTH_JWT_SECRET:
        print("AUTH_JWT_SECRET is NOT set in .env — admin tokens cannot verify.")
    else:
        try:
            jwt.decode(token, AUTH_JWT_SECRET, algorithms=AUTH_JWT_ALGORITHMS,
                       options={"verify_aud": False})
            print(f"AUTH_JWT_SECRET ({AUTH_JWT_ALGORITHMS}): VALID")
        except Exception as e:
            print(f"AUTH_JWT_SECRET ({AUTH_JWT_ALGORITHMS}): FAILED — {e}")

    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM],
                   options={"verify_aud": False})
        print(f"legacy SECRET_KEY ({ALGORITHM}): VALID")
    except Exception as e:
        print(f"legacy SECRET_KEY ({ALGORITHM}): FAILED — {e}")

    print()
    user_id = _decode_token(token)
    print(f"get_current_user would return: {user_id!r}"
          if user_id else "get_current_user would return: 401 Unauthorized")


if __name__ == "__main__":
    main()
