"""
sim_v2.deploy.modal_app — Modal deployment for the v2 backend.

Deploy with:
    modal deploy modal_app.py

That gives you a stable HTTPS URL like:
    https://<workspace>--sim-v2-fastapi-app.modal.run

WebSocket endpoint will be at:
    wss://<workspace>--sim-v2-fastapi-app.modal.run/ws/simulate

The container needs:
  - The existing v1 sim/ module (we mount the repo)
  - sim_v2 package (this code)
  - FastAPI, pydantic v2, uvicorn, numpy, pyarrow (v1 dep)

Resource sizing:
  - One container per active WebSocket session is fine for demo traffic.
  - 8 vCPU lets the ProcessPoolExecutor saturate during pre-compute.
  - 4 GiB memory covers ~16 seeds × ~50MB per RunResult plus headroom.

Cost model:
  - Modal bills per second of container runtime.
  - One demo session: 5-15s pre-compute + 5-10min stream ≈ ~$0.03-0.06.
  - For a recruiter/partner demo period (~100 sessions), total cost <$5.
"""

from __future__ import annotations

import modal
from pathlib import Path

# Only resolves correctly at deploy time (from local repo).
# Inside the container, __file__ is /root/modal_app.py with no parents[2].
try:
    _REPO_ROOT = Path(__file__).resolve().parents[2]
except IndexError:
    _REPO_ROOT = None  # we're inside the container; mounts already happened

# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------

image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "fastapi[standard]>=0.110",
    "pydantic>=2.5",
    "uvicorn[standard]>=0.27",
    "numpy>=1.26",
    "pyarrow>=15.0",
    "websockets>=12.0",
)
# Only add local mounts at deploy time; skip when running inside the container.
if _REPO_ROOT is not None:
    image = image.add_local_dir(str(_REPO_ROOT / "sim"), "/root/sim")
    image = image.add_local_dir(
        str(_REPO_ROOT / "sim_v2" / "backend"), "/root/sim_v2/backend"
    )


app = modal.App("sim-v2", image=image)


# ---------------------------------------------------------------------------
# ASGI entrypoint
# ---------------------------------------------------------------------------


@app.function(
    image=image,
    cpu=8.0,
    memory=4096,
    timeout=900,
    min_containers=1,  # one always warm container during demo window
    # keep_warm=1, # enable during active demos to avoid cold start
)
@modal.asgi_app()
def fastapi_app():
    """Return the FastAPI ASGI app. Modal handles WebSocket upgrade."""
    import sys

    sys.path.insert(0, "/root")
    from sim_v2.backend.main import app as fastapi_instance

    return fastapi_instance


# ---------------------------------------------------------------------------
# Pre-warm hook (optional)
# ---------------------------------------------------------------------------


@app.function(image=image, schedule=modal.Cron("0 14 * * *"))  # daily, 9am ET
def daily_smoke_test():
    """Run a single sim end-to-end to catch deployment regressions."""
    import sys

    sys.path.insert(0, "/root")
    from sim_v2.backend.compute import run_single_seed
    from sim_v2.backend.pnl import settle_and_summarize
    from sim_v2.backend.presets import PRESETS

    req = PRESETS["v1_all_four_diversity"]
    # Speed up: shrink for the smoke test
    req = req.model_copy(update={"horizon_ticks": 2_000})
    req.stream.n_ensemble_seeds = 4
    req.stream.ci_band_seeds = 8

    result = run_single_seed(req)
    class_pnls, rent, tail_ids, gaps = settle_and_summarize(result)

    assert result.tick_max == 2_000
    assert len(class_pnls) >= 2
    print(f"smoke ok: rent_efficiency={rent.rent_efficiency:.3f}")
