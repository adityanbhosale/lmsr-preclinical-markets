/**
 * ConnectionStatus — small top-bar indicator for the v2 simulator.
 *
 * Reads the StreamStatus from useSimStream and renders a compact pill
 * with appropriate color and label. Optionally shows progress info
 * during streaming (total frames received, time elapsed).
 */

"use client";

import type { StreamStatus } from "@/hooks/useSimStream";

interface ConnectionStatusProps {
  status: StreamStatus;
  totalFrames: number;
  errorMessage?: string;
}

const STATUS_LABEL: Record<StreamStatus, string> = {
  idle: "Idle",
  connecting: "Connecting",
  pre_compute: "Pre-computing ensemble",
  streaming: "Streaming",
  done: "Complete",
  error: "Error",
};

const STATUS_COLORS: Record<StreamStatus, { bg: string; dot: string; text: string }> = {
  idle: { bg: "bg-neutral-100 dark:bg-neutral-800", dot: "bg-neutral-400", text: "text-neutral-700 dark:text-neutral-300" },
  connecting: { bg: "bg-blue-50 dark:bg-blue-950/40", dot: "bg-blue-500 animate-pulse", text: "text-blue-700 dark:text-blue-300" },
  pre_compute: { bg: "bg-amber-50 dark:bg-amber-950/40", dot: "bg-amber-500 animate-pulse", text: "text-amber-700 dark:text-amber-300" },
  streaming: { bg: "bg-emerald-50 dark:bg-emerald-950/40", dot: "bg-emerald-500 animate-pulse", text: "text-emerald-700 dark:text-emerald-300" },
  done: { bg: "bg-neutral-100 dark:bg-neutral-800", dot: "bg-neutral-500", text: "text-neutral-700 dark:text-neutral-300" },
  error: { bg: "bg-red-50 dark:bg-red-950/40", dot: "bg-red-500", text: "text-red-700 dark:text-red-300" },
};

export function ConnectionStatus({ status, totalFrames, errorMessage }: ConnectionStatusProps) {
  const colors = STATUS_COLORS[status];

  return (
    <div className="flex items-center gap-3">
      <div
        className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ${colors.bg} ${colors.text}`}
      >
        <span className={`h-2 w-2 rounded-full ${colors.dot}`} />
        {STATUS_LABEL[status]}
      </div>
      {(status === "streaming" || status === "done") && totalFrames > 0 && (
        <span className="text-xs tabular-nums text-neutral-500 dark:text-neutral-400">
          {totalFrames.toLocaleString()} frames
        </span>
      )}
      {status === "error" && errorMessage && (
        <span className="text-xs text-red-600 dark:text-red-400" title={errorMessage}>
          {errorMessage.slice(0, 80)}
          {errorMessage.length > 80 && "…"}
        </span>
      )}
    </div>
  );
}
