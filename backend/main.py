from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from uuid import uuid4
from app.api import notebooks, cells
from app.websocket.handler import handle_websocket

# Ensure notebooks directory exists
NOTEBOOKS_DIR = Path(__file__).parent / "notebooks"
NOTEBOOKS_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="Reactive Notebook API",
    version="0.1.0",
    description="File-based reactive notebook backend",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(notebooks.router)
app.include_router(cells.router)

@app.websocket("/api/v1/ws/notebook/{notebook_id}")
async def websocket_endpoint(websocket: WebSocket, notebook_id: str):
    """WebSocket endpoint for real-time notebook updates."""
    connection_id = str(uuid4())
    await handle_websocket(websocket, connection_id, notebook_id)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
