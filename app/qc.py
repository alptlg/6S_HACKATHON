"""
qc.py  –  Six Sigma quality-control statistics for EMS response times.

RULES (from CLAUDE.md):
  - One plain, tested function per statistic.
  - No FastAPI imports, no file I/O, no network calls.
  - All math must reproduce the SPEC.md §4 known-answer check.

Statistical methods used (SYSEN 5300 course topics):
  1. I-MR Control Chart (Individuals & Moving Range)
     – Works on log-transformed response times to handle right-skew
     – CL  = x̄  (mean of individuals)
     – UCL = x̄ + 2.66 · MR̄      (d2-based, n=2 subgroup)
     – LCL = x̄ − 2.66 · MR̄
     – MR UCL = 3.267 · MR̄        (D4 constant for n=2)
  2. 95% Confidence Interval on the mean response time
     – Uses t-distribution (small samples safe, large samples → normal)
     – Back-transformed from log scale → geometric mean CI
  3. Process Capability (Cpk)
     – Upper spec limit = 8 min (NFPA 1710 ALS target)
     – Computed on ln(response_time_min); Cpu only (one-sided)
  4. NFPA 1710 flag
     – Flag if mean > 8 min OR p90 > 8 min
  5. Descriptive statistics (used in Pareto / priority breakdown)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy import stats as scipy_stats


# ── Data containers ──────────────────────────────────────────────────────────

@dataclass
class IMRResult:
    """I-MR control chart values (log scale + back-transformed minutes)."""
    # log-scale (what the chart is plotted on)
    log_values:  list[float]
    log_cl:      float          # centerline = mean of logs
    log_ucl:     float          # UCL = log_cl + 2.66 * avg_mr
    log_lcl:     float          # LCL = log_cl − 2.66 * avg_mr
    log_mr:      list[float]    # moving ranges
    log_mr_cl:   float          # MR centerline = avg MR
    log_mr_ucl:  float          # MR UCL = 3.267 * avg MR
    # back-transformed minutes (for display)
    cl_min:      float          # exp(log_cl) = geometric mean
    ucl_min:     float          # exp(log_ucl)
    lcl_min:     float          # exp(log_lcl)
    mr_ucl_min:  float          # exp(log_mr_ucl) − context only
    # flags
    n_above_ucl: int            # out-of-control high
    n_below_lcl: int            # out-of-control low


@dataclass
class ConfidenceInterval:
    """95% CI on the mean response time (minutes)."""
    mean_min:   float           # sample mean in minutes
    ci_low:     float           # lower bound (minutes)
    ci_high:    float           # upper bound (minutes)
    geo_mean:   float           # geometric mean (back-transformed from log)
    geo_ci_low: float           # geometric mean CI low
    geo_ci_high: float          # geometric mean CI high
    n:          int
    t_stat:     float
    df:         int


@dataclass
class CapabilityResult:
    """Process capability index (Cpk / Cpu) for NFPA 1710 8-min USL."""
    cpu:        float           # Cpu = (USL − μ_log) / (3σ_log)  [one-sided]
    cpk:        float           # same as Cpu here (one-sided spec)
    usl_min:    float = 8.0
    sigma_log:  float = 0.0
    mu_log:     float = 0.0
    interpretation: str = ""


@dataclass
class DescriptiveStats:
    """Basic descriptive statistics for one group of response times."""
    n:          int
    mean:       float
    median:     float
    std:        float
    min:        float
    p25:        float
    p75:        float
    p90:        float
    max:        float
    geo_mean:   float           # exp(mean of logs)
    nfpa_flag:  bool            # True → zone needs attention


@dataclass
class QCResult:
    """Full QC report for one set of response times."""
    descriptive: DescriptiveStats
    imr:         IMRResult
    ci:          ConfidenceInterval
    capability:  CapabilityResult
    alerts:      list[str] = field(default_factory=list)
    warnings:    list[str] = field(default_factory=list)


# ── Constants ────────────────────────────────────────────────────────────────

D4_N2  = 3.267     # D4 constant for MR chart, subgroup size = 2
D3_N2  = 0.0       # D3 constant (LCL of MR chart is always 0 for n=2)
E2_N2  = 2.660     # E2 constant: UCL factor for I chart  (= 3 / d2, d2=1.128)
NFPA_USL_MIN = 8.0  # NFPA 1710 ALS target: 8 minutes at 90th percentile


# ── Core functions ────────────────────────────────────────────────────────────

def compute_imr(response_times_min: list[float] | np.ndarray) -> IMRResult:
    """
    Compute an I-MR control chart on ln(response_time_min).

    Known-answer check (SPEC.md §4):
      Input: [6, 8, 7, 9, 10]
      log_cl  ≈ 2.0634,  log_ucl ≈ 2.5807,  log_lcl ≈ 1.5461
      cl_min  ≈ 7.87,    ucl_min ≈ 13.21,   lcl_min ≈ 4.69
      MR UCL  ≈ 0.6353 log units
    """
    x = np.asarray(response_times_min, dtype=float)
    if len(x) < 2:
        raise ValueError("I-MR chart requires at least 2 observations.")
    if np.any(x <= 0):
        raise ValueError("All response times must be positive (for log transform).")

    ln_x = np.log(x)

    # Moving ranges (absolute differences of consecutive log values)
    mr = np.abs(np.diff(ln_x))

    log_cl    = float(np.mean(ln_x))
    avg_mr    = float(np.mean(mr))
    log_ucl   = log_cl + E2_N2 * avg_mr
    log_lcl   = log_cl - E2_N2 * avg_mr
    log_mr_ucl = D4_N2 * avg_mr

    return IMRResult(
        log_values  = ln_x.tolist(),
        log_cl      = log_cl,
        log_ucl     = log_ucl,
        log_lcl     = log_lcl,
        log_mr      = mr.tolist(),
        log_mr_cl   = avg_mr,
        log_mr_ucl  = log_mr_ucl,
        cl_min      = math.exp(log_cl),
        ucl_min     = math.exp(log_ucl),
        lcl_min     = math.exp(log_lcl),
        mr_ucl_min  = math.exp(log_mr_ucl),
        n_above_ucl = int(np.sum(ln_x > log_ucl)),
        n_below_lcl = int(np.sum(ln_x < log_lcl)),
    )


def compute_confidence_interval(
    response_times_min: list[float] | np.ndarray,
    confidence: float = 0.95,
) -> ConfidenceInterval:
    """
    95% CI on the mean response time.

    Two CI values are returned:
      1. Arithmetic mean CI (raw minutes) — using t-distribution
      2. Geometric mean CI (back-transformed from log scale)

    The geometric mean CI is more meaningful for lognormal data
    and aligns with the I-MR log-scale analysis.
    """
    x   = np.asarray(response_times_min, dtype=float)
    n   = len(x)
    if n < 2:
        raise ValueError("CI requires at least 2 observations.")

    # Arithmetic CI
    mean    = float(np.mean(x))
    se      = float(scipy_stats.sem(x))
    df      = n - 1
    t_crit  = float(scipy_stats.t.ppf((1 + confidence) / 2, df=df))
    margin  = t_crit * se

    # Geometric CI (on log scale, then back-transform)
    ln_x      = np.log(x)
    log_mean  = float(np.mean(ln_x))
    log_se    = float(scipy_stats.sem(ln_x))
    log_margin = t_crit * log_se

    return ConfidenceInterval(
        mean_min    = mean,
        ci_low      = max(0.0, mean - margin),
        ci_high     = mean + margin,
        geo_mean    = math.exp(log_mean),
        geo_ci_low  = math.exp(log_mean - log_margin),
        geo_ci_high = math.exp(log_mean + log_margin),
        n           = n,
        t_stat      = t_crit,
        df          = df,
    )


def compute_capability(
    response_times_min: list[float] | np.ndarray,
    usl_min: float = NFPA_USL_MIN,
) -> CapabilityResult:
    """
    Compute Cpu (one-sided upper capability index) for NFPA 1710 8-min target.

    Uses log-transformed values because response times are lognormal.
      Cpu = (ln(USL) − μ_log) / (3 · σ_log)

    Interpretation (standard Six Sigma thresholds):
      Cpk ≥ 1.33 → Capable (Six Sigma Green Belt target)
      1.0 ≤ Cpk < 1.33 → Marginally capable
      Cpk < 1.0  → Not capable
    """
    x = np.asarray(response_times_min, dtype=float)
    if np.any(x <= 0):
        raise ValueError("All response times must be positive.")

    ln_x    = np.log(x)
    mu_log  = float(np.mean(ln_x))
    sig_log = float(np.std(ln_x, ddof=1))

    if sig_log == 0:
        # Zero spread: every value meets the USL (+inf) or every value misses it (-inf).
        gap = math.log(usl_min) - mu_log
        cpu = float("inf") if gap > 0 else float("-inf") if gap < 0 else 0.0
    else:
        cpu = (math.log(usl_min) - mu_log) / (3 * sig_log)

    cpk = cpu   # one-sided spec

    if cpk >= 1.33:
        interp = "Capable — process is within NFPA 1710 spec at 4σ level."
    elif cpk >= 1.0:
        interp = "Marginally capable — responses mostly meet 8-min target but with limited margin."
    else:
        interp = "Not capable — response times frequently exceed NFPA 1710 8-min threshold."

    return CapabilityResult(
        cpu=cpu, cpk=cpk,
        usl_min=usl_min, sigma_log=sig_log, mu_log=mu_log,
        interpretation=interp,
    )


def compute_descriptive(
    response_times_min: list[float] | np.ndarray,
    nfpa_usl: float = NFPA_USL_MIN,
) -> DescriptiveStats:
    """Descriptive statistics + NFPA 1710 flag for a group of response times."""
    x   = np.asarray(response_times_min, dtype=float)
    p90 = float(np.percentile(x, 90))
    return DescriptiveStats(
        n        = len(x),
        mean     = float(np.mean(x)),
        median   = float(np.median(x)),
        std      = float(np.std(x, ddof=1)),
        min      = float(np.min(x)),
        p25      = float(np.percentile(x, 25)),
        p75      = float(np.percentile(x, 75)),
        p90      = p90,
        max      = float(np.max(x)),
        geo_mean = float(np.exp(np.mean(np.log(x[x > 0])))),
        # Flag if mean > USL OR p90 > USL (SPEC.md §4)
        nfpa_flag = (float(np.mean(x)) > nfpa_usl) or (p90 > nfpa_usl),
    )


def run_qc(response_times_min: list[float] | np.ndarray) -> QCResult:
    """
    Run the full QC pipeline on a set of response times.
    Returns a QCResult with all charts, stats, and alert messages.
    """
    x = np.asarray(response_times_min, dtype=float)

    desc  = compute_descriptive(x)
    imr   = compute_imr(x)
    ci    = compute_confidence_interval(x)
    cap   = compute_capability(x)

    alerts   = []
    warnings = []

    if desc.nfpa_flag:
        alerts.append(
            f"NFPA 1710 VIOLATION: mean={desc.mean:.1f} min, "
            f"p90={desc.p90:.1f} min (threshold: {NFPA_USL_MIN} min)."
        )
    if imr.n_above_ucl > 0:
        alerts.append(
            f"{imr.n_above_ucl} observation(s) above UCL "
            f"({imr.ucl_min:.1f} min) — process out of control HIGH."
        )
    if imr.n_below_lcl > 0:
        warnings.append(
            f"{imr.n_below_lcl} observation(s) below LCL "
            f"({imr.lcl_min:.1f} min) — unusually fast responses (verify data)."
        )
    if cap.cpk < 1.0:
        alerts.append(f"Cpk={cap.cpk:.2f} — {cap.interpretation}")
    elif cap.cpk < 1.33:
        warnings.append(f"Cpk={cap.cpk:.2f} — {cap.interpretation}")

    if ci.geo_ci_low > NFPA_USL_MIN:
        alerts.append(
            f"95% CI geometric mean [{ci.geo_ci_low:.1f}, {ci.geo_ci_high:.1f}] min — "
            f"entire confidence interval exceeds 8-min NFPA target."
        )
    elif ci.geo_ci_high > NFPA_USL_MIN:
        warnings.append(
            f"95% CI [{ci.geo_ci_low:.1f}, {ci.geo_ci_high:.1f}] min — "
            f"upper bound crosses 8-min NFPA target."
        )

    return QCResult(
        descriptive=desc,
        imr=imr,
        ci=ci,
        capability=cap,
        alerts=alerts,
        warnings=warnings,
    )
