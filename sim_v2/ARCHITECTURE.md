# v2 Architecture — Interactive Market Design Simulator

## Goal

Take the v1 sweep (which proved its findings via 2,400 ensemble runs and 16-cell paired t-tests) and turn the empirical findings into an interactive sandbox where a user can manipulate the parameters v1 identified as binding and watch convergence, PnL, and rent extraction in real time.

## Core design tension (resolved)

v1's findings are ensemble statements. A naive "watch one market" UX will routinely show runs that contradict the narrative because of sampling variance. v2 resolves this three ways simultaneously:

1. **Default view runs N=16 seeds in parallel** (small multiples) so the ensemble *is* the demo
2. **Hero view streams one seed against a pre-computed 95% CI band** so variance is shown not hidden
3. **PnL view aggregates across all running seeds** so the rent-extraction story is statistical, not anecdotal

## System shape

```
┌──────────────────────────┐         WebSocket          ┌──────────────────────────┐
│  Next.js frontend        │ ◀────── frames ──────────▶ │  FastAPI on Modal/Fly    │
│  (animation only,        │                            │                          │
│   no simulation logic)   │ ──── sim_config ─────────▶ │  Pre-computes traces     │
└──────────────────────────┘                            │  using existing sim/     │
                                                        │  module from v1          │
                                                        │                          │
                                                        │  Settles + computes      │
                                                        │  PnL and rent extraction │
                                                        │  Streams back paced      │
                                                        └──────────────────────────┘
```

The backend is the same Python that produced v1's findings. No re-implementation, no parity risk, no second source of truth. The frontend just animates frames.

## Pre-compute → stream model

Why pre-compute rather than stream-as-it-runs:

- A single sim run completes in ~133ms on the user's machine. Streaming as it runs means the WebSocket has to *throttle* a fire hose, not buffer a trickle. The pacing math is the same either way, and pre-computing is simpler.
- Pre-computing also lets us run N=16 seeds in parallel server-side (using v1's existing `ProcessPoolExecutor` pattern), then interleave their frames for the small-multiples view.
- The 95% CI band can be derived from a fast 100-seed pre-pass before the "hero" run starts. The user perceives the CI band as instant; in reality it's ~5-15s of server compute.

Total backend latency from "Run" click to first frame: target <8s. Stream duration: 5-10 min user-configurable.

## Knobs — mapped to v1 findings

Each knob maps directly to either a v1 finding or a v1-recommended next experiment, so v2 isn't a toy — it's the interactive version of experiments the user already prioritized:

| Knob | UI control | Maps to | Why it matters |
|------|-----------|---------|----------------|
| Agent class counts | 4 steppers (naive, aggregation, tail, cross) | Finding 1, 2 | The diversity-wins story |
| Capital per agent | Slider $50-$1000 | Finding 3 / Exp #1 | The binding constraint for tail markets |
| Trade-size mechanism | Toggle fixed / confidence-weighted | Exp #2 (highest priority) | Tests whether Finding 1's negative deltas reverse |
| Disagreement threshold | Slider 0.01-0.10 | Exp #3 | Sustained convergence in tail markets |
| Within-cluster correlation | Slider 0.0-0.9 | Finding 4 | The 2.55× penalty story |
| Information regime | Toggle routine / tail | Findings 2, 4 | Same as v1's regimes |
| Time compression | Slider 5-10 min | UX | Wall-clock pacing only |

Defaults reproduce v1's `naive_only` vs `all_four` comparison in `routine_high_corr` — the most demoable contrast.

## PnL and rent extraction (new in v2)

Beyond Brier, v2 computes PnL by agent class after settling all positions at the true `p*` at horizon:

For each agent:
- For each YES trade of `n` shares at marginal cost `c_yes`: realized PnL = `n × (p* − c_yes / n)`
- For each NO trade: realized PnL = `n × ((1 − p*) − c_no / n)`

Aggregated by class:
- **Mean PnL** — informational rent extracted
- **PnL std** — variance of the rent
- **PnL-per-trade** — capital efficiency
- **Total volume by class** — share of activity

The rent-extraction view is the headline: noise traders' aggregate loss = the pool that informed agents and the AMM share. This is the protocol-design framing that matters for stablecoin/RWA-adjacent conversations more than Brier does.

## Module map

```
sim_v2/
├── backend/
│   ├── main.py              FastAPI app + WebSocket endpoint
│   ├── models.py            Pydantic config + frame schemas (THE contract)
│   ├── compute.py           Wraps sim.runner_agentic.run_sim for v2 configs
│   ├── pnl.py               Settlement + PnL/rent computation (new logic)
│   ├── streaming.py         Frame batching + pacing for WebSocket
│   └── presets.py           v1-finding-mapped knob defaults
├── frontend/
│   ├── components/SimulatorPanel.tsx    Controls
│   ├── components/MarketView.tsx         Live trace + CI band
│   ├── components/PnLPanel.tsx           Rent extraction display
│   ├── components/SmallMultiples.tsx     16-seed fanout
│   ├── hooks/useSimStream.ts             WebSocket consumer
│   └── lib/protocol.ts                   Mirrored types
└── deploy/
    └── modal_app.py         Modal deployment shim
```

## Deployment

Modal is the lighter lift — `modal deploy modal_app.py` from a laptop, free tier covers the demo period, scales workers per WebSocket session. Fly is fine too but needs Docker discipline. The cost ceiling for a demo: ~$0.

## Performance budget

| Operation | Budget | Strategy |
|-----------|--------|----------|
| Pre-compute 100 seeds for CI band | <8s | ProcessPoolExecutor, 8 workers |
| Pre-compute 16 seeds for hero | <2s | Same pool |
| Frame stream | 4-10 frames/sec | Decimation + event-aligned pacing |
| Frontend frame buffer | 2-5s ahead | Backpressure if dropped |

## What this is NOT

- Not a re-implementation of v1 in TS. The TS port on `/simulation` stays as-is for H1/H2.
- Not a substitute for v1's writeup. v2 is the demo; v1 is the citation.
- Not statistically valid for new claims. v2 lets a user *see* the v1 findings; novel claims still require ensemble runs.
