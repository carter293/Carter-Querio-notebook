from fastapi import WebSocket
from typing import Dict, Set
import json

# Import for type hints
try:
    from models import CellStatus
except ImportError:
    CellStatus = None

class WebSocketBroadcaster:
    def __init__(self):
        self.connections: Dict[str, Set[WebSocket]] = {}  # notebook_id -> websockets

    async def connect(self, notebook_id: str, websocket: WebSocket):
        """Add a WebSocket connection"""
        if notebook_id not in self.connections:
            self.connections[notebook_id] = set()
        self.connections[notebook_id].add(websocket)

    async def disconnect(self, notebook_id: str, websocket: WebSocket):
        """Remove a WebSocket connection"""
        if notebook_id in self.connections:
            self.connections[notebook_id].discard(websocket)

    async def broadcast(self, notebook_id: str, message: dict):
        """Send message to all connected clients for this notebook"""
        if notebook_id not in self.connections:
            return

        dead_connections = set()
        for websocket in self.connections[notebook_id]:
            try:
                await websocket.send_json(message)
            except Exception:
                dead_connections.add(websocket)

        # Clean up dead connections
        for ws in dead_connections:
            self.connections[notebook_id].discard(ws)

    async def broadcast_cell_status(self, notebook_id: str, cell_id: str, status):
        await self.broadcast(notebook_id, {
            "type": "cell_status",
            "cellId": cell_id,
            "status": status.value if hasattr(status, 'value') else str(status)
        })

    async def broadcast_cell_stdout(self, notebook_id: str, cell_id: str, data: str):
        await self.broadcast(notebook_id, {
            "type": "cell_stdout",
            "cellId": cell_id,
            "data": data
        })

    async def broadcast_cell_result(self, notebook_id: str, cell_id: str, result):
        await self.broadcast(notebook_id, {
            "type": "cell_result",
            "cellId": cell_id,
            "result": result
        })

    async def broadcast_cell_error(self, notebook_id: str, cell_id: str, error: str):
        await self.broadcast(notebook_id, {
            "type": "cell_error",
            "cellId": cell_id,
            "error": error
        })

# Global broadcaster instance
broadcaster = WebSocketBroadcaster()
