/**
 * useSimStream — React hook to consume the v2 WebSocket stream.
 *
 * Lifecycle:
 *   1. Caller passes a SimRequest via start(req).
 *   2. Hook opens WebSocket, sends request as one JSON message.
 *   3. Server returns CIBandFrame first → exposed via `ciBand`.
 *   4. Server streams FrameMessage per seed → bucketed in `framesBySeed`.
 *   5. FinalFrame per seed → bucketed in `finalsBySeed`.
 *   6. Optional error frame → exposed via `error`, status set to "error".
 *   7. Socket close → status "done".
 *
 * Performance design:
 *   - Frames arrive at target_fps × n_seeds (e.g. 8 × 16 = 128/sec).
 *   - We buffer frames in a ref to avoid React state updates on every
 *     frame. The buffer flushes to state every 250ms in batches.
 *   - `latestFrameBySeed` updates immediately on each frame for components
 *     that need real-time values (tickers, current-price displays).
 *   - `framesBySeed` accumulates the full history for charts that need
 *     to draw the trace.
 *
 * Memory: 16 seeds × 8fps × 7min ≈ 53k frames per session at ~1KB each
 * ≈ 50MB. Fine for a browser tab. For longer sessions or higher density,
 * downsample at the chart layer (every Nth frame).
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  SimRequest,
  OutgoingMessage,
  FrameMessage,
  CIBandFrame,
  FinalFrame,
  ErrorFrame,
} from "@/lib/sim_v2/protocol";

export type StreamStatus =
  | "idle"
  | "connecting"
  | "pre_compute"
  | "streaming"
  | "done"
  | "error";

export interface SimStreamHandle {
  status: StreamStatus;
  ciBand: CIBandFrame | null;
  framesBySeed: Record<number, FrameMessage[]>;
  latestFrameBySeed: Record<number, FrameMessage | null>;
  finalsBySeed: Record<number, FinalFrame>;
  error: ErrorFrame | null;
  start: (req: SimRequest) => void;
  stop: () => void;
  /** Convenience: number of frames received so far across all seeds. */
  totalFrames: number;
}

export function useSimStream(wsUrl: string): SimStreamHandle {
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [ciBand, setCiBand] = useState<CIBandFrame | null>(null);
  const [framesBySeed, setFramesBySeed] = useState<Record<number, FrameMessage[]>>({});
  const [latestFrameBySeed, setLatestFrameBySeed] = useState<Record<number, FrameMessage | null>>({});
  const [finalsBySeed, setFinalsBySeed] = useState<Record<number, FinalFrame>>({});
  const [error, setError] = useState<ErrorFrame | null>(null);
  const [totalFrames, setTotalFrames] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const bufferRef = useRef<Record<number, FrameMessage[]>>({});
  const flushIntervalRef = useRef<number | null>(null);

  const stop = useCallback(() => {
    if (flushIntervalRef.current !== null) {
      window.clearInterval(flushIntervalRef.current);
      flushIntervalRef.current = null;
    }
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {
        // ignore
      }
      wsRef.current = null;
    }
    setStatus("idle");
  }, []);

  const start = useCallback(
    (req: SimRequest) => {
      // Reset all state
      if (wsRef.current) {
        try { wsRef.current.close(); } catch { /* ignore */ }
      }
      setStatus("connecting");
      setCiBand(null);
      setFramesBySeed({});
      setLatestFrameBySeed({});
      setFinalsBySeed({});
      setError(null);
      setTotalFrames(0);
      bufferRef.current = {};
      const n_seen_seeds = new Set<number>();
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("pre_compute");
        ws.send(JSON.stringify(req));
      };

      ws.onmessage = (event) => {
        let msg: OutgoingMessage;
        try {
          msg = JSON.parse(event.data) as OutgoingMessage;
        } catch (parseErr) {
          setStatus("error");
          setError({
            type: "error",
            code: "parse_error",
            message: `Failed to parse server message: ${parseErr}`,
            recoverable: false,
          });
          return;
        }

        switch (msg.type) {
          case "ci_band":
            setCiBand(msg);
            setStatus("streaming");
            break;

            case "frame": {
              const frame = msg;
              const sid = frame.seed_id;
              if (frame.tick % 100 === 0) {
              }
              if (!bufferRef.current[sid]) {
                bufferRef.current[sid] = [];
              }
              bufferRef.current[sid].push(frame);
              setLatestFrameBySeed((prev) => ({ ...prev, [sid]: frame }));
              setTotalFrames((n) => n + 1);
              break;
            }

          case "final":
            setFinalsBySeed((prev) => ({ ...prev, [msg.seed_id]: msg }));
            break;

          case "error":
            setError(msg);
            setStatus("error");
            break;
        }
      };

      ws.onerror = () => {
        setStatus("error");
        setError({
          type: "error",
          code: "ws_error",
          message: "WebSocket connection error",
          recoverable: false,
        });
      };

      ws.onclose = () => {
        const buf = bufferRef.current;
        const pending: Record<number, FrameMessage[]> = {};
        for (const sidStr of Object.keys(buf)) {
          const sid = Number(sidStr);
          if (buf[sid] && buf[sid].length > 0) {
            pending[sid] = buf[sid];
            buf[sid] = [];
          }
        }
        if (Object.keys(pending).length > 0) {
          setFramesBySeed((prev) => {
            const next = { ...prev };
            for (const sidStr of Object.keys(pending)) {
              const sid = Number(sidStr);
              next[sid] = [...(next[sid] ?? []), ...pending[sid]];
            }
            return next;
          });
        }
        setStatus((s) => (s === "error" ? s : "done"));
      };

      // Periodic flush of buffered frames into state
      flushIntervalRef.current = window.setInterval(() => {
        const buf = bufferRef.current;
        let hasNew = false;
        let totalBuffered = 0;
        for (const sidStr of Object.keys(buf)) {
          if (buf[Number(sidStr)] && buf[Number(sidStr)].length > 0) {
            hasNew = true;
            totalBuffered += buf[Number(sidStr)].length;
          }
        }
        if (!hasNew) return;
      
        // SNAPSHOT and CLEAR the buffer outside the React updater.
        // This guarantees the side effect runs exactly once even if
        // React 18 Strict Mode double-invokes the updater.
        const pending: Record<number, FrameMessage[]> = {};
        for (const sidStr of Object.keys(buf)) {
          const sid = Number(sidStr);
          if (buf[sid] && buf[sid].length > 0) {
            pending[sid] = buf[sid];
            buf[sid] = [];
          }
        }
      
        setFramesBySeed((prev) => {
          const next = { ...prev };
          for (const sidStr of Object.keys(pending)) {
            const sid = Number(sidStr);
            next[sid] = [...(next[sid] ?? []), ...pending[sid]];
          }
          return next;
        });
      }, 250);
    },
    [wsUrl],
  );

  useEffect(() => {
    return () => stop();
  }, [stop]);

  return {
    status,
    ciBand,
    framesBySeed,
    latestFrameBySeed,
    finalsBySeed,
    error,
    start,
    stop,
    totalFrames,
  };
}
