from datetime import datetime, timedelta

import numpy as np

from tablegenius.dataset import build_fit_data
from tablegenius.model import FitData, ModelParams, fit, nll_and_grad, outcome_probs, score_matrix


def synthetic_rows(seed: int = 0, n_teams: int = 8, rounds: int = 4):
    """Simulate a mini-league from known strengths so the fit can be checked."""
    rng = np.random.default_rng(seed)
    att = rng.normal(0, 0.3, n_teams)
    dfn = rng.normal(0, 0.3, n_teams)
    att -= att.mean()
    dfn -= dfn.mean()
    rows = []
    start = datetime(2026, 1, 1)
    day = 0
    for _ in range(rounds):
        for i in range(n_teams):
            for j in range(n_teams):
                if i == j:
                    continue
                lam = np.exp(0.1 + 0.25 + att[i] - dfn[j])
                mu = np.exp(0.1 + att[j] - dfn[i])
                rows.append({"home": i, "away": j, "x": int(rng.poisson(lam)), "y": int(rng.poisson(mu)),
                             "date": start + timedelta(days=day), "season": "s"})
                day += 1
    return rows, att, dfn, start + timedelta(days=day + 1)


def test_gradient_matches_finite_differences():
    rows, _, _, as_of = synthetic_rows(seed=1, n_teams=5, rounds=1)
    params = ModelParams(xi=0.002, prior_strength=1.0)
    data = build_fit_data(rows, list(range(5)), {0, 1, 2, 3}, as_of, params, ["s"])
    rng = np.random.default_rng(2)
    theta = rng.normal(0, 0.2, 2 * 5 + 3)
    theta[-1] = -0.08
    f0, g = nll_and_grad(theta, data, params)
    eps = 1e-6
    for k in range(len(theta)):
        tp = theta.copy()
        tp[k] += eps
        tm = theta.copy()
        tm[k] -= eps
        num = (nll_and_grad(tp, data, params)[0] - nll_and_grad(tm, data, params)[0]) / (2 * eps)
        assert abs(num - g[k]) < 1e-4 * max(1.0, abs(num)), f"param {k}: analytic {g[k]} vs numeric {num}"


def test_fit_recovers_relative_strengths():
    rows, att, dfn, as_of = synthetic_rows(seed=3, n_teams=8, rounds=6)
    params = ModelParams(xi=0.0, prior_strength=0.5)
    data = build_fit_data(rows, list(range(8)), set(range(8)), as_of, params, ["s"])
    r = fit(data, params)
    assert r.converged
    # Strong correlation between true and fitted ratings (exact recovery is impossible with noise).
    assert np.corrcoef(att, r.attack)[0, 1] > 0.85
    assert np.corrcoef(dfn, r.defence)[0, 1] > 0.85
    assert 0.05 < r.home_advantage < 0.5


def test_promoted_prior_and_established_centering():
    rows, _, _, as_of = synthetic_rows(seed=4, n_teams=6, rounds=2)
    params = ModelParams(xi=0.0, prior_strength=3.0, promoted_attack=-0.3, promoted_defence=-0.3)
    # Team 5 has no matches at all (a newly promoted side with no history).
    rows = [r for r in rows if 5 not in (r["home"], r["away"])]
    data = build_fit_data(rows, list(range(6)), {0, 1, 2, 3, 4}, as_of, params, ["s"])
    assert data.established.tolist() == [True] * 5 + [False]
    r = fit(data, params)
    assert abs(r.attack[:5].mean()) < 1e-2 and abs(r.defence[:5].mean()) < 1e-2
    assert abs(r.attack[5] - (-0.3)) < 1e-3 and abs(r.defence[5] - (-0.3)) < 1e-3


def test_score_matrix_is_a_distribution_and_dc_lifts_draws():
    lam = np.array([1.4, 0.8])
    mu = np.array([1.1, 1.6])
    P0 = score_matrix(lam, mu, 0.0, 10)
    P1 = score_matrix(lam, mu, -0.12, 10)
    assert np.allclose(P0.sum(axis=(1, 2)), 1.0) and np.allclose(P1.sum(axis=(1, 2)), 1.0)
    o0, o1 = outcome_probs(P0), outcome_probs(P1)
    assert np.allclose(o0.sum(axis=1), 1.0)
    # Negative rho raises the 0-0 and 1-1 probabilities, so the draw share goes up.
    assert (o1[:, 1] > o0[:, 1]).all()


def test_uncertainty_draws_are_wider_with_less_data():
    from tablegenius.model import sample_ratings
    rows, _, _, as_of = synthetic_rows(seed=8, n_teams=6, rounds=4)
    params = ModelParams(xi=0.0, prior_strength=1.0)
    full = fit(build_fit_data(rows, list(range(6)), set(range(6)), as_of, params, ["s"]), params)
    few = fit(build_fit_data(rows[:30], list(range(6)), set(range(6)), as_of, params, ["s"]), params)
    assert full.cov is not None and few.cov is not None
    sd_full = np.sqrt(np.diag(full.cov)[:6]).mean()
    sd_few = np.sqrt(np.diag(few.cov)[:6]).mean()
    assert sd_few > sd_full > 0
    draws = sample_ratings(full, 50, np.random.default_rng(1))
    assert len(draws) == 50
    spread = np.std([d.attack[0] for d in draws])
    assert abs(spread - np.sqrt(full.cov[0, 0])) < 0.5 * np.sqrt(full.cov[0, 0]) + 0.02
    assert all(-0.25 <= d.rho <= 0.25 for d in draws)


def test_time_weights_and_future_exclusion():
    as_of = datetime(2026, 9, 1)
    rows = [
        {"home": 0, "away": 1, "x": 1, "y": 0, "date": as_of - timedelta(days=0.5), "season": "s"},
        {"home": 1, "away": 0, "x": 1, "y": 0, "date": as_of - timedelta(days=365), "season": "s"},
        {"home": 0, "away": 1, "x": 3, "y": 0, "date": as_of + timedelta(days=3), "season": "s"},  # future
    ]
    data = build_fit_data(rows, [0, 1], {0, 1}, as_of, ModelParams(xi=0.0018), ["s"])
    assert len(data.x) == 2
    assert data.weights[0] > 0.99 and abs(data.weights[1] - np.exp(-0.0018 * 365)) < 1e-9
    assert isinstance(data, FitData)
