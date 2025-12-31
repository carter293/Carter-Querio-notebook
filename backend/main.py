import os
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
import jwt
from jwt import PyJWKClient
from routes import router, NOTEBOOKS
from storage import list_notebooks, load_notebook, save_notebook
from chat import router as chat_router

load_dotenv(override=True)

app = FastAPI(title="Reactive Notebook")

# Initialize Clerk JWT verification
CLERK_FRONTEND_API = os.getenv("CLERK_FRONTEND_API")
if not CLERK_FRONTEND_API:
    raise ValueError("CLERK_FRONTEND_API environment variable is required (e.g., 'your-app.clerk.accounts.dev')")

JWKS_URL = f"https://{CLERK_FRONTEND_API}/.well-known/jwks.json"

# Initialize PyJWKClient for JWT verification
jwks_client = PyJWKClient(
    uri=JWKS_URL,
    cache_keys=True,
    max_cached_keys=16,
    cache_jwk_set=True,
    lifespan=300,
)

# CORS configuration with environment variable support
allowed_origins_str = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173"
)
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,  # Required for Clerk cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentication dependency
async def get_current_user(request: Request):
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

# Make get_current_user and jwks_client available to routes
app.state.get_current_user = get_current_user
app.state.jwks_client = jwks_client

@app.on_event("startup")
async def startup_event():
    notebook_ids = list_notebooks()

    if notebook_ids:
        print(f"Loading {len(notebook_ids)} notebook(s)...")
        for notebook_id in notebook_ids:
            try:
                notebook = load_notebook(notebook_id)
                NOTEBOOKS[notebook_id] = notebook
                print(f"  ✓ Loaded: {notebook_id}")
            except Exception as e:
                print(f"  ✗ Failed: {notebook_id}: {e}")
    else:
        # Note: Demo notebook creation removed - requires user_id
        print("No notebooks found. Users will create their own.")

app.include_router(router, prefix="/api")
app.include_router(chat_router, prefix="/api", tags=["chat"])

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
