"""
simulate_trades.py
Synthetic credentialed trade simulation for ARV-806 (ms-002-1).

Runs 4x daily via GitHub Actions. Places 2-4 synthetic trades per run
with slight positive drift, updating q_yes, q_no, q_abmm_yes, q_abmm_no,
and ldi_total in Supabase. ABMM influence retreats as LDI accumulates.

Methodology:
- Expert pool: Brier scores sampled from Beta(6,2) — credentialed but imperfect
- Trade direction: belief drawn from N(current_price + drift, noise)
- Trade size: LogNormal(0, 0.3) * 0.4 — modest per-trade position
- LDI increment: trade_size * brier_score * 0.06 (Brier-weighted)
- ABMM retreat: exponential, w(t) = exp(-lambda * ldi), lambda = log(2)/0.35
"""

import os
import json
import math
import random
import requests
import numpy as np
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
MILESTONE_ID   = 'ms-002-1'          # ARV-806 M1
MOLECULE_ID    = 'mol-002'
MOLECULE_NAME  = 'ARV-806'
TRADES_PER_RUN = random.randint(2, 4) # slight randomness per run
DRIFT          = 0.015                # positive drift per trade
NOISE_SCALE    = 0.08                 # belief noise ~ N(0, noise_scale)
TRADE_SIZE_MU  = 0.0                  # LogNormal mu
TRADE_SIZE_SIG = 0.3                  # LogNormal sigma
TRADE_SIZE_SCALE = 0.4               # scale factor
LDI_WEIGHT     = 0.06                 # Brier-weighted LDI increment per unit
LDI_HALF       = 0.35                 # ABMM half-life
LDI_MAX        = 1.0

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_SERVICE_KEY']

HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
}

# ── LS-LMSR functions ─────────────────────────────────────────────────────────
def lslmsr_price(q_yes, q_no, alpha):
    b = alpha * (q_yes + q_no)
    if b == 0:
        return 0.5
    m = max(q_yes / b, q_no / b)
    exp_yes = math.exp(q_yes / b - m)
    exp_no  = math.exp(q_no  / b - m)
    return exp_yes / (exp_yes + exp_no)

def abmm_weight(ldi, ldi_half=LDI_HALF):
    lam = math.log(2) / ldi_half
    return math.exp(-lam * ldi)

# ── Supabase helpers ──────────────────────────────────────────────────────────
def fetch_milestone():
    url = f"{SUPABASE_URL}/rest/v1/Milestone?id=eq.{MILESTONE_ID}&select=*"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json()[0]

def update_milestone(data: dict):
    url = f"{SUPABASE_URL}/rest/v1/Milestone?id=eq.{MILESTONE_ID}"
    r = requests.patch(url, headers=HEADERS, json=data)
    r.raise_for_status()
    return r.json()

# ── Main simulation ───────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting simulation — {MOLECULE_NAME}")
    print(f"Trades this run: {TRADES_PER_RUN}")

    ms = fetch_milestone()
    q_yes      = float(ms['q_yes'])
    q_no       = float(ms['q_no'])
    alpha      = float(ms['alpha'])
    ldi        = float(ms['ldi_total'] or 0.0)

    print(f"Current state: q_yes={q_yes:.3f}, q_no={q_no:.3f}, "
          f"price={lslmsr_price(q_yes, q_no, alpha):.1%}, "
          f"ldi={ldi:.4f}, abmm_w={abmm_weight(ldi):.3f}")

    rng = np.random.default_rng(seed=int(datetime.now(timezone.utc).timestamp()))

    for i in range(TRADES_PER_RUN):
        current_price = lslmsr_price(q_yes, q_no, alpha)

        # Sample expert
        brier = float(rng.beta(6, 2))

        # Expert belief: slight positive drift from current price
        noise  = rng.normal(0, (1 - brier) * NOISE_SCALE)
        belief = float(np.clip(current_price + DRIFT + noise, 0.03, 0.97))

        # Trade size
        trade_size = float(rng.lognormal(TRADE_SIZE_MU, TRADE_SIZE_SIG)) * TRADE_SIZE_SCALE

        # Direction
        if belief > current_price:
            q_yes += trade_size
        else:
            q_no  += trade_size

        # LDI increment (Brier-weighted)
        ldi = min(LDI_MAX, ldi + trade_size * brier * LDI_WEIGHT)

        new_price = lslmsr_price(q_yes, q_no, alpha)
        print(f"  Trade {i+1}: belief={belief:.3f}, size={trade_size:.3f}, "
              f"direction={'YES' if belief > current_price else 'NO '}, "
              f"price {current_price:.1%} → {new_price:.1%}, "
              f"brier={brier:.2f}, ldi={ldi:.4f}")

    # Compute final ABMM retreat
    w = abmm_weight(ldi)
    q_abmm_yes_init = float(ms['q_abmm_yes'] or q_yes)
    q_abmm_no_init  = float(ms['q_abmm_no']  or q_no)

    # ABMM effective quantities retreat proportionally
    # Use original seed quantities scaled by current weight
    # Seed was ~49.172 / 50.828 for ARV-806
    SEED_Q_YES = 49.172
    SEED_Q_NO  = 50.828
    q_abmm_yes = w * SEED_Q_YES
    q_abmm_no  = w * SEED_Q_NO

    final_price = lslmsr_price(q_yes, q_no, alpha)
    abmm_influence = w * 100

    print(f"\nFinal state: price={final_price:.1%}, ldi={ldi:.4f}, "
          f"abmm_influence={abmm_influence:.1f}%")

    # Write to Supabase
    update_milestone({
        'q_yes':      round(q_yes, 6),
        'q_no':       round(q_no,  6),
        'q_abmm_yes': round(q_abmm_yes, 6),
        'q_abmm_no':  round(q_abmm_no,  6),
        'ldi_total':  round(ldi, 6),
    })

    print(f"[{datetime.now(timezone.utc).isoformat()}] Simulation complete.")

if __name__ == '__main__':
    main()
