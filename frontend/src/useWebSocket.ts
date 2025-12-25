import { useEffect, useRef, useCallback } from 'react';

export type WSMessage =
  | { type: 'cell_status'; cellId: string; status: string }
  | { type: 'cell_stdout'; cellId: string; data: string }
  | { type: 'cell_result'; cellId: string; result: any }
  | { type: 'cell_error'; cellId: string; error: string };

export function useWebSocket(
  notebookId: string,
  onMessage: (msg: WSMessage) => void
) {
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    const websocket = new WebSocket(
      `ws://localhost:8000/api/ws/notebooks/${notebookId}`
    );

    websocket.onopen = () => {
      console.log('WebSocket connected');
    };

    websocket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      onMessage(message);
    };

    websocket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    websocket.onclose = () => {
      console.log('WebSocket disconnected');
    };

    ws.current = websocket;

    return () => {
      websocket.close();
    };
  }, [notebookId, onMessage]);

  const sendMessage = useCallback((message: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(message));
    }
  }, []);

  return { sendMessage };
}
