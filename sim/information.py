"""
Continuous-time information environment.

Generates a multi-market world with latent factor correlation structure and a
marked point process of signal arrivals per market. Two tail-event modes:

  - "separate": independent low-rate Poisson process per market for tail signals
  - "marked":   single process per market, each signal independently marked tail

The two modes are statistically equivalent on the aggregate (by the marked
Poisson superposition theorem), but consume RNG differently. The sweep tests
whether downstream findings are robust to the generative scaffold.

Latent factor model
-------------------
    f ~ N(0, I_k)                       latent factor vector (k dim)
    β_m ∈ R^k                           market m's loadings
    ε_m ~ N(0, σ_idio^2)                idiosyncratic component
    logit(p*_m) = β_m · f + ε_m         true logit for market m
    p*_m = sigmoid(logit(p*_m))         true probability

Cluster structure
-----------------
A market in cluster c has high loading on f[c] (drawn around primary_loading_mean)
and small loadings on other factors. Independent markets have small loadings
across all factors and are dominated by ε_m. Markets in the same cluster move
together; markets in different clusters or independent markets do not.

Signal model
------------
    s_routine = logit(p*_m) + N(0, σ_signal^2)
    s_tail    = logit(p*_m) + N(0, σ_tail^2)        with σ_tail < σ_signal

The tail mark itself is the agent-relevant distinction: signal CONTENT differs
only by noise level. Modal-biased Bayesian agents under-weight tail-marked
signals because their prior pulls toward central outcomes; base-rate-prior
agents update correctly. This is the test setup for Metric 3 (tail-regime
behavior).

Determinism: f, β, ε, and all signal noise are drawn from the injected
np.random.Generator. World construction iterates clusters then independents
in declared order; signal scheduling iterates markets by integer id. Same seed
→ same world → same scheduled trajectory.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from sim.events import EventPriority
from sim.simulator import Simulator, schedule_poisson


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class ClusterSpec:
    """A cluster of markets sharing a primary latent factor."""
    primary_factor: int
    market_count: int
    primary_loading_mean: float = 1.5
    primary_loading_std: float = 0.2
    secondary_loading_std: float = 0.15

    def __post_init__(self):
        if self.market_count <= 0:
            raise ValueError("market_count must be positive")
        if self.primary_factor < 0:
            raise ValueError("primary_factor must be non-negative")
        if self.primary_loading_std < 0 or self.secondary_loading_std < 0:
            raise ValueError("loading stds must be non-negative")


@dataclass
class InformationConfig:
    """Top-level config for the information environment."""
    k: int = 5
    clusters: list[ClusterSpec] = field(default_factory=list)
    n_independent_markets: int = 0
    independent_loading_std: float = 0.4
    idiosyncratic_std: float = 0.5

    # Signal noise
    signal_noise_std: float = 1.0
    tail_noise_std: float = 0.4

    # Arrival rates (per unit time, per market)
    routine_rate_per_market: float = 1.0
    tail_rate_per_market: float = 0.05

    # Tail-event scaffold
    tail_mode: str = "separate"  # "separate" or "marked"

    @property
    def n_markets(self) -> int:
        return sum(c.market_count for c in self.clusters) + self.n_independent_markets

    def validate(self) -> None:
        if self.k < 1:
            raise ValueError("k must be >= 1")
        if self.tail_mode not in {"separate", "marked"}:
            raise ValueError(
                f"tail_mode must be 'separate' or 'marked', got {self.tail_mode!r}"
            )
        for c in self.clusters:
            if c.primary_factor >= self.k:
                raise ValueError(
                    f"cluster primary_factor {c.primary_factor} exceeds k={self.k}"
                )
        if self.n_markets == 0:
            raise ValueError("config defines zero markets")
        for name in ("idiosyncratic_std", "signal_noise_std", "tail_noise_std",
                     "independent_loading_std"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        for name in ("routine_rate_per_market", "tail_rate_per_market"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")


# -----------------------------------------------------------------------------
# Truth and signal payloads
# -----------------------------------------------------------------------------

@dataclass(frozen=True, eq=False)
class MarketTruth:
    """The (unobserved) truth about a single market. Agents do not see p_star."""
    market_id: int
    cluster_id: Optional[int]   # None if independent
    loadings: np.ndarray        # shape (k,)
    idiosyncratic: float
    logit_p_star: float
    p_star: float


@dataclass(frozen=True)
class Signal:
    """Payload of a 'signal' event."""
    market_id: int
    value: float        # noisy logit-space observation
    is_tail: bool
    noise_std: float    # the σ used for this signal — agents can weight by it


# -----------------------------------------------------------------------------
# Latent factor world
# -----------------------------------------------------------------------------

class LatentFactorModel:
    """
    Realized latent factor vector and per-market loadings/truths.

    All randomness comes from the injected RNG. Construction order:
      1. Draw f (k draws)
      2. For each cluster, for each market in cluster: draw loadings (k draws),
         draw idiosyncratic (1 draw)
      3. For each independent market: draw loadings (k draws), draw
         idiosyncratic (1 draw)
    """

    def __init__(self, config: InformationConfig, rng: np.random.Generator):
        config.validate()
        self.config = config

        # 1. Latent factors
        self.f: np.ndarray = rng.standard_normal(config.k)

        truths: list[MarketTruth] = []
        market_id = 0

        # 2. Cluster markets
        for cluster_id, cluster in enumerate(config.clusters):
            for _ in range(cluster.market_count):
                loadings = rng.normal(
                    0.0, cluster.secondary_loading_std, size=config.k
                )
                loadings[cluster.primary_factor] = rng.normal(
                    cluster.primary_loading_mean, cluster.primary_loading_std
                )
                idio = float(rng.normal(0.0, config.idiosyncratic_std))
                logit = float(loadings @ self.f + idio)
                p_star = float(1.0 / (1.0 + np.exp(-logit)))
                truths.append(MarketTruth(
                    market_id=market_id,
                    cluster_id=cluster_id,
                    loadings=loadings,
                    idiosyncratic=idio,
                    logit_p_star=logit,
                    p_star=p_star,
                ))
                market_id += 1

        # 3. Independent markets
        for _ in range(config.n_independent_markets):
            loadings = rng.normal(0.0, config.independent_loading_std, size=config.k)
            idio = float(rng.normal(0.0, config.idiosyncratic_std))
            logit = float(loadings @ self.f + idio)
            p_star = float(1.0 / (1.0 + np.exp(-logit)))
            truths.append(MarketTruth(
                market_id=market_id,
                cluster_id=None,
                loadings=loadings,
                idiosyncratic=idio,
                logit_p_star=logit,
                p_star=p_star,
            ))
            market_id += 1

        self.truths: list[MarketTruth] = truths
        self.n_markets: int = len(truths)

    def truth(self, market_id: int) -> MarketTruth:
        return self.truths[market_id]

    @property
    def p_star_array(self) -> np.ndarray:
        return np.array([t.p_star for t in self.truths])

    @property
    def logit_p_star_array(self) -> np.ndarray:
        return np.array([t.logit_p_star for t in self.truths])

    @property
    def loadings_matrix(self) -> np.ndarray:
        """Shape (n_markets, k). Row m is β_m."""
        return np.stack([t.loadings for t in self.truths], axis=0)


# -----------------------------------------------------------------------------
# Information environment
# -----------------------------------------------------------------------------

class InformationEnvironment:
    """
    Owns the latent factor world and the signal-generation point process.

    Usage:
        env = InformationEnvironment(config=cfg, rng=rng)
        counts = env.schedule_signals(sim, until_ts=...)
        sim.register_handler(InformationEnvironment.SIGNAL_EVENT, my_handler)
        sim.run_until(...)

    The env consumes RNG during world construction and during schedule_signals.
    After schedule_signals returns, the full signal trajectory is committed to
    the simulator's event queue.
    """

    SIGNAL_EVENT: str = "signal"

    def __init__(self, config: InformationConfig, rng: np.random.Generator):
        self.config = config
        self.rng = rng
        self.world = LatentFactorModel(config, rng)
        self._scheduled = False

    @property
    def truths(self) -> list[MarketTruth]:
        return self.world.truths

    @property
    def n_markets(self) -> int:
        return self.world.n_markets

    def schedule_signals(self, sim: Simulator, until_ts: int) -> dict[str, int]:
        """
        Pre-schedule signal arrivals from sim.now to until_ts for all markets.

        Returns {"routine": N, "tail": M, "total": N+M}.

        In "marked" mode, each market's signals come from a single Poisson
        process with rate (routine_rate + tail_rate); each signal is then
        independently marked tail with probability tail_rate/(routine_rate+tail_rate).
        In "separate" mode, two independent Poisson processes per market.

        Both modes use the SAME aggregate rate and the SAME expected tail
        fraction, so they're statistically equivalent on the aggregate. The
        scaffold differs in RNG consumption order.
        """
        if self._scheduled:
            raise RuntimeError(
                "schedule_signals already called; create a fresh env for a new run"
            )

        cfg = self.config
        routine_count = [0]
        tail_count = [0]

        if cfg.tail_mode == "separate":
            for m_id in range(self.world.n_markets):
                logit = self.world.truths[m_id].logit_p_star

                def make_routine(s, mid=m_id, lg=logit, rc=routine_count):
                    rc[0] += 1
                    return Signal(
                        market_id=mid,
                        value=float(lg + s.rng.normal(0.0, cfg.signal_noise_std)),
                        is_tail=False,
                        noise_std=cfg.signal_noise_std,
                    )

                def make_tail(s, mid=m_id, lg=logit, tc=tail_count):
                    tc[0] += 1
                    return Signal(
                        market_id=mid,
                        value=float(lg + s.rng.normal(0.0, cfg.tail_noise_std)),
                        is_tail=True,
                        noise_std=cfg.tail_noise_std,
                    )

                schedule_poisson(
                    sim,
                    rate_per_unit_time=cfg.routine_rate_per_market,
                    event_type=self.SIGNAL_EVENT,
                    until_ts=until_ts,
                    payload_fn=make_routine,
                    priority=EventPriority.SIGNAL,
                )
                schedule_poisson(
                    sim,
                    rate_per_unit_time=cfg.tail_rate_per_market,
                    event_type=self.SIGNAL_EVENT,
                    until_ts=until_ts,
                    payload_fn=make_tail,
                    priority=EventPriority.SIGNAL,
                )

        else:  # tail_mode == "marked"
            total_rate = cfg.routine_rate_per_market + cfg.tail_rate_per_market
            if total_rate > 0:
                p_tail = cfg.tail_rate_per_market / total_rate
            else:
                p_tail = 0.0

            for m_id in range(self.world.n_markets):
                logit = self.world.truths[m_id].logit_p_star

                def make_signal(
                    s, mid=m_id, lg=logit, pt=p_tail,
                    rc=routine_count, tc=tail_count,
                ):
                    is_tail = bool(s.rng.random() < pt)
                    sigma = cfg.tail_noise_std if is_tail else cfg.signal_noise_std
                    if is_tail:
                        tc[0] += 1
                    else:
                        rc[0] += 1
                    return Signal(
                        market_id=mid,
                        value=float(lg + s.rng.normal(0.0, sigma)),
                        is_tail=is_tail,
                        noise_std=sigma,
                    )

                schedule_poisson(
                    sim,
                    rate_per_unit_time=total_rate,
                    event_type=self.SIGNAL_EVENT,
                    until_ts=until_ts,
                    payload_fn=make_signal,
                    priority=EventPriority.SIGNAL,
                )

        self._scheduled = True
        return {
            "routine": routine_count[0],
            "tail": tail_count[0],
            "total": routine_count[0] + tail_count[0],
        }
