from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core import settings
from app.api import api_router, NOTEBOOKS
from app.storage import load_notebook, list_notebooks

load_dotenv(override=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    print(f"Starting {settings.APP_TITLE}...")
    
    if settings.DYNAMODB_ENABLED:
        print(f"✓ DynamoDB enabled: {settings.DYNAMODB_TABLE_NAME}")
        print("  - Sub-10ms latency for all operations")
        print("  - Serverless auto-scaling enabled")
        print("  - Notebooks will be lazy-loaded on first access")
    else:
        print("Using file-based storage (local dev)")
        # Load existing notebooks from files
        notebook_ids = await list_notebooks()
        if notebook_ids:
            print(f"Loading {len(notebook_ids)} notebook(s)...")
            for notebook_id in notebook_ids:
                try:
                    notebook = await load_notebook(notebook_id)
                    if notebook:
                        NOTEBOOKS[notebook_id] = notebook
                        print(f"  ✓ Loaded: {notebook_id}")
                except Exception as e:
                    print(f"  ✗ Failed: {notebook_id}: {e}")
        else:
            print("No notebooks found. Users will create their own.")
    
    yield
    print("👋 Shutting down...")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title=settings.APP_TITLE,
        lifespan=lifespan,
        debug=settings.DEBUG
    )
    
    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API router with /api/v1 prefix
    app.include_router(api_router, prefix="/api/v1")
    
    # Health check endpoint
    @app.get("/health")
    async def health():
        return {"status": "ok"}
    
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

