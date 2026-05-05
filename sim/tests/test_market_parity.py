"""
Parity test: Python LS-LMSR must match Solidity LS-LMSR within tolerance.
ABMM retreat is OFF for parity (Python-only extension; no Solidity reference).
"""

import json
import pathlib
import pytest
from sim.market import LSLMSRMarket, LSLMSRConfig, ABMMConfig

FIXTURE_PATH = pathlib.Path(__file__).parent / "fixtures" / "parity_run.json"
TOLERANCE = 1e-9
SCALE = 10**18  # UD60x18 → float


@pytest.fixture
def fixture_data():
    if not FIXTURE_PATH.exists():
        pytest.skip(f"parity fixture not generated yet: {FIXTURE_PATH}")
    with open(FIXTURE_PATH) as f:
        return json.load(f)


def test_python_matches_solidity(fixture_data):
    cfg = LSLMSRConfig(
        alpha=int(fixture_data["config"]["alpha_wei"]) / SCALE,
        q_abmm_yes=int(fixture_data["config"]["q_abmm_yes_wei"]) / SCALE,
        q_abmm_no=int(fixture_data["config"]["q_abmm_no_wei"]) / SCALE,
    )
    market = LSLMSRMarket(config=cfg, abmm=ABMMConfig(enabled=False))

    # check initial price matches
    py_p0 = market.price_yes()
    sol_p0 = int(fixture_data["initial_price_yes_wei"]) / SCALE
    assert abs(py_p0 - sol_p0) < TOLERANCE, (
        f"initial: py={py_p0:.12f} sol={sol_p0:.12f}"
    )

    for i, trade in enumerate(fixture_data["trades"]):
        shares = int(trade["shares_wei"]) / SCALE
        market.execute_trade(is_yes=trade["is_yes"], shares=shares)

        py_price = market.price_yes()
        sol_price = int(trade["solidity_price_yes_wei"]) / SCALE
        diff = abs(py_price - sol_price)
        assert diff < TOLERANCE, (
            f"trade {i}: py={py_price:.12f} sol={sol_price:.12f} diff={diff:.2e}"
        )


def test_market_initializes_to_symmetric_price():
    cfg = LSLMSRConfig(alpha=0.05, q_abmm_yes=500.0, q_abmm_no=500.0)
    market = LSLMSRMarket(config=cfg)
    assert abs(market.price_yes() - 0.5) < 1e-12


def test_buying_yes_increases_yes_price():
    cfg = LSLMSRConfig(alpha=0.05, q_abmm_yes=500.0, q_abmm_no=500.0)
    market = LSLMSRMarket(config=cfg)
    p_before = market.price_yes()
    market.execute_trade(is_yes=True, shares=10.0)
    assert market.price_yes() > p_before


def test_asymmetric_seed_skews_price():
    """qAbmmYes < qAbmmNo means more NO already 'held' → NO priced higher, YES lower."""
    cfg = LSLMSRConfig(alpha=0.05, q_abmm_yes=300.0, q_abmm_no=700.0)
    market = LSLMSRMarket(config=cfg)
    assert market.price_yes() < 0.5
    assert market.price_no() > 0.5