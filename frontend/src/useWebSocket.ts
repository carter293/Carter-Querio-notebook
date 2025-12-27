import { useEffect, useRef, useCallback, useState } from 'react';
import type { CellResponse, OutputResponse, CellStatus } from './client/types.gen';

// WebSocket message types - these match the backend WebSocket broadcaster in backend/websocket.py
// Note: WebSocket messages are not part of the OpenAPI spec, so these are manually maintained
// but should match the backend implementation exactly
// 
// Using a discriminated union pattern for type safety and narrowing
export type WSMessage =
  | { type: 'cell_updated'; cellId: string; cell: { code: string; reads: string[]; writes: string[]; status: string } }
  | { type: 'cell_created'; cellId: string; cell: CellResponse }
  | { type: 'cell_deleted'; cellId: string }
  | { type: 'cell_status'; cellId: string; status: CellStatus }
  | { type: 'cell_stdout'; cellId: string; data: string }
  | { type: 'cell_error'; cellId: string; error: string }
  | { type: 'cell_output'; cellId: string; output: OutputResponse };

// Type guard helpers for better type narrowing
export function isWSMessage(msg: unknown): msg is WSMessage {
  return (
    typeof msg === 'object' &&
    msg !== null &&
    'type' in msg &&
    'cellId' in msg &&
    typeof (msg as { type: unknown; cellId: unknown }).type === 'string' &&
    typeof (msg as { cellId: unknown }).cellId === 'string'
  );
}

// Specific type guards for each message type
export function isCellUpdated(msg: WSMessage): msg is Extract<WSMessage, { type: 'cell_updated' }> {
  return msg.type === 'cell_updated';
}

export function isCellCreated(msg: WSMessage): msg is Extract<WSMessage, { type: 'cell_created' }> {
  return msg.type === 'cell_created';
}

export function isCellDeleted(msg: WSMessage): msg is Extract<WSMessage, { type: 'cell_deleted' }> {
  return msg.type === 'cell_deleted';
}

export function isCellStatus(msg: WSMessage): msg is Extract<WSMessage, { type: 'cell_status' }> {
  return msg.type === 'cell_status';
}

export function isCellStdout(msg: WSMessage): msg is Extract<WSMessage, { type: 'cell_stdout' }> {
  return msg.type === 'cell_stdout';
}

export function isCellError(msg: WSMessage): msg is Extract<WSMessage, { type: 'cell_error' }> {
  return msg.type === 'cell_error';
}

export function isCellOutput(msg: WSMessage): msg is Extract<WSMessage, { type: 'cell_output' }> {
  return msg.type === 'cell_output';
}

export function useWebSocket(
  notebookId: string,
  onMessage: (msg: WSMessage) => void
) {
  const ws = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;
  const reconnectDelay = 1000; // Start with 1 second

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    const websocket = new WebSocket(
      `ws://localhost:8000/api/ws/notebooks/${notebookId}`
    );

    websocket.onopen = () => {
      console.log('WebSocket connected');
      setConnected(true);
      reconnectAttempts.current = 0;
    };

    websocket.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        
        // Runtime validation - ensure message structure is valid
        if (!isWSMessage(parsed)) {
          console.error('Invalid WebSocket message structure:', parsed);
          return;
        }
        
        onMessage(parsed);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error, event.data);
      }
    };

    websocket.onerror = (error) => {
      console.error('WebSocket error:', error);
      setConnected(false);
    };

    websocket.onclose = () => {
      console.log('WebSocket disconnected');
      setConnected(false);
      
      // Attempt reconnection with exponential backoff
      if (reconnectAttempts.current < maxReconnectAttempts) {
        reconnectAttempts.current += 1;
        const delay = reconnectDelay * Math.pow(2, reconnectAttempts.current - 1);
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      } else {
        console.error('Max reconnection attempts reached');
      }
    };

    ws.current = websocket;
  }, [notebookId, onMessage]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      ws.current?.close();
    };
  }, [connect]);

  const sendMessage = useCallback((message: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket not connected, message not sent:', message);
    }
  }, []);

  return { sendMessage, connected };
}
