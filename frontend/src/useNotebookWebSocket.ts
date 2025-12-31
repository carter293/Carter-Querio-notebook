import useWebSocket, { ReadyState } from 'react-use-websocket';
import { useCallback, useRef, useEffect, useState } from 'react';
import type { CellResponse, OutputResponse, CellStatus } from './client/types.gen';
import { WS_BASE_URL } from './api-client';

// Re-export WebSocket message types (keep existing discriminated union)
// These match the backend WebSocket broadcaster in backend/websocket.py
export type WSMessage =
  | { type: 'cell_updated'; cellId: string; cell: { code: string; reads: string[]; writes: string[]; status: string } }
  | { type: 'cell_created'; cellId: string; cell: CellResponse; index?: number }
  | { type: 'cell_deleted'; cellId: string }
  | { type: 'cell_status'; cellId: string; status: CellStatus }
  | { type: 'cell_stdout'; cellId: string; data: string }
  | { type: 'cell_error'; cellId: string; error: string }
  | { type: 'cell_output'; cellId: string; output: OutputResponse };

// Keep existing type guards for compatibility
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

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected' | 'reconnecting';

interface UseNotebookWebSocketOptions {
  onMessage: (msg: WSMessage) => void;
}

export function useNotebookWebSocket(
  notebookId: string | null,
  token: string | null,
  options: UseNotebookWebSocketOptions
) {
  const didUnmount = useRef(false);
  const isAuthenticated = useRef(false);
  const tokenRef = useRef(token);
  const messageQueue = useRef<object[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected');
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  
  // Keep token ref updated for use in callbacks
  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  // Only connect when we have both notebookId and token
  const socketUrl = notebookId && token
    ? `${WS_BASE_URL}/api/ws/notebooks/${notebookId}`
    : null;

  const {
    sendJsonMessage,
    readyState,
  } = useWebSocket(socketUrl, {
    // Send auth message immediately on open
    onOpen: () => {
      console.log('WebSocket connected, sending authentication...');
      isAuthenticated.current = false;
      setConnectionStatus('connecting');
      setReconnectAttempt(0);
      sendJsonMessage({ type: 'authenticate', token: tokenRef.current });
    },

    // Handle all messages including auth response
    onMessage: (event) => {
      try {
        const data = JSON.parse(event.data);

        // Handle auth response
        if (data.type === 'authenticated') {
          console.log('WebSocket authenticated successfully');
          isAuthenticated.current = true;
          setConnectionStatus('connected');
          
          // Flush message queue
          if (messageQueue.current.length > 0) {
            console.log(`Flushing ${messageQueue.current.length} queued messages...`);
            const queue = [...messageQueue.current];
            messageQueue.current = [];
            queue.forEach(msg => sendJsonMessage(msg));
          }
          return;
        }

        // Handle errors
        if (data.type === 'error') {
          console.error('WebSocket error:', data.message);
          return;
        }

        // Validate and forward to consumer
        if (isWSMessage(data)) {
          options.onMessage(data);
        } else {
          console.error('Invalid WebSocket message structure:', data);
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    },

    onClose: (event) => {
      console.log('WebSocket disconnected', event.code, event.reason);
      isAuthenticated.current = false;
      
      // Update status based on whether we'll reconnect
      if (event.code === 1008 || event.code === 1000 || didUnmount.current) {
        setConnectionStatus('disconnected');
      } else {
        setConnectionStatus('reconnecting');
        setReconnectAttempt(prev => prev + 1);
      }
    },

    onError: (event) => {
      console.error('WebSocket error:', event);
    },

    // Reconnection with exponential backoff
    shouldReconnect: (closeEvent) => {
      // Don't reconnect on auth failure (1008) or clean close (1000)
      if (closeEvent.code === 1008 || closeEvent.code === 1000) {
        console.log(`WebSocket closed with code ${closeEvent.code}, not reconnecting`);
        return false;
      }
      // Don't reconnect if component unmounted
      if (didUnmount.current) {
        return false;
      }
      return true;
    },
    reconnectInterval: (attemptNumber) =>
      Math.min(Math.pow(2, attemptNumber) * 1000, 10000),
    reconnectAttempts: 5,
    retryOnError: true,

    // Don't share connection between hook instances
    share: false,
  }, !!socketUrl); // Enable only when URL is valid

  // Track unmount for reconnection logic
  useEffect(() => {
    didUnmount.current = false;
    return () => {
      didUnmount.current = true;
    };
  }, []);

  // Send run_cell command
  const runCell = useCallback((cellId: string) => {
    if (readyState === ReadyState.OPEN && isAuthenticated.current) {
      sendJsonMessage({ type: 'run_cell', cellId });
    } else {
      console.warn('WebSocket not ready, queueing cell execution for:', cellId);
      messageQueue.current.push({ type: 'run_cell', cellId });
    }
  }, [readyState, sendJsonMessage]);

  // Generic send for any message (maintains old interface)
  const sendMessage = useCallback((message: object) => {
    if (readyState === ReadyState.OPEN && isAuthenticated.current) {
      sendJsonMessage(message);
    } else {
      console.warn('WebSocket not connected, queueing message:', message);
      messageQueue.current.push(message);
    }
  }, [readyState, sendJsonMessage]);

  return {
    sendMessage,
    runCell,
    connected: readyState === ReadyState.OPEN && isAuthenticated.current,
    readyState,
    connectionStatus,
    reconnectAttempt,
    queuedMessages: messageQueue.current.length,
  };
}

