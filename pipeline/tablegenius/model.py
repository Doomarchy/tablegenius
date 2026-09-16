"""Dixon-Coles team-strength model with time-weighted matches and shrinkage priors.

Each match between home team i and away team j is modelled as

    home goals ~ Poisson(lambda),  lambda = exp(c + h + att_i - def_j)
    away goals ~ Poisson(mu),      mu     = exp(c     + att_j - def_i)

with the Dixon-Coles correction tau(x, y) applied to the four low-scoring outcomes
(0-0, 1-0, 0-1, 1-1), which fixes the plain Poisson model's under-prediction of draws.

Ratings maximise the weighted log-likelihood  sum_m w_m log P(x_m, y_m)  with
w_m = exp(-xi * days_before_as_of), minus a ridge penalty pulling each team's attack and
defence towards a prior mean (0 for established teams, a negative "promoted team" prior for
newcomers). Attack and defence are centred on the established teams, so a rating of 0 means
"an average established team in this league" and the intercept c carries the scoring level.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Hashable, Sequence

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

TeamId = Hashable


@dataclass
class ModelParams:
    xi: float = 0.0018                 # time decay per day; half-life = ln 2 / xi days
    prior_strength: float = 3.0        # ridge weight kappa (roughly a few matches' worth of information)
    promoted_attack: float = -0.2      # prior mean for teams not in last season's top flight
    promoted_defence: float = -0.25
    rho_bounds: tuple[float, float] = (-0.25, 0.25)
    max_goals: int = 10                # score matrix truncation for simulation
    constraint_weight: float = 1000.0  # soft constraint keeping established teams centred on 0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ModelParams":
        p = cls()
        p.xi = float(d.get("time_decay_xi_per_day", p.xi))
        p.prior_strength = float(d.get("prior_strength", p.prior_strength))
        promoted = d.get("promoted_prior", {})
        p.promoted_attack = float(promoted.get("attack", p.promoted_attack))
        p.promoted_defence = float(promoted.get("defence", p.promoted_defence))
        rb = d.get("rho_bounds")
        if rb:
            p.rho_bounds = (float(rb[0]), float(rb[1]))
        p.max_goals = int(d.get("max_goals", p.max_goals))
        return p

    @property
    def half_life_days(self) -> float:
        return float(np.log(2) / self.xi) if self.xi > 0 else float("inf")


@dataclass
class FitData:
    """Matches ready for fitting. Team index < n_current are the current-season teams."""
    team_ids: list                      # index -> team id
    home: np.ndarray                    # team index of home side, per match
    away: np.ndarray
    x: np.ndarray                       # home goals
    y: np.ndarray                       # away goals
    weights: np.ndarray                 # time-decay weights
    prior_attack: np.ndarray            # per-team prior mean
    prior_defence: np.ndarray
    established: np.ndarray             # bool mask: teams that anchor the zero point
    n_current: int = 0
    seasons: list[str] = field(default_factory=list)


@dataclass
class Ratings:
    team_ids: list
    attack: np.ndarray
    defence: np.ndarray
    intercept: float
    home_advantage: float
    rho: float
    n_matches: int
    effective_matches: float
    converged: bool
    theta: np.ndarray | None = field(default=None, repr=False)   # full parameter vector at the optimum
    cov: np.ndarray | None = field(default=None, repr=False)     # Laplace-approximation covariance
    index: dict = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.index = {t: i for i, t in enumerate(self.team_ids)}

    def expected_goals(self, home_ids: Sequence[TeamId], away_ids: Sequence[TeamId]) -> tuple[np.ndarray, np.ndarray]:
        hi = np.array([self.index[t] for t in home_ids], dtype=int)
        ai = np.array([self.index[t] for t in away_ids], dtype=int)
        lam = np.exp(self.intercept + self.home_advantage + self.attack[hi] - self.defence[ai])
        mu = np.exp(self.intercept + self.attack[ai] - self.defence[hi])
        return lam, mu

    def team_rating(self, team_id: TeamId) -> dict[str, float]:
        i = self.index[team_id]
        return {"attack": float(self.attack[i]), "defence": float(self.defence[i])}

    def with_flat_teams(self) -> "Ratings":
        """Same scoring level and home advantage, but every team equal (baseline model)."""
        return Ratings(self.team_ids, np.zeros_like(self.attack), np.zeros_like(self.defence),
                       self.intercept, self.home_advantage, self.rho, self.n_matches,
                       self.effective_matches, self.converged)


def _unpack(theta: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray, float, float, float]:
    return theta[:n], theta[n:2 * n], float(theta[2 * n]), float(theta[2 * n + 1]), float(theta[2 * n + 2])


def nll_and_grad(theta: np.ndarray, data: FitData, params: ModelParams) -> tuple[float, np.ndarray]:
    """Penalised negative weighted log-likelihood and its analytic gradient."""
    n = len(data.team_ids)
    att, dfn, c, h, rho = _unpack(theta, n)
    home, away, x, y, w = data.home, data.away, data.x, data.y, data.weights

    loglam = c + h + att[home] - dfn[away]
    logmu = c + att[away] - dfn[home]
    lam = np.exp(loglam)
    mu = np.exp(logmu)

    # Dixon-Coles correction and its partial derivatives.
    m00 = (x == 0) & (y == 0)
    m01 = (x == 0) & (y == 1)
    m10 = (x == 1) & (y == 0)
    m11 = (x == 1) & (y == 1)
    tau = np.ones_like(lam)
    dt_dlam = np.zeros_like(lam)
    dt_dmu = np.zeros_like(lam)
    dt_drho = np.zeros_like(lam)
    tau[m00] = 1 - lam[m00] * mu[m00] * rho
    dt_dlam[m00] = -mu[m00] * rho
    dt_dmu[m00] = -lam[m00] * rho
    dt_drho[m00] = -lam[m00] * mu[m00]
    tau[m01] = 1 + lam[m01] * rho
    dt_dlam[m01] = rho
    dt_drho[m01] = lam[m01]
    tau[m10] = 1 + mu[m10] * rho
    dt_dmu[m10] = rho
    dt_drho[m10] = mu[m10]
    tau[m11] = 1 - rho
    dt_drho[m11] = -1.0
    tau = np.maximum(tau, 1e-8)

    ll = w * (np.log(tau) + x * loglam - lam + y * logmu - mu)

    # d loglik / d loglam and d loglam / d logmu per match
    a_h = (x - lam) + lam * dt_dlam / tau
    a_a = (y - mu) + mu * dt_dmu / tau
    g_att = np.bincount(home, w * a_h, minlength=n) + np.bincount(away, w * a_a, minlength=n)
    g_def = -np.bincount(away, w * a_h, minlength=n) - np.bincount(home, w * a_a, minlength=n)
    g_c = float(np.sum(w * (a_h + a_a)))
    g_h = float(np.sum(w * a_h))
    g_rho = float(np.sum(w * dt_drho / tau))

    # Penalties: ridge towards priors, plus soft centring of established teams.
    k = params.prior_strength
    est = data.established
    n_est = max(int(est.sum()), 1)
    mean_att = float(att[est].mean()) if est.any() else 0.0
    mean_def = float(dfn[est].mean()) if est.any() else 0.0
    cw = params.constraint_weight
    pen = k * float(np.sum((att - data.prior_attack) ** 2) + np.sum((dfn - data.prior_defence) ** 2))
    pen += cw * (mean_att ** 2 + mean_def ** 2)
    gp_att = 2 * k * (att - data.prior_attack) + est * (2 * cw * mean_att / n_est)
    gp_def = 2 * k * (dfn - data.prior_defence) + est * (2 * cw * mean_def / n_est)

    nll = -float(np.sum(ll)) + pen
    grad = np.concatenate([-g_att + gp_att, -g_def + gp_def, [-g_c, -g_h, -g_rho]])
    return nll, grad


def hessian(theta: np.ndarray, data: FitData, params: ModelParams, eps: float = 1e-5) -> np.ndarray:
    """Hessian of the penalised NLL by central differences of the analytic gradient."""
    k = len(theta)
    H = np.zeros((k, k))
    for j in range(k):
        tp = theta.copy()
        tp[j] += eps
        tm = theta.copy()
        tm[j] -= eps
        H[:, j] = (nll_and_grad(tp, data, params)[1] - nll_and_grad(tm, data, params)[1]) / (2 * eps)
    return 0.5 * (H + H.T)


def covariance(theta: np.ndarray, data: FitData, params: ModelParams) -> np.ndarray:
    """Laplace approximation: the inverse Hessian at the optimum is the posterior covariance
    of the ratings (the ridge penalty plays the role of a Gaussian prior)."""
    H = hessian(theta, data, params)
    k = len(theta)
    try:
        cov = np.linalg.inv(H + 1e-8 * np.eye(k))
    except np.linalg.LinAlgError:
        cov = np.linalg.pinv(H)
    cov = 0.5 * (cov + cov.T)
    w, V = np.linalg.eigh(cov)
    w = np.clip(w, 1e-12, None)   # numerical guard: keep it positive definite
    return (V * w) @ V.T


def sample_ratings(ratings: Ratings, n_draws: int, rng: np.random.Generator,
                   rho_bounds: tuple[float, float] = (-0.25, 0.25)) -> list[Ratings]:
    """Draw plausible alternative rating sets from the fitted uncertainty, so simulations
    reflect that the ratings themselves are estimates rather than known truths."""
    if ratings.theta is None or ratings.cov is None or n_draws <= 1:
        return [ratings]
    n = len(ratings.team_ids)
    draws = rng.multivariate_normal(ratings.theta, ratings.cov, size=n_draws, method="eigh")
    out = []
    for th in draws:
        att, dfn, c, h, rho = _unpack(th, n)
        rho = float(np.clip(rho, rho_bounds[0], rho_bounds[1]))
        out.append(Ratings(ratings.team_ids, att.copy(), dfn.copy(), c, h, rho, ratings.n_matches,
                           ratings.effective_matches, ratings.converged))
    return out


def predict_outcomes(draws: Sequence[Ratings], home_ids: Sequence[TeamId], away_ids: Sequence[TeamId],
                     max_goals: int = 10) -> np.ndarray:
    """(F, 3) home/draw/away probabilities averaged over rating draws."""
    acc = None
    for r in draws:
        lam, mu = r.expected_goals(home_ids, away_ids)
        p = outcome_probs(score_matrix(lam, mu, r.rho, max_goals))
        acc = p if acc is None else acc + p
    return acc / len(draws)


def fit(data: FitData, params: ModelParams, compute_cov: bool = True) -> Ratings:
    """Fit ratings by penalised maximum likelihood (L-BFGS-B with analytic gradient)."""
    n = len(data.team_ids)
    theta0 = np.zeros(2 * n + 3)
    if len(data.x) > 0:
        wsum = max(float(data.weights.sum()), 1e-9)
        mean_home = max(float(np.sum(data.weights * data.x) / wsum), 0.2)
        mean_away = max(float(np.sum(data.weights * data.y) / wsum), 0.2)
        theta0[2 * n] = np.log(mean_away)
        theta0[2 * n + 1] = np.log(mean_home / mean_away)
    else:
        theta0[2 * n] = np.log(1.2)
        theta0[2 * n + 1] = 0.25
    theta0[:n] = data.prior_attack
    theta0[n:2 * n] = data.prior_defence
    theta0[2 * n + 2] = -0.05
    bounds = [(None, None)] * (2 * n + 2) + [params.rho_bounds]
    res = minimize(nll_and_grad, theta0, args=(data, params), jac=True, method="L-BFGS-B",
                   bounds=bounds, options={"maxiter": 1000, "gtol": 1e-6})
    att, dfn, c, h, rho = _unpack(res.x, n)
    cov = covariance(res.x, data, params) if compute_cov else None
    return Ratings(
        team_ids=list(data.team_ids), attack=att.copy(), defence=dfn.copy(), intercept=c,
        home_advantage=h, rho=rho, n_matches=int(len(data.x)),
        effective_matches=float(data.weights.sum()), converged=bool(res.success),
        theta=res.x.copy(), cov=cov,
    )


def score_matrix(lam: np.ndarray, mu: np.ndarray, rho: float, max_goals: int) -> np.ndarray:
    """P(home goals = i, away goals = j) for i, j in 0..max_goals, shape (F, K+1, K+1)."""
    ks = np.arange(max_goals + 1)
    px = poisson.pmf(ks[None, :], lam[:, None])
    py = poisson.pmf(ks[None, :], mu[:, None])
    P = px[:, :, None] * py[:, None, :]
    P[:, 0, 0] *= 1 - lam * mu * rho
    P[:, 0, 1] *= 1 + lam * rho
    P[:, 1, 0] *= 1 + mu * rho
    P[:, 1, 1] *= 1 - rho
    P = np.clip(P, 0.0, None)
    P /= P.sum(axis=(1, 2), keepdims=True)
    return P


def outcome_probs(P: np.ndarray) -> np.ndarray:
    """(F, 3) probabilities of home win, draw, away win from a score matrix."""
    K = P.shape[1]
    i, j = np.meshgrid(np.arange(K), np.arange(K), indexing="ij")
    home = P[:, i > j].sum(axis=1)
    draw = P[:, i == j].sum(axis=1)
    away = P[:, i < j].sum(axis=1)
    return np.stack([home, draw, away], axis=1)
