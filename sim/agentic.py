"""
Continuous-time agent population for the agentic sim.

Defines:
  - NaiveCredentialedAgent: baseline credentialed trader. Observes signals on
    its assigned markets with delay δ (modeling slower human reaction).
    Maintains a sequential Bayesian posterior over each market's logit(p*)
    with a strong modal prior centered at logit 0 (= probability 0.5).
    Mixed reactive + low-frequency review decision policy.

  - NoiseTrader: Poisson-arrival random trades. Picks a random market from
    its assigned set, random side, jittered size. No beliefs, no observation.
    Background flow.

  - AgentPopulation: orchestrator that registers four event handlers
    (signal, agent_decision, agent_review, noise_trade) with the simulator
    and dispatches events to the right agent by agent_id.

This is the Task 4 baseline. Subsequent tasks add:
  - Task 5: AggregationDepthAgent (instant observation, wider signal sample)
  - Task 6: TailEventReasoningAgent (base-rate priors)
  - Task 7: CrossMarketConsistencyAgent (joint posterior over latent factors)

All four agent classes will share this same AgentPopulation infrastructure.

Capital model
-------------
Each agent maintains two counters:
  - `deployed`     : sum of ACTUAL costs from executed trades (pulled from
                     the market env's trade_log via incremental sync).
  - `pending_cost` : sum of ESTIMATED costs for trades scheduled in the
                     current tick that haven't executed yet.

`available = budget - deployed - pending_cost` is what the agent checks
before each trade. After scheduling a trade, `pending_cost += cost_est`.
At the start of every decision/review/noise event, AgentPopulation._sync_costs
scans new entries in the trade_log: for each affected agent, it moves the
actual cost into `deployed` and resets `pending_cost` to 0 (correct as long
as all trades use delay=0, which is the case throughout Tasks 4-7).

Why pending_cost is necessary: trade events fire with priority TRADE (200);
decision/review events fire with priority DECISION (100). Within the same
tick, all DECISIONs run before any TRADE. So if an agent's posterior
triggers trades from multiple events at the same tick — e.g. a review and a
reactive decision colliding — _sync_costs at the start of the second event
still sees no new trades in the log, and without pending_cost the agent
would commit to both trades on stale `deployed`, exceeding budget.

This is the "minimal capital model" per the handoff. Documented limitation:
agents are otherwise capital-unconstrained beyond per-agent budget — no
portfolio theory, no risk-of-ruin sizing.

Modal bias
----------
NaiveCredentialedAgent's prior is logit ~ N(0, 1/τ_0) with τ_0 = 5 by
default. With per-signal assumed precision τ_s = 1, posterior precision
after N signals is τ_0 + N*τ_s = 5 + N. Posterior mean is the
precision-weighted average of prior (0) and signals. Implication: even
after 50 signals, the prior still contributes 5/55 ≈ 9% weight, pulling
posterior toward 0 (prob 0.5). This produces the "anchors near modal
prior" behavior we want to test against tail-aware agents in Task 6.
The agent treats all signals with `signal_precision_assumed` regardless
of the signal's actual noise_std — it doesn't know to weight tail
signals more heavily.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Union

import numpy as np

from sim.events import Event, EventPriority
from sim.information import InformationEnvironment, Signal
from sim.market_env import MarketEnvironment, TradeRequest
from sim.simulator import Simulator


# -----------------------------------------------------------------------------
# Numerical helper
# -----------------------------------------------------------------------------

def _compute_trade_size(
    base_size: float,
    confidence_weighted: bool,
    posterior_precision: float,
    prior_precision: float,
    floor: float,
    ceiling: float,
) -> float:
    """Single source of truth for confidence-weighted sizing.
    confidence_weighted=False returns base_size unchanged (v1 behavior)."""
    if not confidence_weighted:
        return base_size
    relative = posterior_precision / max(prior_precision, 1e-9)
    multiplier = float(np.clip(math.sqrt(max(relative, 0.0)), floor, ceiling))
    return base_size * multiplier


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        ex = math.exp(-x)
        return 1.0 / (1.0 + ex)
    ex = math.exp(x)
    return ex / (1.0 + ex)


def _consider_trade_helper(
    agent_id: int,
    market_id: int,
    posterior_mean: float,
    market_env: MarketEnvironment,
    disagreement_threshold: float,
    trade_size: float,
    safety_margin: float,
    available: float,
    min_shares: float = 0.1,
) -> tuple[Optional[TradeRequest], float]:
    """
    Shared trade-decision logic used by all posterior-based agent classes.

    Returns (TradeRequest, cost_committed) on a yes-trade, or (None, 0.0) if:
      - posterior agrees with market price (within disagreement_threshold)
      - capital exhausted to below `min_shares` worth

    Capital handling: if the full trade_size fits within `available`, schedule
    it. Otherwise, binary-search the largest fractional size that fits. Uses
    market.cost_of_trade() (LS-LMSR exact) — not shares × price, which
    underestimates by ~2x at p ≈ 0.5.
    """
    p_post = _sigmoid(posterior_mean)
    p_market = market_env.price_yes(market_id)
    diff = p_post - p_market
    if abs(diff) < disagreement_threshold:
        return None, 0.0
    is_yes = bool(diff > 0)
    shares = trade_size
    market = market_env.markets[market_id]
    cost_est = market.cost_of_trade(is_yes, shares) * safety_margin
    if cost_est > available:
        lo, hi = 0.0, shares
        for _ in range(20):
            mid = 0.5 * (lo + hi)
            if mid < 1e-9:
                break
            c = market.cost_of_trade(is_yes, mid) * safety_margin
            if c <= available:
                lo = mid
            else:
                hi = mid
        shares = lo
        if shares < min_shares:
            return None, 0.0
        cost_est = market.cost_of_trade(is_yes, shares) * safety_margin
    return (
        TradeRequest(
            market_id=market_id,
            agent_id=agent_id,
            is_yes=is_yes,
            shares=shares,
        ),
        cost_est,
    )


# -----------------------------------------------------------------------------
# Naive credentialed agent
# -----------------------------------------------------------------------------

@dataclass
class NaiveCredentialedAgent:
    """
    Baseline credentialed agent.

    Parameters
    ----------
    agent_id, budget : identification + capital
    market_ids       : tuple of markets this agent observes
    observation_delay: δ in ticks; reactive trade fires at signal_t + δ
    review_interval  : ticks between periodic reviews (0 = no review)
    prior_precision  : τ_0; higher = stronger modal anchor
    signal_precision_assumed : agent's assumed 1/σ² for signals (modal bias
                       means this is *fixed*, not noise_std-aware)
    disagreement_threshold : min |p_posterior - p_market| to trade
    trade_size       : fixed shares per trade
    safety_margin    : multiplier on estimated cost for capital check
    """
    agent_id: int
    budget: float
    market_ids: tuple[int, ...]
    observation_delay: int = 1000
    review_interval: int = 5000
    prior_precision: float = 5.0
    signal_precision_assumed: float = 1.0
    disagreement_threshold: float = 0.05
    trade_size: float = 1.0
    confidence_weighted: bool = False
    confidence_floor: float = 0.25
    confidence_ceiling: float = 4.0

    safety_margin: float = 1.2

    # Internal state
    deployed: float = field(default=0.0, init=False)
    pending_cost: float = field(default=0.0, init=False)
    _posterior_mean: dict = field(default_factory=dict, init=False)
    _posterior_precision: dict = field(default_factory=dict, init=False)

    # Population dispatch knobs (NoiseTrader has its own; default 0 here)
    arrival_rate_per_unit: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        if not self.market_ids:
            raise ValueError("market_ids must be non-empty")
        if self.observation_delay < 0:
            raise ValueError("observation_delay must be non-negative")
        if self.review_interval < 0:
            raise ValueError("review_interval must be non-negative")
        if self.prior_precision <= 0:
            raise ValueError("prior_precision must be positive")
        if self.signal_precision_assumed <= 0:
            raise ValueError("signal_precision_assumed must be positive")
        if self.disagreement_threshold < 0:
            raise ValueError("disagreement_threshold must be non-negative")
        if self.trade_size <= 0:
            raise ValueError("trade_size must be positive")
        if self.safety_margin < 1.0:
            raise ValueError("safety_margin must be >= 1.0")
        self.market_ids = tuple(self.market_ids)
        for m in self.market_ids:
            self._posterior_mean[m] = 0.0
            self._posterior_precision[m] = self.prior_precision

    def _choose_trade_size(self, posterior_precision: float) -> float:
        return _compute_trade_size(
            base_size=self.trade_size,
            confidence_weighted=self.confidence_weighted,
            posterior_precision=posterior_precision,
            prior_precision=self.prior_precision,
            floor=self.confidence_floor,
            ceiling=self.confidence_ceiling,
        )

    @property
    def available(self) -> float:
        return self.budget - self.deployed - self.pending_cost

    def observes(self, market_id: int) -> bool:
        return market_id in self._posterior_mean

    def posterior(self, market_id: int) -> tuple[float, float]:
        """Return (μ_post, τ_post) for the given market."""
        return self._posterior_mean[market_id], self._posterior_precision[market_id]

    def update_posterior(self, signal: Signal) -> None:
        """
        Sequential Bayesian update with conjugate Gaussian.

        Posterior precision: τ_new = τ_old + τ_signal
        Posterior mean:      μ_new = (τ_old · μ_old + τ_signal · s) / τ_new

        Modal bias: uses self.signal_precision_assumed for τ_signal regardless
        of signal.noise_std. Tail signals (low noise_std) carry more info than
        this agent extracts.
        """
        m = signal.market_id
        tau_s = self.signal_precision_assumed
        old_mu = self._posterior_mean[m]
        old_tau = self._posterior_precision[m]
        new_tau = old_tau + tau_s
        new_mu = (old_tau * old_mu + tau_s * signal.value) / new_tau
        self._posterior_mean[m] = new_mu
        self._posterior_precision[m] = new_tau

    def decide(
        self,
        sim: Simulator,
        signal: Signal,
        market_env: MarketEnvironment,
    ) -> Optional[TradeRequest]:
        """Reactive path: update posterior with the signal, then consider a trade."""
        self.update_posterior(signal)
        return self._consider_trade(signal.market_id, market_env)

    def review(
        self,
        sim: Simulator,
        market_env: MarketEnvironment,
    ) -> list[TradeRequest]:
        """Periodic review path: check every observed market."""
        out: list[TradeRequest] = []
        for m_id in self.market_ids:
            req = self._consider_trade(m_id, market_env)
            if req is not None:
                out.append(req)
        return out

    def fire_noise(self, sim: Simulator, market_env: MarketEnvironment) -> None:
        return None  # not a noise trader

    def _consider_trade(
        self,
        market_id: int,
        market_env: MarketEnvironment,
    ) -> Optional[TradeRequest]:
        req, cost = _consider_trade_helper(
            agent_id=self.agent_id,
            market_id=market_id,
            posterior_mean=self._posterior_mean[market_id],
            market_env=market_env,
            disagreement_threshold=self.disagreement_threshold,
            trade_size=self._choose_trade_size(self._posterior_precision[market_id]),
            safety_margin=self.safety_margin,
            available=self.available,
        )
        if req is not None:
            self.pending_cost += cost
        return req


# -----------------------------------------------------------------------------
# Noise trader
# -----------------------------------------------------------------------------

@dataclass
class NoiseTrader:
    """
    Background flow. Poisson-arrival random trades.

    Picks a uniform-random market from market_ids, uniform-random side,
    jittered size around mean_trade_size. No beliefs, no posterior, no
    review — just noise.
    """
    agent_id: int
    budget: float
    market_ids: tuple[int, ...]
    arrival_rate_per_unit: float
    mean_trade_size: float = 1.0
    size_jitter: float = 0.5  # uniform multiplier in [1-jitter, 1+jitter]
    safety_margin: float = 1.2

    deployed: float = field(default=0.0, init=False)
    pending_cost: float = field(default=0.0, init=False)

    # Population dispatch knobs (uniform interface with NaiveCredentialedAgent)
    observation_delay: int = field(default=0, init=False)
    review_interval: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if not self.market_ids:
            raise ValueError("market_ids must be non-empty")
        if self.arrival_rate_per_unit < 0:
            raise ValueError("arrival_rate_per_unit must be non-negative")
        if self.mean_trade_size <= 0:
            raise ValueError("mean_trade_size must be positive")
        if not (0 <= self.size_jitter < 1):
            raise ValueError("size_jitter must be in [0, 1)")
        if self.safety_margin < 1.0:
            raise ValueError("safety_margin must be >= 1.0")
        self.market_ids = tuple(self.market_ids)

    @property
    def available(self) -> float:
        return self.budget - self.deployed - self.pending_cost

    def observes(self, market_id: int) -> bool:
        return False

    def decide(self, sim, signal, market_env) -> None:
        return None

    def review(self, sim, market_env) -> list:
        return []

    def fire_noise(
        self,
        sim: Simulator,
        market_env: MarketEnvironment,
    ) -> Optional[TradeRequest]:
        """One noise trade. Picks random market/side/size; capital-checked."""
        m_id = int(sim.rng.choice(self.market_ids))
        is_yes = bool(sim.rng.integers(0, 2))
        multiplier = float(
            sim.rng.uniform(1.0 - self.size_jitter, 1.0 + self.size_jitter)
        )
        shares = multiplier * self.mean_trade_size
        market = market_env.markets[m_id]
        cost_est = market.cost_of_trade(is_yes, shares) * self.safety_margin
        if cost_est > self.available:
            return None
        self.pending_cost += cost_est
        return TradeRequest(
            market_id=m_id,
            agent_id=self.agent_id,
            is_yes=is_yes,
            shares=shares,
        )


Agent = Union[
    NaiveCredentialedAgent,
    NoiseTrader,
    "AggregationDepthAgent",
    "TailEventReasoningAgent",
    "CrossMarketConsistencyAgent",
]


# -----------------------------------------------------------------------------
# Aggregation-depth agent
# -----------------------------------------------------------------------------

@dataclass
class AggregationDepthAgent:
    """
    Aggregation-depth agent.

    Differs from NaiveCredentialedAgent in three ways:
      1. Observes signals on a WIDER SET of markets (`observed_markets` ⊇
         `market_ids`). Cross-market signals update the agent's posterior on
         each primary market via a discounted Bayesian update, weighted by
         the loadings-derived correlation between markets.
      2. Observation is INSTANT (`observation_delay = 0` by default).
      3. Reviews at HIGH FREQUENCY (`review_interval = 500` by default vs
         naive credentialed's 5000).

    The "multiple sub-types varying in evidence-weighting prior" pattern
    from the handoff is realized by instantiating multiple agents with
    different `prior_precision` values — see `make_aggregation_depth_pool`.

    Cross-market signal update
    --------------------------
    For each primary market i, when signal s_j arrives on observed market j
    with weight ρ_ij (≈ cosine similarity of latent loadings):

        τ_effective = signal_precision_assumed · ρ²
        value_eff   = ρ · s_j
        τ_new       = τ_old + τ_effective
        μ_new       = (τ_old · μ_old + τ_effective · value_eff) / τ_new

    This is the precision-weighted sequential update with the cross-market
    signal treated as a discounted own-market signal. For ρ = 1 (own market)
    it reduces to the standard update. For ρ → 0 it adds zero info. Weights
    below `min_cross_weight` are ignored entirely (no event-loop overhead).
    """
    agent_id: int
    budget: float
    market_ids: tuple[int, ...]            # primary markets (where it trades)
    observed_markets: tuple[int, ...]      # superset (where it observes signals)
    cross_weights: dict                    # {(primary_id, observed_id): weight}
    observation_delay: int = 0             # instant by default
    review_interval: int = 500             # high-frequency by default
    prior_precision: float = 2.0           # moderate by default
    signal_precision_assumed: float = 1.0
    disagreement_threshold: float = 0.05
    trade_size: float = 1.0
    confidence_weighted: bool = False
    confidence_floor: float = 0.25
    confidence_ceiling: float = 4.0

    safety_margin: float = 1.2
    min_cross_weight: float = 0.05         # below this, treat cross-market signal as 0

    # Internal state
    deployed: float = field(default=0.0, init=False)
    pending_cost: float = field(default=0.0, init=False)
    _posterior_mean: dict = field(default_factory=dict, init=False)
    _posterior_precision: dict = field(default_factory=dict, init=False)

    # Population dispatch knobs (uniform interface; doesn't fire noise)
    arrival_rate_per_unit: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        if not self.market_ids:
            raise ValueError("market_ids must be non-empty")
        if not self.observed_markets:
            raise ValueError("observed_markets must be non-empty")
        if self.observation_delay < 0:
            raise ValueError("observation_delay must be non-negative")
        if self.review_interval < 0:
            raise ValueError("review_interval must be non-negative")
        if self.prior_precision <= 0:
            raise ValueError("prior_precision must be positive")
        if self.signal_precision_assumed <= 0:
            raise ValueError("signal_precision_assumed must be positive")
        if self.disagreement_threshold < 0:
            raise ValueError("disagreement_threshold must be non-negative")
        if self.trade_size <= 0:
            raise ValueError("trade_size must be positive")
        if self.safety_margin < 1.0:
            raise ValueError("safety_margin must be >= 1.0")
        if not (0 <= self.min_cross_weight <= 1):
            raise ValueError("min_cross_weight must be in [0, 1]")
        self.market_ids = tuple(self.market_ids)
        self.observed_markets = tuple(self.observed_markets)
        for m in self.market_ids:
            if m not in self.observed_markets:
                raise ValueError(
                    f"primary market {m} must be in observed_markets"
                )
        # Posteriors are kept only for primary markets — non-primary markets
        # are observed for information but not traded.
        for m in self.market_ids:
            self._posterior_mean[m] = 0.0
            self._posterior_precision[m] = self.prior_precision

    def _choose_trade_size(self, posterior_precision: float) -> float:
        return _compute_trade_size(
            base_size=self.trade_size,
            confidence_weighted=self.confidence_weighted,
            posterior_precision=posterior_precision,
            prior_precision=self.signal_precision_assumed,
            floor=self.confidence_floor,
            ceiling=self.confidence_ceiling,
        )

    @property
    def available(self) -> float:
        return self.budget - self.deployed - self.pending_cost

    def observes(self, market_id: int) -> bool:
        return market_id in self.observed_markets

    def posterior(self, market_id: int) -> tuple[float, float]:
        return self._posterior_mean[market_id], self._posterior_precision[market_id]

    def update_posterior(self, signal: Signal) -> None:
        """Update every primary market's posterior using this signal."""
        sig_m = signal.market_id
        for primary_m in self.market_ids:
            if primary_m == sig_m:
                weight = 1.0
            else:
                weight = self.cross_weights.get((primary_m, sig_m), 0.0)
            if abs(weight) < self.min_cross_weight:
                continue
            tau_eff = self.signal_precision_assumed * weight * weight
            val_eff = weight * signal.value
            old_mu = self._posterior_mean[primary_m]
            old_tau = self._posterior_precision[primary_m]
            new_tau = old_tau + tau_eff
            new_mu = (old_tau * old_mu + tau_eff * val_eff) / new_tau
            self._posterior_mean[primary_m] = new_mu
            self._posterior_precision[primary_m] = new_tau

    def decide(
        self,
        sim: Simulator,
        signal: Signal,
        market_env: MarketEnvironment,
    ) -> Optional[TradeRequest]:
        """Update posteriors on all primary markets; trade only on primary signals."""
        self.update_posterior(signal)
        if signal.market_id in self._posterior_mean:
            return self._consider_trade(signal.market_id, market_env)
        return None

    def review(
        self,
        sim: Simulator,
        market_env: MarketEnvironment,
    ) -> list[TradeRequest]:
        out: list[TradeRequest] = []
        for m_id in self.market_ids:
            req = self._consider_trade(m_id, market_env)
            if req is not None:
                out.append(req)
        return out

    def fire_noise(self, sim: Simulator, market_env: MarketEnvironment) -> None:
        return None

    def _consider_trade(
        self,
        market_id: int,
        market_env: MarketEnvironment,
    ) -> Optional[TradeRequest]:
        req, cost = _consider_trade_helper(
            agent_id=self.agent_id,
            market_id=market_id,
            posterior_mean=self._posterior_mean[market_id],
            market_env=market_env,
            disagreement_threshold=self.disagreement_threshold,
            trade_size=self._choose_trade_size(self._posterior_precision[market_id]),
            safety_margin=self.safety_margin,
            available=self.available,
        )
        if req is not None:
            self.pending_cost += cost
        return req


# -----------------------------------------------------------------------------
# Helpers for constructing aggregation-depth pools
# -----------------------------------------------------------------------------

def cross_weights_from_loadings(
    loadings: "np.ndarray",
    primary_markets: tuple[int, ...],
    observed_markets: tuple[int, ...],
    min_weight: float = 0.1,
) -> dict[tuple[int, int], float]:
    """
    Compute cross-market weights from latent factor loadings β_m ∈ R^k.

    Weight(i, j) = cosine similarity of β_i, β_j. Self-pairs (i == j) are
    omitted from the returned dict (the agent treats them as weight 1.0
    implicitly). Pairs with |weight| < `min_weight` are dropped.

    Typical usage:
        weights = cross_weights_from_loadings(
            info_env.world.loadings_matrix,
            primary_markets, observed_markets,
        )
    """
    norms = np.linalg.norm(loadings, axis=1)
    out: dict[tuple[int, int], float] = {}
    for i in primary_markets:
        for j in observed_markets:
            if i == j:
                continue
            denom = norms[i] * norms[j]
            if denom < 1e-12:
                continue
            cos_sim = float(loadings[i] @ loadings[j] / denom)
            if abs(cos_sim) >= min_weight:
                out[(i, j)] = cos_sim
    return out


def make_aggregation_depth_pool(
    n_agents: int,
    base_id: int,
    budget: float,
    primary_markets: tuple[int, ...],
    observed_markets: tuple[int, ...],
    cross_weights: dict,
    prior_precisions: Optional[list[float]] = None,
    **kwargs,
) -> list["AggregationDepthAgent"]:
    """
    Build a pool of AggregationDepthAgents with diverse `prior_precision`.

    The "multiple sub-types varying in evidence-weighting prior" pattern from
    the handoff. If `prior_precisions` is None, defaults to a log-spaced
    range from 0.5 (credulous) to 10.0 (skeptical).

    `**kwargs` is forwarded to every agent's constructor (so you can set
    `trade_size`, `disagreement_threshold`, etc. uniformly across the pool).
    """
    if n_agents <= 0:
        raise ValueError("n_agents must be positive")
    if prior_precisions is None:
        if n_agents == 1:
            prior_precisions = [2.0]
        else:
            log_lo, log_hi = math.log(0.5), math.log(10.0)
            prior_precisions = [
                math.exp(log_lo + (log_hi - log_lo) * i / (n_agents - 1))
                for i in range(n_agents)
            ]
    if len(prior_precisions) != n_agents:
        raise ValueError(
            f"len(prior_precisions) = {len(prior_precisions)} != n_agents = {n_agents}"
        )
    return [
        AggregationDepthAgent(
            agent_id=base_id + i,
            budget=budget,
            market_ids=primary_markets,
            observed_markets=observed_markets,
            cross_weights=cross_weights,
            prior_precision=prior_precisions[i],
            **kwargs,
        )
        for i in range(n_agents)
    ]


# -----------------------------------------------------------------------------
# Tail-event reasoning agent
# -----------------------------------------------------------------------------

@dataclass
class TailEventReasoningAgent:
    """
    Tail-event reasoning agent.

    Differs from NaiveCredentialedAgent in two intentional ways, both rooted
    in "correct Bayesian inference with informed prior":

      1. Prior mean per market is logit(base_rate_m), drawn from the agent's
         precomputed base-rate library, instead of anchored at logit(0) =
         probability 0.5. So when p* is in the tail, the prior is in the
         tail — no modal anchor.

      2. Posterior updates use signal.noise_std DIRECTLY as the inverse
         precision, rather than a fixed signal_precision_assumed. Tail
         signals carry σ_tail ≈ 0.4 (precision ≈ 6.25) vs routine signals
         at σ_routine ≈ 1.0 (precision 1.0). The agent automatically weights
         tail signals ~6x more — naive credentialed treats them identically.

    Together these produce the "reaches the tail outcome" behavior the
    handoff calls out for Metric 3, where naive-credentialed-only populations
    fail to push prices into the tail even when truth is there.

    Observation is INSTANT (this is a Bayesian agent — no human reaction
    lag). Review interval is moderate (1000 ticks = 1 unit time by default).
    """
    agent_id: int
    budget: float
    market_ids: tuple[int, ...]
    base_rates: dict           # {market_id: prior_probability in (0, 1)}
    observation_delay: int = 0
    review_interval: int = 1000
    prior_precision: float = 1.0       # weaker than naive's 5.0 — data drives
    disagreement_threshold: float = 0.05
    trade_size: float = 1.0
    confidence_weighted: bool = False
    confidence_floor: float = 0.25
    confidence_ceiling: float = 4.0

    safety_margin: float = 1.2

    # Internal state
    deployed: float = field(default=0.0, init=False)
    pending_cost: float = field(default=0.0, init=False)
    _posterior_mean: dict = field(default_factory=dict, init=False)
    _posterior_precision: dict = field(default_factory=dict, init=False)

    # Population dispatch knobs (uniform interface)
    arrival_rate_per_unit: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        if not self.market_ids:
            raise ValueError("market_ids must be non-empty")
        if self.observation_delay < 0:
            raise ValueError("observation_delay must be non-negative")
        if self.review_interval < 0:
            raise ValueError("review_interval must be non-negative")
        if self.prior_precision <= 0:
            raise ValueError("prior_precision must be positive")
        if self.disagreement_threshold < 0:
            raise ValueError("disagreement_threshold must be non-negative")
        if self.trade_size <= 0:
            raise ValueError("trade_size must be positive")
        if self.safety_margin < 1.0:
            raise ValueError("safety_margin must be >= 1.0")
        self.market_ids = tuple(self.market_ids)
        # Validate base_rates covers all primary markets and produce logit-space priors
        for m in self.market_ids:
            if m not in self.base_rates:
                raise ValueError(f"base_rates missing entry for market {m}")
            p = self.base_rates[m]
            if not (0.0 < p < 1.0):
                raise ValueError(
                    f"base_rates[{m}] = {p} must be in open interval (0, 1)"
                )
            self._posterior_mean[m] = math.log(p / (1.0 - p))
            self._posterior_precision[m] = self.prior_precision

    def _choose_trade_size(self, posterior_precision: float) -> float:
        return _compute_trade_size(
            base_size=self.trade_size,
            confidence_weighted=self.confidence_weighted,
            posterior_precision=posterior_precision,
            prior_precision=self.prior_precision,
            floor=self.confidence_floor,
            ceiling=self.confidence_ceiling,
        )

    @property
    def available(self) -> float:
        return self.budget - self.deployed - self.pending_cost

    def observes(self, market_id: int) -> bool:
        return market_id in self._posterior_mean

    def posterior(self, market_id: int) -> tuple[float, float]:
        return self._posterior_mean[market_id], self._posterior_precision[market_id]

    def update_posterior(self, signal: Signal) -> None:
        """
        Precision-weighted Bayesian update using the signal's ACTUAL noise_std.

        τ_signal = 1 / σ²
        τ_new    = τ_old + τ_signal
        μ_new    = (τ_old · μ_old + τ_signal · s) / τ_new
        """
        if signal.market_id not in self._posterior_mean:
            return
        if signal.noise_std <= 0:
            return
        m = signal.market_id
        tau_s = 1.0 / (signal.noise_std * signal.noise_std)
        old_mu = self._posterior_mean[m]
        old_tau = self._posterior_precision[m]
        new_tau = old_tau + tau_s
        new_mu = (old_tau * old_mu + tau_s * signal.value) / new_tau
        self._posterior_mean[m] = new_mu
        self._posterior_precision[m] = new_tau

    def decide(
        self,
        sim: Simulator,
        signal: Signal,
        market_env: MarketEnvironment,
    ) -> Optional[TradeRequest]:
        self.update_posterior(signal)
        return self._consider_trade(signal.market_id, market_env)

    def review(
        self,
        sim: Simulator,
        market_env: MarketEnvironment,
    ) -> list[TradeRequest]:
        out: list[TradeRequest] = []
        for m_id in self.market_ids:
            req = self._consider_trade(m_id, market_env)
            if req is not None:
                out.append(req)
        return out

    def fire_noise(self, sim: Simulator, market_env: MarketEnvironment) -> None:
        return None

    def _consider_trade(
        self,
        market_id: int,
        market_env: MarketEnvironment,
    ) -> Optional[TradeRequest]:
        req, cost = _consider_trade_helper(
            agent_id=self.agent_id,
            market_id=market_id,
            posterior_mean=self._posterior_mean[market_id],
            market_env=market_env,
            disagreement_threshold=self.disagreement_threshold,
            trade_size=self._choose_trade_size(self._posterior_precision[market_id]),
            safety_margin=self.safety_margin,
            available=self.available,
        )
        if req is not None:
            self.pending_cost += cost
        return req


def base_rates_from_truth(
    info_env: "InformationEnvironment",
    market_ids: tuple[int, ...],
    rng: "np.random.Generator",
    noise_std: float = 0.5,
    clip: float = 0.01,
) -> dict:
    """
    Produce noisy base-rate estimates of p* for a set of markets.

    For each market m:
        noisy_logit_m = info_env.truths[m].logit_p_star + N(0, noise_std²)
        base_rate_m   = clip(sigmoid(noisy_logit_m), clip, 1 - clip)

    Models "agent has historical priors that approximate p* with error."
    noise_std = 0 returns truth; larger noise_std gives more agnostic priors.
    Clipping prevents pathological priors at exactly 0 or 1.

    Caller passes their own RNG so determinism doesn't depend on whether
    this helper is called before or after info_env construction.
    """
    if noise_std < 0:
        raise ValueError("noise_std must be non-negative")
    if not (0 <= clip < 0.5):
        raise ValueError("clip must be in [0, 0.5)")
    out: dict = {}
    for m in market_ids:
        true_logit = info_env.truths[m].logit_p_star
        noisy_logit = true_logit + float(rng.normal(0.0, noise_std)) if noise_std > 0 else true_logit
        p = 1.0 / (1.0 + math.exp(-noisy_logit))
        out[m] = max(clip, min(1.0 - clip, p))
    return out


# -----------------------------------------------------------------------------
# Cross-market consistency agent
# -----------------------------------------------------------------------------

@dataclass
class CrossMarketConsistencyAgent:
    """
    Cross-market consistency agent.

    Maintains a joint Bayesian posterior over the k latent factors f given
    signals observed across a portfolio of markets. From the posterior on
    f, derives implied logit for each market as β_m · μ_post. Trades on
    a market when its implied logit differs from the market's price by
    more than the disagreement threshold.

    Most complex agent class. Uses proper Bayesian updating over heuristic
    coherence check — math is tractable, findings are stronger.

    Posterior representation
    ------------------------
    Stored in information form so updates are O(k²) without inversion:

        Λ ∈ R^{k×k}   precision matrix
        η ∈ R^k       precision-weighted mean

    Mean of the posterior is μ_post = Λ⁻¹ η — the "joint posterior over
    factors" the handoff calls out. Each signal s_j on observed market j
    contributes:

        ΔΛ = τ_s · β_j β_j^T
        Δη = τ_s · s_j · β_j

    where τ_s = 1 / (σ_signal · signal_noise_inflation)². Reading
    signal.noise_std directly means tail signals carry more weight
    automatically (same as TailEventReasoningAgent).

    Cross-market inference
    ----------------------
    Two markets with shared loadings (β_a ≈ β_b) get jointly updated by a
    signal on either: a signal on market A moves μ_post, which moves
    implied_logit(B) = β_b · μ_post too. This is the key property that
    distinguishes this agent from AggregationDepth's discounted-update
    heuristic.

    Capital allocation
    ------------------
    Reactive `decide` trades one share on the signal's market when implied
    disagreement exceeds threshold. Periodic `review` scans ALL primary
    markets, sorts opportunities by |implied − market| descending, and
    processes in that order — so when budget is limited, biggest gaps get
    filled first rather than whichever market came first in market_ids.

    What's modeled vs not
    ---------------------
    The agent's belief about market m's true logit is β_m · μ_post — it
    ignores the per-market idiosyncratic ε_m. Equivalent to "the agent
    can only infer the factor-driven component, not the idiosyncratic
    component." Documented limitation; including ε_m would require
    maintaining one extra posterior per observed market and complicate
    inference; for Task 7 scope this is the right tradeoff.
    """
    agent_id: int
    budget: float
    market_ids: tuple[int, ...]            # markets it trades on
    observed_markets: tuple[int, ...]      # markets it observes signals from (superset)
    loadings: dict                         # {market_id: np.ndarray (k,)}
    observation_delay: int = 0             # instant
    review_interval: int = 1000
    prior_precision_scale: float = 1.0     # Λ_0 = scale * I_k
    signal_noise_inflation: float = 1.0    # multiplier on signal.noise_std for τ_s
    disagreement_threshold: float = 0.05
    trade_size: float = 1.0
    confidence_weighted: bool = False
    confidence_floor: float = 0.25
    confidence_ceiling: float = 4.0

    safety_margin: float = 1.2

    # Internal state
    deployed: float = field(default=0.0, init=False)
    pending_cost: float = field(default=0.0, init=False)
    _k: int = field(default=0, init=False)
    _Lambda: object = field(default=None, init=False)
    _eta: object = field(default=None, init=False)
    _observed_set: set = field(default_factory=set, init=False)
    _primary_set: set = field(default_factory=set, init=False)

    # Population dispatch knobs
    arrival_rate_per_unit: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        if not self.market_ids:
            raise ValueError("market_ids must be non-empty")
        if not self.observed_markets:
            raise ValueError("observed_markets must be non-empty")
        if self.observation_delay < 0:
            raise ValueError("observation_delay must be non-negative")
        if self.review_interval < 0:
            raise ValueError("review_interval must be non-negative")
        if self.prior_precision_scale <= 0:
            raise ValueError("prior_precision_scale must be positive")
        if self.signal_noise_inflation <= 0:
            raise ValueError("signal_noise_inflation must be positive")
        if self.disagreement_threshold < 0:
            raise ValueError("disagreement_threshold must be non-negative")
        if self.trade_size <= 0:
            raise ValueError("trade_size must be positive")
        if self.safety_margin < 1.0:
            raise ValueError("safety_margin must be >= 1.0")

        self.market_ids = tuple(self.market_ids)
        self.observed_markets = tuple(self.observed_markets)
        self._observed_set = set(self.observed_markets)
        self._primary_set = set(self.market_ids)

        for m in self.market_ids:
            if m not in self._observed_set:
                raise ValueError(f"primary market {m} must be in observed_markets")
        for m in self.observed_markets:
            if m not in self.loadings:
                raise ValueError(f"loadings missing entry for observed market {m}")

        # Determine k from any loading vector; require consistent dimensions
        first = np.asarray(self.loadings[self.observed_markets[0]])
        if first.ndim != 1 or first.shape[0] < 1:
            raise ValueError("loadings must be 1-D non-empty arrays")
        self._k = int(first.shape[0])
        # Normalize loadings to numpy arrays of the right shape
        normalized = {}
        for m, beta in self.loadings.items():
            arr = np.asarray(beta, dtype=float)
            if arr.shape != (self._k,):
                raise ValueError(
                    f"loading dimension mismatch for market {m}: "
                    f"expected ({self._k},), got {arr.shape}"
                )
            normalized[m] = arr
        self.loadings = normalized

        # Initialize posterior to prior
        self._Lambda = self.prior_precision_scale * np.eye(self._k)
        self._eta = np.zeros(self._k)

    def _choose_trade_size(self, market_id: int) -> float:
        # Posterior precision on market m's implied logit:
        # β_m^T · Λ · β_m  (scalar)
        if self._Lambda is not None and market_id in self.loadings:
            beta_m = self.loadings[market_id]
            posterior_precision = float(beta_m @ self._Lambda @ beta_m)
        else:
            posterior_precision = self.prior_precision_scale * max(self._k, 1)
        prior_precision = self.prior_precision_scale * max(self._k, 1)
        return _compute_trade_size(
            base_size=self.trade_size,
            confidence_weighted=self.confidence_weighted,
            posterior_precision=posterior_precision,
            prior_precision=prior_precision,
            floor=self.confidence_floor,
            ceiling=self.confidence_ceiling,
        )

    @property
    def available(self) -> float:
        return self.budget - self.deployed - self.pending_cost

    @property
    def k(self) -> int:
        return self._k

    def observes(self, market_id: int) -> bool:
        return market_id in self._observed_set

    def posterior_factor_mean(self) -> "np.ndarray":
        """μ_post = Λ⁻¹ η, the posterior mean of the latent factors."""
        return np.linalg.solve(self._Lambda, self._eta)

    def posterior_factor_covariance(self) -> "np.ndarray":
        """Σ_post = Λ⁻¹."""
        return np.linalg.inv(self._Lambda)

    def implied_logit(self, market_id: int) -> float:
        """β_m · μ_post — the agent's implied logit for market m."""
        if market_id not in self.loadings:
            raise KeyError(f"market {market_id} not in this agent's loadings")
        mu = self.posterior_factor_mean()
        return float(self.loadings[market_id] @ mu)

    def implied_logits_all(self) -> dict:
        """Implied logits for every observed market (one matrix solve)."""
        mu = self.posterior_factor_mean()
        return {m: float(self.loadings[m] @ mu) for m in self.observed_markets}

    def update_posterior(self, signal: Signal) -> None:
        """
        Rank-1 update of (Λ, η).

        ΔΛ = τ_s · β_j β_j^T
        Δη = τ_s · s_j · β_j
        """
        if signal.market_id not in self._observed_set:
            return
        if signal.noise_std <= 0:
            return
        beta = self.loadings[signal.market_id]
        sigma_eff = signal.noise_std * self.signal_noise_inflation
        tau_s = 1.0 / (sigma_eff * sigma_eff)
        # Λ += τ_s · β βᵀ  (outer product, k×k)
        self._Lambda = self._Lambda + tau_s * np.outer(beta, beta)
        # η += τ_s · s · β
        self._eta = self._eta + tau_s * signal.value * beta

    def decide(
        self,
        sim: Simulator,
        signal: Signal,
        market_env: MarketEnvironment,
    ) -> Optional[TradeRequest]:
        """
        Update factor posterior, then trade only if the signal is on a
        primary market and that market's implied logit disagrees with price.
        """
        self.update_posterior(signal)
        if signal.market_id not in self._primary_set:
            return None
        implied = self.implied_logit(signal.market_id)
        return self._consider_trade(signal.market_id, implied, market_env)

    def review(
        self,
        sim: Simulator,
        market_env: MarketEnvironment,
    ) -> list[TradeRequest]:
        """
        Portfolio-wide arbitrage check across all primary markets.

        Sorts opportunities by |p_implied − p_market| descending, processes
        in that order so the largest gap consumes capital first. Documented
        as the "capital allocation logic" per the handoff.
        """
        implied_logits = self.implied_logits_all()
        opportunities: list = []
        for m_id in self.market_ids:
            implied_logit = implied_logits[m_id]
            p_implied = _sigmoid(implied_logit)
            p_market = market_env.price_yes(m_id)
            diff_mag = abs(p_implied - p_market)
            if diff_mag >= self.disagreement_threshold:
                opportunities.append((diff_mag, m_id, implied_logit))
        opportunities.sort(key=lambda t: -t[0])
        trades: list[TradeRequest] = []
        for _, m_id, implied_logit in opportunities:
            req = self._consider_trade(m_id, implied_logit, market_env)
            if req is not None:
                trades.append(req)
        return trades

    def fire_noise(self, sim: Simulator, market_env: MarketEnvironment) -> None:
        return None

    def _consider_trade(
        self,
        market_id: int,
        implied_logit: float,
        market_env: MarketEnvironment,
    ) -> Optional[TradeRequest]:
        req, cost = _consider_trade_helper(
            agent_id=self.agent_id,
            market_id=market_id,
            posterior_mean=implied_logit,
            market_env=market_env,
            disagreement_threshold=self.disagreement_threshold,
            trade_size=self._choose_trade_size(market_id),
            safety_margin=self.safety_margin,
            available=self.available,
        )
        if req is not None:
            self.pending_cost += cost
        return req


def make_cross_market_agent(
    agent_id: int,
    budget: float,
    primary_markets: tuple[int, ...],
    observed_markets: tuple[int, ...],
    info_env: "InformationEnvironment",
    **kwargs,
) -> CrossMarketConsistencyAgent:
    """
    Construct a CrossMarketConsistencyAgent using the world's loading matrix.

    Assumes the agent has perfect knowledge of β_m for each observed market —
    a defensible idealization for prediction markets where cluster/sector
    structure is public knowledge. Real-world relaxation (noisy β) is out
    of scope for Task 7.

    `**kwargs` is forwarded to the constructor (set review_interval,
    trade_size, etc.).
    """
    loadings_matrix = info_env.world.loadings_matrix
    loadings = {m: loadings_matrix[m].copy() for m in observed_markets}
    return CrossMarketConsistencyAgent(
        agent_id=agent_id,
        budget=budget,
        market_ids=primary_markets,
        observed_markets=observed_markets,
        loadings=loadings,
        **kwargs,
    )


# -----------------------------------------------------------------------------
# AgentPopulation orchestrator
# -----------------------------------------------------------------------------

class AgentPopulation:
    """
    Owns a list of agents. Registers four event handlers with the simulator
    and dispatches each event to the relevant agent by agent_id.

    Event types
    -----------
    signal          : from InformationEnvironment; we register the handler
                      and fan out delayed decision events to interested agents
    agent_decision  : payload (agent_id, signal) — fires at signal_t + δ
    agent_review    : payload agent_id — periodic review
    noise_trade     : payload agent_id — NoiseTrader's next firing

    Capital reconciliation runs at the start of every decision/review/noise
    event via _sync_costs (incremental scan over market_env.trade_log).
    """

    SIGNAL_EVENT: str = InformationEnvironment.SIGNAL_EVENT  # "signal"
    DECISION_EVENT: str = "agent_decision"
    REVIEW_EVENT: str = "agent_review"
    NOISE_EVENT: str = "noise_trade"

    def __init__(self, agents: list[Agent]):
        if len(set(a.agent_id for a in agents)) != len(agents):
            raise ValueError("agent_ids must be unique across the population")
        self.agents: list[Agent] = list(agents)
        self.agent_by_id: dict[int, Agent] = {a.agent_id: a for a in self.agents}
        self._sim: Optional[Simulator] = None
        self._market_env: Optional[MarketEnvironment] = None
        self._until_ts: Optional[int] = None
        self._registered: bool = False
        self._log_cursor: int = 0

    @property
    def n_agents(self) -> int:
        return len(self.agents)

    def register(
        self,
        sim: Simulator,
        market_env: MarketEnvironment,
        until_ts: int,
    ) -> None:
        """Register handlers and schedule initial events for every agent."""
        if self._registered:
            raise RuntimeError("AgentPopulation.register called twice")
        sim.register_handler(self.SIGNAL_EVENT, self._on_signal)
        sim.register_handler(self.DECISION_EVENT, self._on_decision)
        sim.register_handler(self.REVIEW_EVENT, self._on_review)
        sim.register_handler(self.NOISE_EVENT, self._on_noise)
        self._sim = sim
        self._market_env = market_env
        self._until_ts = until_ts
        # Initial schedules — iterate in agent-list order for RNG determinism
        for agent in self.agents:
            if agent.review_interval > 0:
                first = sim.now + agent.review_interval
                if first <= until_ts:
                    sim.schedule_at(
                        timestamp=first,
                        event_type=self.REVIEW_EVENT,
                        payload=agent.agent_id,
                        priority=EventPriority.DECISION,
                    )
            if agent.arrival_rate_per_unit > 0:
                self._schedule_next_noise(agent)
        self._registered = True

    # ----- capital reconciliation -----

    def _sync_costs(self) -> None:
        """
        Pull new trade costs from log into agent.deployed (incremental scan
        via _log_cursor).  For each agent whose trades cleared, reset
        pending_cost — correct because all delay=0 trades from previous ticks
        have executed by the time the next decision/review/noise event runs.
        """
        log = self._market_env.trade_log
        if self._log_cursor == len(log):
            return
        affected: set = set()
        for r in log[self._log_cursor:]:
            a = self.agent_by_id.get(r.agent_id)
            if a is not None:
                a.deployed += r.cost
                affected.add(r.agent_id)
        for agent_id in affected:
            self.agent_by_id[agent_id].pending_cost = 0.0
        self._log_cursor = len(log)

    # ----- internal noise scheduling -----

    def _schedule_next_noise(self, agent: NoiseTrader) -> None:
        sim = self._sim
        rate_per_tick = agent.arrival_rate_per_unit / sim.time_resolution
        if rate_per_tick <= 0:
            return
        gap = sim.rng.exponential(1.0 / rate_per_tick)
        t = sim.now + max(1, int(round(gap)))
        if t > self._until_ts:
            return
        sim.schedule_at(
            timestamp=t,
            event_type=self.NOISE_EVENT,
            payload=agent.agent_id,
            priority=EventPriority.DECISION,
        )

    # ----- handlers -----

    def _on_signal(self, sim: Simulator, event: Event) -> None:
        signal: Signal = event.payload
        for agent in self.agents:
            if not agent.observes(signal.market_id):
                continue
            delay = agent.observation_delay
            if sim.now + delay > self._until_ts:
                continue
            sim.schedule(
                delay=delay,
                event_type=self.DECISION_EVENT,
                payload=(agent.agent_id, signal),
                priority=EventPriority.DECISION,
            )

    def _on_decision(self, sim: Simulator, event: Event) -> None:
        self._sync_costs()
        agent_id, signal = event.payload
        agent = self.agent_by_id[agent_id]
        req = agent.decide(sim, signal, self._market_env)
        if req is not None:
            sim.schedule(
                delay=0,
                event_type=MarketEnvironment.TRADE_EVENT,
                payload=req,
                priority=EventPriority.TRADE,
            )

    def _on_review(self, sim: Simulator, event: Event) -> None:
        self._sync_costs()
        agent_id = event.payload
        agent = self.agent_by_id[agent_id]
        for req in agent.review(sim, self._market_env):
            sim.schedule(
                delay=0,
                event_type=MarketEnvironment.TRADE_EVENT,
                payload=req,
                priority=EventPriority.TRADE,
            )
        # Schedule next review
        if agent.review_interval > 0:
            next_t = sim.now + agent.review_interval
            if next_t <= self._until_ts:
                sim.schedule_at(
                    timestamp=next_t,
                    event_type=self.REVIEW_EVENT,
                    payload=agent.agent_id,
                    priority=EventPriority.DECISION,
                )

    def _on_noise(self, sim: Simulator, event: Event) -> None:
        self._sync_costs()
        agent_id = event.payload
        agent = self.agent_by_id[agent_id]
        req = agent.fire_noise(sim, self._market_env)
        if req is not None:
            sim.schedule(
                delay=0,
                event_type=MarketEnvironment.TRADE_EVENT,
                payload=req,
                priority=EventPriority.TRADE,
            )
        # Schedule next noise fire — always, regardless of whether this one
        # succeeded (capital exhaustion shouldn't stop the trader trying again
        # after other trades execute and possibly free up budget via gains).
        if agent.arrival_rate_per_unit > 0:
            self._schedule_next_noise(agent)
