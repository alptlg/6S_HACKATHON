"""Known-answer and degenerate-case tests for app/qc.py.

Known answer: x = [6, 8, 7, 9, 10] minutes (SPEC.md section 4), worked by hand:
  ln x       = 1.79176, 2.07944, 1.94591, 2.19722, 2.30259   mean = 2.06338
  |diff ln x| = 0.28768, 0.13353, 0.25131, 0.10536           MR-bar = 0.19447
  I chart:  UCL = 2.06338 + 2.66 * 0.19447 = 2.58067  -> 13.21 min
            LCL = 2.06338 - 2.66 * 0.19447 = 1.54609  ->  4.69 min
  MR chart: UCL = 3.267 * 0.19447 = 0.63534
  s(ln x) = 0.20184, se = 0.09027, t(0.975, 4) = 2.77645
  geometric-mean 95% CI = exp(2.06338 -/+ 0.25062) = [6.127, 10.115]
  arithmetic 95% CI     = 8 -/+ 2.77645 * 1.58114 / sqrt(5) = [6.037, 9.963]
  Cpu = (ln 8 - 2.06338) / (3 * 0.20184) = 0.0265
"""

import math

import pytest

from app.qc import (
    compute_capability,
    compute_confidence_interval,
    compute_descriptive,
    compute_imr,
    run_qc,
)

X = [6, 8, 7, 9, 10]


def test_imr_known_answer():
    r = compute_imr(X)
    assert r.log_cl == pytest.approx(2.06338, abs=1e-4)
    assert r.log_mr_cl == pytest.approx(0.19447, abs=1e-4)
    assert r.log_ucl == pytest.approx(2.58067, abs=1e-4)
    assert r.log_lcl == pytest.approx(1.54609, abs=1e-4)
    assert r.log_mr_ucl == pytest.approx(0.63534, abs=1e-4)
    assert r.cl_min == pytest.approx(7.87, abs=0.01)
    assert r.ucl_min == pytest.approx(13.21, abs=0.01)
    assert r.lcl_min == pytest.approx(4.69, abs=0.01)
    assert (r.n_above_ucl, r.n_below_lcl) == (0, 0)


def test_ci_known_answer():
    ci = compute_confidence_interval(X)
    assert ci.t_stat == pytest.approx(2.77645, abs=1e-4)
    assert (ci.geo_ci_low, ci.geo_ci_high) == pytest.approx((6.127, 10.115), abs=1e-3)
    assert (ci.ci_low, ci.ci_high) == pytest.approx((6.037, 9.963), abs=1e-3)
    assert ci.df == 4


def test_capability_known_answer():
    cap = compute_capability(X)
    assert cap.sigma_log == pytest.approx(0.20184, abs=1e-4)
    assert cap.cpk == pytest.approx(0.0265, abs=1e-3)
    assert cap.cpk < 1.0


def test_descriptive_known_answer():
    d = compute_descriptive(X)
    assert (d.n, d.mean, d.median) == (5, 8.0, 8.0)
    assert d.p90 == pytest.approx(9.6)  # numpy linear interpolation: 9 + 0.6 * (10 - 9)
    assert d.nfpa_flag  # p90 9.6 > 8


def test_imr_flags_an_obvious_outlier():
    r = compute_imr([7, 7.5, 7, 7.5, 7, 7.5, 7, 60])
    assert r.n_above_ucl == 1


def test_constant_data_below_usl():
    r = run_qc([5, 5, 5, 5])
    assert r.imr.log_mr_cl == 0
    assert r.imr.ucl_min == r.imr.lcl_min == pytest.approx(5)
    assert r.imr.n_above_ucl == r.imr.n_below_lcl == 0
    assert r.capability.cpk == math.inf  # zero spread, every value meets 8 min


def test_constant_data_above_usl_is_not_capable():
    cap = compute_capability([10, 10, 10, 10])
    assert cap.cpk == -math.inf
    assert cap.interpretation.startswith("Not capable")


@pytest.mark.parametrize("bad", [[7.0], [], [5, 0, 6], [5, -1, 6]])
def test_rejects_too_few_or_non_positive(bad):
    with pytest.raises((ValueError, IndexError)):
        run_qc(bad)
