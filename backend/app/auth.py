import os
import jwt
import requests
import json
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt.exceptions import PyJWTError

security = HTTPBearer()

CLERK_FRONTEND_API = os.getenv(
    "CLERK_FRONTEND_API", "https://actual-earwig-78.clerk.accounts.dev"
)
CLERK_JWKS_URL = f"{CLERK_FRONTEND_API}/.well-known/jwks.json"

JWKS_FILE_PATH = os.path.join(os.path.dirname(__file__), "clerk_jwks.json")


def get_clerk_public_key(token: str):
    """
    دریافت کلیدهای عمومی (ابتدا به صورت آفلاین و در صورت عدم وجود، آنلاین)
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(
                status_code=401, detail="توکن ساختار معتبری ندارد (فاقد kid)"
            )

        jwks = None

        if os.path.exists(JWKS_FILE_PATH):
            try:
                with open(JWKS_FILE_PATH, "r", encoding="utf-8") as f:
                    jwks = json.load(f)
                    print(
                        "🟢 [Clerk Auth] Public keys successfully loaded from local cache."
                    )
            except Exception as file_err:
                print(f"⚠️ Warning: Could not read local JWKS file: {str(file_err)}")

        if not jwks:
            print("🌐 [Clerk Auth] Local cache missing. Fetching keys online...")
            response = requests.get(CLERK_JWKS_URL)
            jwks = response.json()

        print(f"🔍 DEBUG: Token kid from Frontend is: '{kid}'")
        print(
            f"🔍 DEBUG: Available kids in JSON file: {[k.get('kid') for k in jwks.get('keys', [])]}"
        )

        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return jwt.algorithms.RSAAlgorithm.from_jwk(key)

        raise HTTPException(status_code=401, detail="کلید تایید امضا پیدا نشد.")
    except Exception as e:
        raise HTTPException(
            status_code=401, detail=f"خطا در واکشی کلید عمومی: {str(e)}"
        )


def verify_clerk_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    تابع میان‌بر (Dependency) برای بررسی و تایید نهایی توکن JWT کلرک
    """
    token = credentials.credentials
    print(f"📡 Token Received from Frontend: '{token[:20]}...'")
    try:
        public_key = get_clerk_public_key(token)

        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
            leeway=60,
        )

        return payload

    except jwt.ExpiredSignatureError:
        print("❌ Real Clerk Auth Error: Token has expired!")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="توکن امنیتی شما منقضی شده است.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (PyJWTError, Exception) as e:
        print("❌ Real Clerk Auth Error:", str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"دسترسی غیرمجاز: توکن نامعتبر است. {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
