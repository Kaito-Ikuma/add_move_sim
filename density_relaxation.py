"""One-step signed response on the fixed label ring, with a paired binary pulse."""

import sys
from pathlib import Path

import numpy as np

from field_comparison import write_csv
from phase_prediction import decision_orbit
from transport_diagnostics import ROOT, load_pilot, restore_sample

CLOSURE = (ROOT.parent / "シミュレーション/1d_long_range_spinodal/simulations/local_gaussian_closure")
OUT = ROOT / "outputs/density/relaxation"


def closure():
    if not (CLOSURE / "src/model.py").is_file():
        raise FileNotFoundError(CLOSURE / "src/model.py")
    sys.path.insert(0, str(CLOSURE))
    from src.kernel import build_powerlaw_kernel
    from src.model import gaussian_map_step, uniform_map, uniform_map_derivative

    kernel = build_powerlaw_kernel(24, 4, 0.2)
    params = dict(mu=0.45, phi_bar=0., h=0., sigma_eff=0.45)
    fixed = 0.
    assert uniform_map(fixed, **params) == fixed
    derivative = float(uniform_map_derivative(fixed, **params))
    assert abs(derivative) < 1  # normalized nonnegative kernel bounds all other modes
    rows = []
    for index in (0, 1):
        q = 2 * np.pi * index / 24
        radii = np.arange(1, 5)
        weights = radii ** -1.2
        prediction = derivative * np.dot(weights, np.cos(q*radii)) / sum(weights)
        mode = np.cos(q*np.arange(24))
        errors = []
        for eps in (0.01, 0.003, 0.001):
            updated = gaussian_map_step(fixed + eps*mode, np.fft.rfft(kernel), **params)
            ratio = np.dot(updated-fixed,mode) / (eps*np.dot(mode,mode))
            error = abs(ratio-prediction)
            errors.append(error)
            rows.append(dict(k=index,q=q,eps=eps,prediction=prediction,ratio=ratio,error=error))
        assert errors[2] < errors[1] < errors[0]
    write_csv(OUT / "closure.csv", rows)


def binary():
    rows = []
    mode = np.cos(2*np.pi*np.arange(24)/24)
    for sample in load_pilot()["samples"]:
        ring = restore_sample(sample)
        orbit, cycle = decision_orbit(ring, sample["s"], .35, 4096)
        for phase in range(cycle["period"]):
            old = orbit[cycle["transient"] + phase]
            unforced = np.array(ring.update(old, .35))
            for eps in (.01,.03,.05):
                # All sites use the same old state, with only the applied local field changed.
                forced = np.array([ring.update(old, .35 + eps * value)[i]
                                   for i, value in enumerate(mode)])
                delta = forced-unforced
                flipped = [pid for pid, change in zip(ring.ids, delta) if change]
                rows.append(dict(seed=sample["seed"],period=cycle["period"],phase=phase,eps=eps,
                                 count=len(flipped),ids=" ".join(flipped),
                                 signed_amplitude=np.dot(delta,mode)/np.dot(mode,mode)))
    write_csv(OUT / "binary.csv", rows)
    for eps in (.01,.03,.05):
        matched=[r for r in rows if r["eps"]==eps]
        print(eps,sorted({r['seed'] for r in matched if r['count']}),
              min(r['signed_amplitude'] for r in matched),max(r['signed_amplitude'] for r in matched))


if __name__ == "__main__":
    OUT.mkdir(parents=True,exist_ok=True)
    closure()
    binary()
