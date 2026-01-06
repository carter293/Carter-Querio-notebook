from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict
from ..orchestration.coordinator import NotebookCoordinator


class ConnectionManager:
    """Manage active WebSocket connections."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.coordinators: Dict[str, NotebookCoordinator] = {}

    async def connect(self, websocket: WebSocket, connection_id: str, notebook_id: str):
        await websocket.accept()
        self.active_connections[connection_id] = websocket

        # Create coordinator for this connection
        coordinator = NotebookCoordinator(broadcaster=self)
        coordinator.load_notebook(notebook_id)
        self.coordinators[connection_id] = coordinator

    def disconnect(self, connection_id: str):
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        if connection_id in self.coordinators:
            del self.coordinators[connection_id]

    async def send_message(self, connection_id: str, message: dict):
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            await websocket.send_json(message)

    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        for websocket in self.active_connections.values():
            await websocket.send_json(message)


manager = ConnectionManager()


async def handle_websocket(websocket: WebSocket, connection_id: str, notebook_id: str):
    """Handle WebSocket connection lifecycle."""
    await manager.connect(websocket, connection_id, notebook_id)
    coordinator = manager.coordinators[connection_id]

    try:
        # Wait for authentication
        auth_message = await websocket.receive_json()
        if auth_message.get("type") != "authenticate":
            await websocket.close(code=1008, reason="Authentication required")
            return

        # Send authentication success
        await manager.send_message(connection_id, {"type": "authenticated"})

        # Message loop
        while True:
            message = await websocket.receive_json()
            await handle_message(connection_id, coordinator, message)

    except WebSocketDisconnect:
        manager.disconnect(connection_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(connection_id)


async def handle_message(connection_id: str, coordinator: NotebookCoordinator, message: dict):
    """Handle incoming WebSocket messages."""
    msg_type = message.get("type")

    if msg_type == "run_cell":
        cell_id = message.get("cellId")
        if cell_id:
            await coordinator.handle_run_cell(cell_id)
    else:
        print(f"Unknown message type: {msg_type}")
