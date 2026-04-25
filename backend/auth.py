"""Clerk JWT verification for FastAPI.

Verifies short-lived JWTs issued by Clerk using the JWKS endpoint.
Falls back to allowing unauthenticated requests when Clerk is not
configured (CLERK_JWKS_URL env var missing), so local development
without Clerk still works.
"""

import os
import logging

import jwt
import httpx
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt.algorithms import RSAAlgorithm

logger = logging.getLogger("pii_shield.auth")

CLERK_JWKS_URL = os.getenv(
    "CLERK_JWKS_URL",
    "https://ace-reptile-21.clerk.accounts.dev/.well-known/jwks.json",
)

security = HTTPBearer(auto_error=False)

# In-memory JWKS cache — refreshed on process restart.
_jwks_cache: dict | None = None


def get_jwks() -> dict:
    """Fetch and cache the JSON Web Key Set from Clerk."""
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache

    try:
        response = httpx.get(CLERK_JWKS_URL, timeout=5.0)
        response.raise_for_status()
        _jwks_cache = response.json()
        return _jwks_cache
    except Exception as exc:
        logger.warning("Failed to fetch JWKS from %s: %s", CLERK_JWKS_URL, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )


def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """Dependency that verifies the Clerk JWT and returns the payload.

    Returns a dict with at least ``"sub"`` (the Clerk user ID).
    If no Authorization header is present, raises 401.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    jwks = get_jwks()

    try:
        unverified_header = jwt.get_unverified_header(token)
        rsa_key: dict = {}
        for key in jwks.get("keys", []):
            if key["kid"] == unverified_header.get("kid"):
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"],
                }
                break

        if not rsa_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to find appropriate signing key",
            )

        public_key = RSAAlgorithm.from_jwk(rsa_key)

        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
