/**
 * useSimStream — React hook to consume the v2 WebSocket stream.
 *
 * Lifecycle:
 *   1. Caller passes a SimRequest. Hook opens WebSocket, sends request.
 *   2. First message: CIBandFrame → stored, exposed via `ciBand`.
 *   3. Stream of FrameMessage per seed → bucketed by seed_id in `framesBySeed`.
 *   4. FinalFrame per seed → bucketed in `finalsBySeed`.
 *   5. Optional error frame → exposed via `error`.
 *   6. Socket close → status = "done".
 *
 * The hook does NOT render anything. Components consume frames via a ref
 * + requestAnimationFrame for animation, or via state for slow-changing
 * UI like the PnL table.
 *
 * Memory: we keep all frames for the duration of the session — for 16
 * seeds × ~3360 frames × ~2KB/frame that's ~100 MB worst case, which is
 * fine for a single browser tab. For longer sessions or higher fps,
 * downsample to e.g. every-Nth frame for the chart layer.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  SimRequest,
  OutgoingMessage,
  FrameMessage,
  CIBandFrame,
  FinalFrame,
  ErrorFrame,
} from "../lib/protocol";

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
}

export function useSimStream(wsUrl: string): SimStreamHandle {
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [ciBand, setCiBand] = useState<CIBandFrame | null>(null);
  const [framesBySeed, setFramesBySeed] = useState<
    Record<number, FrameMessage[]>
  >({});
  const [latestFrameBySeed, setLatestFrameBySeed] = useState<
    Record<number, FrameMessage | null>
  >({});
  const [finalsBySeed, setFinalsBySeed] = useState<Record<number, FinalFrame>>(
    {},
  );
  const [error, setError] = useState<ErrorFrame | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  // Rolling buffer so we don't trigger React render per frame.
  // Components that want frame-rate animation read directly from this ref.
  const bufferRef = useRef<Record<number, FrameMessage[]>>({});

  const flushIntervalRef = useRef<number | null>(null);

  const start = useCallback(
    (req: SimRequest) => {
      if (wsRef.current) wsRef.current.close();
      setStatus("connecting");
      setCiBand(null);
      setFramesBySeed({});
      setLatestFrameBySeed({});
      setFinalsBySeed({});
      setError(null);
      bufferRef.current = {};

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("pre_compute");
        ws.send(JSON.stringify(req));
      };

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data) as OutgoingMessage;

        if (msg.type === "ci_band") {
          setCiBand(msg);
          setStatus("streaming");
        } else if (msg.type === "frame") {
          // Buffer; flush in batches to avoid render storm
          if (!bufferRef.current[msg.seed_id]) {
            bufferRef.current[msg.seed_id] = [];
          }
          bufferRef.current[msg.seed_id].push(msg);
          // Latest frame is exposed as state for chart-tip / PnL panels
          setLatestFrameBySeed((prev) => ({ ...prev, [msg.seed_id]: msg }));
        } else if (msg.type === "final") {
          setFinalsBySeed((prev) => ({ ...prev, [msg.seed_id]: msg }));
        } else if (msg.type === "error") {
          setError(msg);
          setStatus("error");
        }
      };

      ws.onerror = () => {
        setStatus("error");
        setError({
          type: "error",
          code: "ws_error",
          message: "WebSocket error",
          recoverable: false,
        });
      };

      ws.onclose = () => {
        setStatus((s) => (s === "error" ? s : "done"));
      };

      // Flush buffered frames into state every 250ms
      // (chart components reading via ref get all frames; React state
      // updates are throttled for components that need rerenders)
      flushIntervalRef.current = window.setInterval(() => {
        setFramesBySeed((prev) => {
          const next = { ...prev };
          let changed = false;
          for (const seedId of Object.keys(bufferRef.current)) {
            const buf = bufferRef.current[Number(seedId)];
            if (buf && buf.length > 0) {
              const sid = Number(seedId);
              next[sid] = [...(next[sid] ?? []), ...buf];
              bufferRef.current[sid] = [];
              changed = true;
            }
          }
          return changed ? next : prev;
        });
      }, 250);
    },
    [wsUrl],
  );

  const stop = useCallback(() => {
    if (flushIntervalRef.current) {
      window.clearInterval(flushIntervalRef.current);
      flushIntervalRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus("idle");
  }, []);

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
  };
}
