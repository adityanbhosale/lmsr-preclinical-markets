"""
sim_v2.backend.main — FastAPI app with WebSocket endpoint.

Lifecycle of a single demo session:
  1. Client opens WebSocket to /ws/simulate
  2. Client sends one SimRequest JSON
  3. Server runs ci-band ensemble (~100 seeds) → sends CIBandFrame
  4. Server runs hero ensemble (req.stream.n_ensemble_seeds) — typically 16 seeds
  5. For each seed in hero ensemble: stream FrameMessages paced at target_fps
  6. After each seed's stream completes: send its FinalFrame
  7. Optionally close, or keep open for a re-run with a new config

For the small-multiples UI, seeds stream concurrently with seed_id tagging.
For the hero view, only seed_id=0 is rendered (with CI band overlaid).

Deployment shape:
  - One process per WebSocket session — the pre-compute happens in worker
    processes via ProcessPoolExecutor, but the streaming itself is async
    and cheap.
  - Modal: deploy as @modal.asgi_app, autoscales per session.
  - Fly: same code, run with `uvicorn main:app --host 0.0.0.0`.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .models import SimRequest, ErrorFrame
from .compute import run_ensemble
from .streaming import build_frame_plan, build_ci_band_message, stream_seed
from .presets import PRESETS


log = logging.getLogger("sim_v2")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("sim_v2 backend starting")
    yield
    log.info("sim_v2 backend shutting down")


app = FastAPI(title="Dual-Layer Biotech Liquidity v2", lifespan=lifespan)

# In production, lock this down to the Vercel deployment origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Static endpoints — presets, health
# ---------------------------------------------------------------------------


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/presets")
async def presets():
    """Returns named SimRequest presets — the v1-finding-mapped defaults."""
    return {name: cfg.model_dump() for name, cfg in PRESETS.items()}


# ---------------------------------------------------------------------------
# WebSocket — the live stream
# ---------------------------------------------------------------------------


async def _send(ws: WebSocket, frame) -> None:
    """One place to serialize and send any frame type."""
    await ws.send_json(frame.model_dump())


@app.websocket("/ws/simulate")
async def simulate(ws: WebSocket):
    await ws.accept()
    try:
        raw = await ws.receive_json()
        req = SimRequest.model_validate(raw)
    except Exception as e:
        await _send(
            ws,
            ErrorFrame(
                code="bad_request",
                message=f"Could not parse SimRequest: {e}",
                recoverable=False,
            ),
        )
        await ws.close()
        return

    log.info(
        "starting sim: seed=%s n_seeds=%s duration=%ss",
        req.base_seed,
        req.stream.n_ensemble_seeds,
        req.stream.duration_seconds,
    )

    try:
        # Stage 1: CI band ensemble. Heavy but bounded — typically 5-15s.
        # Run in a thread to avoid blocking the event loop, since the work
        # is in worker processes anyway.
        loop = asyncio.get_running_loop()
        ci_results = await loop.run_in_executor(
            None, run_ensemble, req, req.stream.ci_band_seeds, 8
        )
        ci_msg = build_ci_band_message(ci_results)
        await _send(ws, ci_msg)
    except Exception as e:
        log.exception("ci band stage failed")
        await _send(
            ws,
            ErrorFrame(code="ci_failed", message=str(e), recoverable=False),
        )
        await ws.close()
        return

    try:
        # Stage 2: hero/small-multiples ensemble.
        hero_results = await loop.run_in_executor(
            None, run_ensemble, req, req.stream.n_ensemble_seeds, 8
        )
    except Exception as e:
        log.exception("hero ensemble failed")
        await _send(
            ws,
            ErrorFrame(code="hero_failed", message=str(e), recoverable=False),
        )
        await ws.close()
        return

    # Stage 3: concurrent paced streaming of all seeds.
    plan = build_frame_plan(req)

    async def stream_one(seed_result, seed_id: int):
        async for frame in stream_seed(seed_result, plan, seed_id=seed_id):
            await _send(ws, frame)

    try:
        await asyncio.gather(
            *(stream_one(r, i) for i, r in enumerate(hero_results))
        )
    except WebSocketDisconnect:
        log.info("client disconnected mid-stream")
        return
    except Exception as e:
        log.exception("streaming failed")
        try:
            await _send(
                ws,
                ErrorFrame(
                    code="stream_failed",
                    message=str(e),
                    recoverable=True,
                ),
            )
        except Exception:
            pass
        return

    log.info("sim complete")
    try:
        await ws.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Local dev entrypoint
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("sim_v2.backend.main:app", host="0.0.0.0", port=8000, reload=True)
