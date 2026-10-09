"""
JWT authentication module for SecureRepo API.

Verifies Keycloak JWT tokens with proper cryptographic signature verification.
"""
import logging
import requests
from typing import Optional, Dict
from jose import jwt, jwk
from jose.exceptions import JWTError, JWKError
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import settings

logger = logging.getLogger(__name__)


def _issued_for_client(payload: Dict, client_id: Optional[str]) -> bool:
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


# Keycloak configuration (from environment)
KEYCLOAK_URL = settings.keycloak_url
REALM = settings.keycloak_realm


class TokenVerifier:
    """
    Verifies Keycloak JWT tokens using JWKS (JSON Web Key Set).
    Caches JWKS to avoid repeated requests.
    """

    __slots__ = ['_jwks_cache', '_last_fetch', '_cache_ttl', '_jwks_url']

    def __init__(self, cache_ttl: int = 3600):
        """
        Initialize token verifier.

        Args:
            cache_ttl: How long to cache JWKS keys in seconds (default: 1 hour)
        """
        self._jwks_cache = None
        self._last_fetch = 0
        self._cache_ttl = cache_ttl
        self._jwks_url = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/certs"

    def _get_jwks(self) -> Dict:
        """Fetch JWKS from Keycloak, using cache if available and not expired."""
        import time

        # Use cached JWKS if still valid
        if self._jwks_cache and (time.time() - self._last_fetch) < self._cache_ttl:
            return self._jwks_cache

        # Fetch fresh JWKS from Keycloak
        try:
            logger.info(f"Fetching JWKS from {self._jwks_url}")
            response = requests.get(self._jwks_url, timeout=10)
            response.raise_for_status()

            jwks = response.json()

            # Update cache
            self._jwks_cache = jwks
            self._last_fetch = time.time()

            logger.info(f"Successfully fetched JWKS with {len(jwks.get('keys', []))} keys")
            return jwks

        except requests.RequestException as e:
            logger.error(f"Failed to fetch JWKS from Keycloak: {e}")
            # If cache exists but is expired, use stale data as fallback
            if self._jwks_cache:
                logger.warning("Using stale JWKS cache as fallback")
                return self._jwks_cache
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to verify token - Keycloak JWKS endpoint unavailable"
            )

    def verify_token(self, token: str) -> Dict:
        """
        Verify JWT token signature and claims.

        Args:
            token: JWT token string (without "Bearer " prefix)

        Returns:
            Decoded token payload

        Raises:
            HTTPException: If token is invalid, expired, or signature verification fails
        """
        try:
            # Get JWKS with public keys
            jwks = self._get_jwks()

            # kid is a field of the JWK. CryptographyRSAKey from jwk.construct() does not expose key_id.
            headers = jwt.get_unverified_headers(token)
            key_id = headers.get('kid')

            if not key_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token missing key identifier (kid)"
                )

            algorithm = headers.get('alg') or 'RS256'
            public_key = None
            for key_data in jwks.get('keys', []):
                if key_data.get('kid') != key_id or key_data.get('use') not in (None, 'sig'):
                    continue
                public_key = jwk.construct(key_data, key_data.get('alg') or algorithm)
                break

            if public_key is None:
                logger.error(f"Token key_id {key_id} not found in JWKS")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token signed with unknown key"
                )

            # Get issuer from token or use configured one
            unverified_payload = jwt.get_unverified_claims(token)
            issuer = unverified_payload.get('iss', f"{KEYCLOAK_URL}/realms/{REALM}")

            # Verify signature and decode token
            # This will raise JWTError if signature is invalid or token is expired.
            # Keycloak puts the client id in azp; aud is often only "account".
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
                    'verify_nbf': True,  # Verify not-before
                    'require_iat': True,  # Require issued-at timestamp
                }
            )

            if not _issued_for_client(payload, settings.keycloak_audience):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token was not issued for this client"
                )

            logger.debug(f"Successfully verified token for user: {payload.get('sub')}")

            return payload

        except JWTError as e:
            logger.warning(f"JWT verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}"
            )
        except JWKError as e:
            logger.error(f"JWK construction error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token verification error"
            )


# Global token verifier instance
_token_verifier = TokenVerifier(cache_ttl=3600)  # Cache for 1 hour


# FastAPI security scheme
security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """
    FastAPI dependency to extract and verify user ID from JWT token.

    Args:
        credentials: HTTP Authorization header (Bearer token)

    Returns:
        user_id: User ID from token's "sub" claim

    Raises:
        HTTPException: If token is missing, invalid, or expired
    """
    token = credentials.credentials
    payload = _token_verifier.verify_token(token)

    user_id = payload.get('sub')
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identifier (sub claim)"
        )

    return user_id


def validate_token_manual(token: str) -> str:
    """
    Manual token validation (for non-dependency contexts).

    Args:
        token: JWT token string (without "Bearer " prefix)

    Returns:
        user_id: User ID from token's "sub" claim

    Raises:
        HTTPException: If token is invalid
    """
    payload = _token_verifier.verify_token(token)
    user_id = payload.get('sub')

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identifier (sub claim)"
        )

    return user_id
