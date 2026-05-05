# Agentic Simulation — Layer 2 LS-LMSR Markets

Multi-agent simulation of the Layer 2 LS-LMSR markets, built to test two
hypotheses about the dual-layer mechanism design.

## Hypotheses under test

**H1 — ABMM retreat robustness:** The ABMM retreat function is robust to
coordinated liquidity-withdrawal attacks below a characterizable threshold.

**H2 — Convergence to true probability:** Under mixed agent populations,
LS-LMSR price converges to true probability within a bounded number of trades,
regardless of starting prior.

## Architecture

- `market.py` — pure-Python LS-LMSR + ABMM retreat. Validated for price
  parity against the Solidity reference implementation in `/contracts/Layer2/`.
- `agents/` — three agent classes: credentialed-conviction (informed),
  noise (random), momentum (trend-following). H1 adds an adversarial class.
- `runner.py` — simulation loop. Takes a config, populates a market,
  runs N trades, logs all state to Parquet.
- `analysis/` — convergence metrics and plot generators.
- `configs/` — YAML sweep specifications for H1 and H2.

## Why pure Python (not testnet contracts)

A 1,500-run sweep against testnet would take days; in pure Python it runs
in ~2 hours. Parity test in `tests/test_market_parity.py` ensures the
Python port reproduces Solidity prices within 1e-9.

## Running

    cd sim
    source venv/bin/activate
    pytest tests/                    # parity + unit tests
    python runner.py configs/h1_*.yaml   # single sweep