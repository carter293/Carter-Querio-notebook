import os
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from clerk_backend_api import Clerk
from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions
from routes import router, NOTEBOOKS
from storage import list_notebooks, load_notebook, save_notebook
from chat import router as chat_router

load_dotenv(override=True)

app = FastAPI(title="Reactive Notebook")

# Initialize Clerk SDK
CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")
if not CLERK_SECRET_KEY:
    raise ValueError("CLERK_SECRET_KEY environment variable is required")

clerk = Clerk(bearer_auth=CLERK_SECRET_KEY)

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
    Raises HTTPException(401) if token is invalid or missing.
    """
    # Convert FastAPI Request to httpx Request for Clerk SDK
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
        
        # Create httpx Request from FastAPI Request
        url = str(request.url)
        method = request.method
        headers = dict(request.headers)
        
        httpx_request = httpx.Request(
            method=method,
            url=url,
            headers=headers,
        )
        
        # Verify token with Clerk using authenticate_request
        request_state = clerk.authenticate_request(
            httpx_request,
            AuthenticateRequestOptions()
        )
        
        if not request_state.is_signed_in:
            reason = request_state.reason or "Token verification failed"
            raise HTTPException(
                status_code=401,
                detail=f"Authentication failed: {reason}. Please sign in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Extract user_id from token payload
        payload = request_state.payload
        if not payload:
            raise HTTPException(
                status_code=401,
                detail="Invalid token: missing payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid token: missing user ID (sub claim)",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user_id
    
    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid authorization header format: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        # Log the full error for debugging
        error_msg = str(e)
        error_type = type(e).__name__
        raise HTTPException(
            status_code=401,
            detail=f"Authentication error ({error_type}): {error_msg}",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Make clerk and get_current_user available to routes
app.state.clerk = clerk
app.state.get_current_user = get_current_user

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
