import useWebSocket, { ReadyState } from "react-use-websocket";
import { useCallback, useRef, useEffect, useState } from "react";
import type {
  CellResponse,
  OutputResponse,
} from "./client/types.gen";
import { WS_BASE_URL, CellStatus } from "./api-client";

// Re-export WebSocket message types (keep existing discriminated union)
// These match the backend WebSocket broadcaster in backend/websocket.py
export type WSMessage =
  | {
      type: "cell_updated";
      cellId: string;
      cell: { code: string; reads: string[]; writes: string[]; status: string };
    }
  | { type: "cell_created"; cellId: string; cell: CellResponse; index?: number }
  | { type: "cell_deleted"; cellId: string }
  | { type: "cell_status"; cellId: string; status: CellStatus }
  | { type: "cell_stdout"; cellId: string; data: string }
  | { type: "cell_error"; cellId: string; error: string }
  | { type: "cell_output"; cellId: string; output: OutputResponse }
  | {
      type: "db_connection_updated";
      connectionString: string;
      status: "success" | "error";
      error?: string
    }
  | {
      type: "kernel_error";
      error: string;
    };

// Keep existing type guards for compatibility
export function isWSMessage(msg: unknown): msg is WSMessage {
  if (typeof msg !== "object" || msg === null || !("type" in msg)) {
    return false;
  }

  const msgType = (msg as { type: unknown }).type;
  if (typeof msgType !== "string") {
    return false;
  }

  // db_connection_updated and kernel_error don't have cellId
  if (msgType === "db_connection_updated" || msgType === "kernel_error") {
    return true;
  }

  // All other messages require cellId
  return "cellId" in msg && typeof (msg as { cellId: unknown }).cellId === "string";
}

export type ConnectionStatus =
  | "connected"
  | "connecting"
  | "disconnected"
  | "reconnecting";

interface UseNotebookWebSocketOptions {
  notebookId: string | null;
  onMessage: (msg: WSMessage) => void;
}

export function useNotebookWebSocket(
  options: UseNotebookWebSocketOptions
) {
  const didUnmount = useRef(false);
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("disconnected");
  const [reconnectAttempt, setReconnectAttempt] = useState(0);

  // Only connect when we have notebookId
  const socketUrl = options.notebookId
    ? `${WS_BASE_URL}/api/v1/ws/notebook/${options.notebookId}`
    : null;

  const { sendJsonMessage, readyState } = useWebSocket(
    socketUrl,
    {
      onOpen: () => {
        console.log("WebSocket connected");
        setConnectionStatus("connected");
        setReconnectAttempt(0);
      },

      onMessage: (event) => {
        try {
          const data = JSON.parse(event.data);

          // Handle errors
          if (data.type === "error") {
            console.error("WebSocket error:", data.message);
            return;
          }

          // Validate and forward to consumer
          if (isWSMessage(data)) {
            options.onMessage(data);
          } else {
            console.error("Invalid WebSocket message structure:", data);
          }
        } catch (e) {
          console.error("Failed to parse WebSocket message:", e);
        }
      },

      onClose: (event) => {
        console.log("WebSocket disconnected", event.code, event.reason);

        // Update status based on whether we'll reconnect
        if (event.code === 1000 || didUnmount.current) {
          setConnectionStatus("disconnected");
        } else {
          setConnectionStatus("reconnecting");
          setReconnectAttempt((prev) => prev + 1);
        }
      },

      onError: (event) => {
        console.error("WebSocket error:", event);
      },

      // Reconnection with exponential backoff
      shouldReconnect: (closeEvent) => {
        // Don't reconnect on clean close (1000)
        if (closeEvent.code === 1000) {
          console.log(
            `WebSocket closed with code ${closeEvent.code}, not reconnecting`
          );
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
    },
    !!socketUrl
  ); // Enable only when URL is valid

  // Track unmount for reconnection logic
  useEffect(() => {
    didUnmount.current = false;
    return () => {
      didUnmount.current = true;
    };
  }, []);

  // Send run_cell command
  const runCell = useCallback(
    (cellId: string) => {
      if (readyState === ReadyState.OPEN) {
        sendJsonMessage({ type: "run_cell", cellId });
      } else {
        console.warn("WebSocket not ready, cannot run cell:", cellId);
      }
    },
    [readyState, sendJsonMessage]
  );

  // Generic send for any message (maintains old interface)
  const sendMessage = useCallback(
    (message: object) => {
      if (readyState === ReadyState.OPEN) {
        sendJsonMessage(message);
      } else {
        console.warn("WebSocket not connected, cannot send message:", message);
      }
    },
    [readyState, sendJsonMessage]
  );

  return {
    sendMessage,
    runCell,
    connected: readyState === ReadyState.OPEN,
    readyState,
    connectionStatus,
    reconnectAttempt,
  };
}
