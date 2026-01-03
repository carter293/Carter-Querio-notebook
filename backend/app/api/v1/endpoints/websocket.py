from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core import verify_clerk_token
from app.execution import scheduler
from app.websocket import broadcaster
from app.api.v1.state import NOTEBOOKS
import asyncio

router = APIRouter()


@router.websocket("/ws/notebooks/{notebook_id}")
async def notebook_websocket(websocket: WebSocket, notebook_id: str):
    """
    WebSocket endpoint for real-time notebook updates.
    
    Authentication Flow:
    1. Accept connection
    2. Wait for authentication message: {"type": "authenticate", "token": "..."}
    3. Verify token and extract user_id
    4. Send confirmation: {"type": "authenticated"}
    5. Proceed with normal message handling
    """
    
    # Accept connection immediately (auth happens in-band)
    await websocket.accept()
    
    # Step 1: Wait for authentication message
    try:
        # Set timeout for auth message (10 seconds)
        auth_message = await asyncio.wait_for(
            websocket.receive_json(),
            timeout=10.0
        )
    except asyncio.TimeoutError:
        await websocket.send_json({
            "type": "error",
            "message": "Authentication timeout"
        })
        await websocket.close(code=1008, reason="Authentication timeout")
        return
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": f"Failed to receive authentication: {str(e)}"
        })
        await websocket.close(code=1008, reason="Invalid message format")
        return
    
    # Step 2: Validate authentication message format
    if not isinstance(auth_message, dict) or auth_message.get("type") != "authenticate":
        await websocket.send_json({
            "type": "error",
            "message": "Expected authentication message"
        })
        await websocket.close(code=1008, reason="Expected authentication message")
        return
    
    token = auth_message.get("token")
    if not token:
        await websocket.send_json({
            "type": "error",
            "message": "Missing authentication token"
        })
        await websocket.close(code=1008, reason="Missing token")
        return
    
    # Step 3: Verify token using JWT
    user_id = await verify_clerk_token(token)
    
    if not user_id:
        await websocket.send_json({
            "type": "error",
            "message": "Invalid authentication token"
        })
        await websocket.close(code=1008, reason="Invalid token")
        return
    
    # Step 4: Send authentication confirmation
    await websocket.send_json({
        "type": "authenticated",
        "user_id": user_id
    })
    
    # Handle legacy notebook IDs
    if notebook_id == "demo":
        notebook_id = f"demo-{user_id}"
    elif notebook_id == "blank":
        notebook_id = f"blank-{user_id}"
    
    # Check if notebook exists
    if notebook_id not in NOTEBOOKS:
        await websocket.send_json({
            "type": "error",
            "message": "Notebook not found"
        })
        await websocket.close(code=1008, reason="Notebook not found")
        return
    
    # Verify notebook ownership
    notebook = NOTEBOOKS[notebook_id]
    if notebook.user_id != user_id:
        await websocket.send_json({
            "type": "error",
            "message": "Access denied: You don't have permission to access this notebook"
        })
        await websocket.close(code=1008, reason="Access denied")
        return
    
    # Connection established and authenticated
    await broadcaster.connect(notebook_id, websocket)

    try:
        while True:
            message = await websocket.receive_json()

            if message["type"] == "run_cell":
                cell_id = message["cellId"]
                
                # Re-verify notebook ownership before execution
                if notebook_id not in NOTEBOOKS:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Notebook not found"
                    })
                    continue
                
                notebook = NOTEBOOKS[notebook_id]
                if notebook.user_id != user_id:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Access denied"
                    })
                    continue

                await scheduler.enqueue_run(notebook_id, cell_id, notebook, broadcaster)
            
            elif message["type"] == "refresh_auth":
                # Support mid-connection token refresh
                new_token = message.get("token")
                if not new_token:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Missing token in refresh request"
                    })
                    continue
                
                new_user_id = await verify_clerk_token(new_token)
                
                if not new_user_id or new_user_id != user_id:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Token refresh failed: user mismatch"
                    })
                    # Don't close connection - keep using old auth
                    continue
                
                await websocket.send_json({
                    "type": "auth_refreshed"
                })

    except WebSocketDisconnect:
        await broadcaster.disconnect(notebook_id, websocket)
