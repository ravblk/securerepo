import os
import json
import base64
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Query, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jose import jwt, jwk
from jose.exceptions import JWTError

app = FastAPI(title="SecureRepo Frontend")

# Config
API_URL = os.getenv("API_URL", "http://api:8000")
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")  # For server-side calls
BROWSER_KEYCLOAK_URL = os.getenv("BROWSER_KEYCLOAK_URL", "http://localhost:8180")  # For browser redirects
REALM = os.getenv("KEYCLOAK_REALM", "securerepo")
CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "securerepo-api")
CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "securerepo-secret")

templates = Jinja2Templates(directory="templates")


def _issued_for_client(payload: dict, client_id: str) -> bool:
    """Keycloak access tokens carry the client id in azp; aud is often just \"account\"."""
    if not client_id:
        return True
    aud = payload.get("aud")
    if isinstance(aud, str):
        audiences = [aud]
    elif isinstance(aud, list):
        audiences = aud
    else:
        audiences = []
    return client_id in audiences or payload.get("azp") == client_id


def validate_token(token: str) -> dict:
    """
    Validate JWT token and return payload.

    This uses proper cryptographic signature verification with Keycloak public keys.
    A malicious user cannot forge tokens without the private key.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Token required")

    try:
        # Fetch JWKS (JSON Web Key Set) from Keycloak
        jwks_url = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/certs"
        response = httpx.get(jwks_url, timeout=5)
        response.raise_for_status()
        jwks = response.json()

        # kid is a field of the JWK. CryptographyRSAKey from jwk.construct() does not expose key_id.
        headers = jwt.get_unverified_headers(token)
        key_id = headers.get('kid')
        if not key_id:
            raise HTTPException(status_code=401, detail="Token missing key identifier (kid)")

        algorithm = headers.get('alg') or 'RS256'
        public_key = None
        for key_data in jwks.get('keys', []):
            if key_data.get('kid') != key_id or key_data.get('use') not in (None, 'sig'):
                continue
            public_key = jwk.construct(key_data, key_data.get('alg') or algorithm)
            break

        if public_key is None:
            raise HTTPException(status_code=401, detail="Token signed with unknown key")

        # Get issuer from token
        unverified_payload = jwt.get_unverified_claims(token)
        issuer = unverified_payload.get('iss', f"{KEYCLOAK_URL}/realms/{REALM}")

        # Verify signature and decode token
        # This will raise JWTError if signature is invalid or token is expired.
        # Keycloak puts the client id in azp; aud is often only "account", so audience
        # is checked below instead of via verify_aud.
        payload = jwt.decode(
            token,
            public_key,
            algorithms=['RS256'],  # Keycloak uses RS256
            issuer=issuer,
            options={
                'verify_signature': True,  # CRITICAL: verify cryptographic signature
                'verify_issuer': True,
                'verify_aud': False,
                'verify_exp': True,  # Verify expiration
                'verify_nbf': True,
                'require_iat': True,
            }
        )

        if not _issued_for_client(payload, CLIENT_ID):
            raise HTTPException(status_code=401, detail="Token was not issued for this client")

        # Validate required fields
        if not payload.get('sub'):
            raise HTTPException(status_code=401, detail="Invalid token payload: missing sub claim")

        return payload

    except httpx.HTTPError as e:
        print(f"Token validation error - Keycloak unreachable: {str(e)}")
        raise HTTPException(status_code=503, detail="Unable to verify token - Keycloak unreachable")
    except JWTError as e:
        print(f"Token validation error: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Token validation error: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


def extract_user_from_token(authorization: str) -> Optional[str]:
    """Extract user_id from Authorization header"""
    print(f"DEBUG: Extract user from token called, auth: {authorization[:20] if authorization else None}...")

    if not authorization:
        print("DEBUG: No authorization header")
        return None

    try:
        # Remove "Bearer " prefix if present
        if authorization.startswith("Bearer "):
            token = authorization[7:]
        else:
            token = authorization

        print(f"DEBUG: Token extracted, length: {len(token)}")

        # Validate and extract user_id
        payload_data = validate_token(token)
        user_id = payload_data.get('sub')

        print(f"DEBUG: User ID extracted: {user_id}")
        return user_id
    except HTTPException as e:
        print(f"DEBUG: HTTP Exception: {e}")
        return None
    except Exception as e:
        print(f"DEBUG: Unexpected error: {e}")
        return None


@app.get("/", response_class=HTMLResponse)
async def root():
    """Главная страница - перенаправление на login"""
    with open("templates/index.html", "r") as f:
        return f.read()


@app.get("/login", response_class=HTMLResponse)
async def login():
    """Страница логина - редирект на Keycloak"""
    with open("templates/login.html", "r") as f:
        content = f.read()
        content = content.replace("{{KEYCLOAK_URL}}", BROWSER_KEYCLOAK_URL)
        content = content.replace("{{REALM}}", REALM)
        content = content.replace("{{CLIENT_ID}}", CLIENT_ID)
        return HTMLResponse(
            content=content,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Дашборд - основная страница после логина"""
    with open("templates/dashboard.html", "r") as f:
        content = f.read()
        content = content.replace("{{API_URL}}", API_URL)
        return HTMLResponse(
            content=content,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )


@app.get("/callback", response_class=HTMLResponse)
async def callback():
    """Callback от Keycloak - обработка кода авторизации"""
    with open("templates/callback.html", "r") as f:
        return f.read()


@app.post("/auth/token", response_class=JSONResponse)
async def get_token(request: Request):
    """Обмен кода авторизации на токен"""
    body = await request.json()
    code = body.get("code")
    redirect_uri = body.get("redirect_uri")

    if not code:
        raise HTTPException(status_code=400, detail="Code required")

    import httpx
    try:
        async with httpx.AsyncClient() as client:
            token_url = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token"
            response = await client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": redirect_uri
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token"),
                    "expires_in": data.get("expires_in"),
                    "token_type": data.get("token_type")
                }
            else:
                raise HTTPException(status_code=400, detail="Failed to get token")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/refresh", response_class=JSONResponse)
async def refresh_access_token(request: Request):
    """Обмен refresh token на новый access token в Keycloak."""
    body = await request.json()
    refresh_token = body.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Refresh token required")

    token_url = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_url,
                data={
                    "grant_type": "refresh_token",
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.HTTPError as e:
        print(f"Token refresh error - Keycloak unreachable: {e}")
        raise HTTPException(status_code=503, detail="Keycloak unreachable")

    if response.status_code != 200:
        print(f"Token refresh rejected by Keycloak: {response.status_code}")
        raise HTTPException(status_code=401, detail="Failed to refresh token")

    data = response.json()
    return {
        "access_token": data.get("access_token"),
        "refresh_token": data.get("refresh_token") or refresh_token,
        "expires_in": data.get("expires_in"),
        "token_type": data.get("token_type"),
    }


@app.get("/api/audits", response_class=JSONResponse)
async def get_audits(
    authorization: str = Header(None),
    status: str = None,
    limit: int = 10,
    offset: int = 0
):
    """Получение списка аудитов (прокси к API с валидацией токена)"""
    print(f"DEBUG /api/audits: authorization header: {authorization[:50] if authorization else None}...")

    user_id = extract_user_from_token(authorization)
    if not user_id:
        print(f"DEBUG /api/audits: No user_id extracted, returning 401")
        raise HTTPException(status_code=401, detail="Unauthorized")

    print(f"DEBUG /api/audits: User_id extracted: {user_id}")

    import httpx
    try:
        # Build URL with query params (excluding user_id)
        params = {}
        if status:
            params['status'] = status
        params['limit'] = limit
        params['offset'] = offset

        async with httpx.AsyncClient() as client:
            # Forward Authorization header but don't include user_id in query
            response = await client.get(
                f"{API_URL}/audit",
                params=params,
                headers={"Authorization": authorization},
                timeout=30.0
            )
            return response.json()
    except Exception as e:
        print(f"DEBUG /api/audits: API call failed: {e}")
        return {"error": str(e), "items": [], "total": 0}


@app.post("/api/audits/start", response_class=JSONResponse)
async def start_audit(request: Request, authorization: str = Header(None)):
    """Запуск аудита (прокси к API с валидацией токена)"""
    body = await request.json()

    # Validate token and extract user_id
    user_id = extract_user_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Add user_id to request body
    body['user_id'] = user_id

    import httpx
    try:
        async with httpx.AsyncClient() as client:
            # Forward Authorization header - API service will verify and override user_id
            response = await client.post(
                f"{API_URL}/audit/start",
                json=body,
                headers={"Authorization": authorization},
                timeout=30.0
            )
            return response.json()
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/audits/{audit_id}/status", response_class=JSONResponse)
async def get_audit_status(audit_id: str, authorization: str = Header(None)):
    """Получение статуса аудита (прокси к API с валидацией токена)"""
    user_id = extract_user_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    import httpx
    try:
        async with httpx.AsyncClient() as client:
            # Forward Authorization header but don't include user_id in query
            response = await client.get(
                f"{API_URL}/audit/{audit_id}/status",
                headers={"Authorization": authorization},
                timeout=30.0
            )
            return response.json()
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/audits/{audit_id}/report", response_class=JSONResponse)
async def get_audit_report(audit_id: str, authorization: str = Header(None)):
    """Получение отчёта аудита (прокси к API с валидацией токена)"""
    user_id = extract_user_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    import httpx
    try:
        async with httpx.AsyncClient() as client:
            # Forward Authorization header but don't include user_id in query
            response = await client.get(
                f"{API_URL}/audit/{audit_id}/report",
                headers={"Authorization": authorization},
                timeout=30.0
            )
            return response.json()
    except Exception as e:
        return {"error": str(e)}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "frontend"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
