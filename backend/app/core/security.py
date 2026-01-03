import jwt
from jwt import PyJWKClient
from fastapi import HTTPException, Request
from typing import Optional
from .config import settings


# Initialize PyJWKClient for JWT verification
jwks_client = PyJWKClient(
    uri=settings.jwks_url,
    cache_keys=True,
    max_cached_keys=16,
    cache_jwk_set=True,
    lifespan=300,
)


async def get_current_user(request: Request) -> str:
    """
    Verify Clerk JWT token and return user ID.
    Uses PyJWT with Clerk's JWKS endpoint for verification.
    Raises HTTPException(401) if token is invalid or missing.
    """
    auth_header = request.headers.get("authorization")
    if not auth_header:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization header. Please sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        # Extract token from "Bearer <token>" format
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Invalid authorization header format. Expected 'Bearer <token>'.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token = parts[1]
        
        # Get signing key from JWKS
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        # Decode and verify JWT token
        decoded_token = jwt.decode(
            token,
            key=signing_key.key,
            algorithms=["RS256"],
            options={
                "verify_exp": True,
                "verify_aud": False,
                "verify_iss": False,
                "verify_iat": True,
            },
            leeway=0,
        )
        
        # Extract user_id from 'sub' claim
        user_id = decoded_token.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid token: missing user ID (sub claim)",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user_id
    
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        raise HTTPException(
            status_code=401,
            detail=f"Authentication error ({error_type}): {error_msg}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def verify_clerk_token(token: str) -> Optional[str]:
    """
    Verify Clerk JWT token and extract user_id.
    Used for WebSocket authentication.
    
    Args:
        token: JWT token string (without "Bearer " prefix)
        
    Returns:
        user_id if token is valid, None otherwise
    """
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        decoded_token = jwt.decode(
            token,
            key=signing_key.key,
            algorithms=["RS256"],
            options={
                "verify_exp": True,
                "verify_aud": False,
                "verify_iss": False,
                "verify_iat": True,
            },
            leeway=0,
        )
        
        return decoded_token.get("sub")
        
    except Exception as e:
        print(f"Token verification error: {e}")
        return None

