"""Matched constant-field comparison using the saved pilot realizations."""

import argparse
import csv
import json
from time import perf_counter

from coupled import save
from movement import REASONS
from transport_diagnostics import ROOT, calculate, load_pilot, recurrence, verify_social


OUTPUT = ROOT / "outputs" / "field_comparison"
FIELDS = (0.0, 0.35, 0.70, 1.05)


def case_id(seed, h, nd):
    return f"field-{seed}-h{h:.2f}-nd{nd}"


def compact(trials, limit, population):
    extra = limit - len(trials)
    if not 0 <= extra < limit or (extra and trials[-1]["cumulative_exits"] != population):
        raise ValueError("only fully evacuated runs may be padded")
    return {
        "arrivals": [0] + [r["cumulative_exits"] for r in trials] + [population] * extra,
        **{key: [0] + [r[key] for r in trials] + [0] * extra for key in REASONS},
    }


def compare_curve(baseline, tested):
    delta = [b - a for a, b in zip(baseline, tested, strict=True)]
    peak = max(map(abs, delta))
    time = next((t for t, d in enumerate(delta) if abs(d) == peak), None) if peak else None
    return {
        "max_abs_difference": peak, "first_peak_t": time,
        "signed_difference_at_first_peak": delta[time] if time is not None else 0,
        "first_difference_t": next((t for t, d in enumerate(delta) if d), None),
        "end_difference": delta[-1],
    }


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_field(h, groups, limit, population):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, panels = plt.subplots(len(groups), 1, figsize=(10, 7.5), sharex=True, layout="constrained")
    styles = ("-", "--", ":", "-.", (0, (5, 2, 1, 2, 1, 2)))
    for ax, (seed, series) in zip(panels, groups.items(), strict=True):
        for (nd, curve), style in zip(series.items(), styles, strict=True):
            ax.step(range(limit + 1), curve["arrivals"], where="post", label=f"Nd={nd}", ls=style)
        ax.set(ylim=(-1, population + 1), ylabel=f"Seed {seed}\nArrived")
        ax.grid(alpha=0.2)
    panels[0].legend(loc="upper left", ncol=5)
    panels[-1].set(xlim=(0, limit), xlabel="Movement trial t (seconds)")
    fig.suptitle(f"Cumulative arrivals | constant h = {h:.2f}")
    fig.savefig(OUTPUT / f"arrivals_h{h:.2f}.svg")
    plt.close(fig)


def benchmark():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    data = load_pilot()
    sample = data["samples"][0]
    h, nd = FIELDS[0], 1
    rid = case_id(sample["seed"], h, nd)
    path = OUTPUT / "benchmark_trial_log.json"
    start = perf_counter()
    case = calculate(data, sample, h, nd, rid)
    series = compact(case.trials, data["settings"]["limit"], data["settings"]["m"])
    compact_text = json.dumps({"run_id": rid, **series}, separators=(",", ":")) + "\n"
    path.write_text(compact_text, encoding="utf-8")
    elapsed = perf_counter() - start
    result = {"run_id": rid, "calculate_and_write_seconds": elapsed,
              "saved_compact_log_bytes": path.stat().st_size,
              "full_log_bytes_if_pretty_printed": len(
                  (json.dumps(case.log, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))}
    save(OUTPUT / "benchmark.json", result)
    print(result)


def sweep():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    data = load_pilot()
    settings = data["settings"]
    limit, population = settings["limit"], settings["m"]
    rows, comparisons, records = [], [], {}
    for h in FIELDS:
        groups = {}
        for sample in data["samples"]:
            seed = sample["seed"]
            cases = {}
            for nd in settings["nd_values"]:
                rid = case_id(seed, h, nd)
                if h == settings["h"]:
                    pilot = next(r for r in data["runs"] if r["seed"] == seed and r["nd"] == nd)
                    summary, trials = pilot, pilot["trials"]
                    from_source = pilot["run_id"]
                else:
                    case = calculate(data, sample, h, nd, rid)
                    cases[nd] = case
                    summary, trials = case.summary, case.trials
                    from_source = None
                series = compact(trials, limit, population)
                groups.setdefault(seed, {})[nd] = series
                records[rid] = series
                rows.append({
                    "seed": seed, "h": h, "nd": nd, "run_id": rid, "reused_pilot": from_source,
                    "arrived_t200": series["arrivals"][-1],
                    "first_exit_t": next((t for t, x in enumerate(series["arrivals"]) if x), None),
                    "t90": summary["t90"], "t_all": summary["t_all"],
                    "intention_stop_person_trials": sum(series["intention_stop"]),
                    "exclusion_stop_person_trials": sum(series["exclusion_stop"]),
                    "observed_trials": len(trials),
                })
            if cases:
                social = recurrence(verify_social(sample, h, cases))
            else:
                diagnosis = json.loads((ROOT / "outputs/transport_diagnostics/diagnostics.json").read_text())
                social = diagnosis[str(seed)]["social_cycle"]
            for nd, series in groups[seed].items():
                baseline = groups[seed][1]
                comparison = compare_curve(baseline["arrivals"], series["arrivals"])
                stop_distance = sum(abs(a - b) for key in REASONS
                                    for a, b in zip(baseline[key], series[key], strict=True))
                comparisons.append({
                    "seed": seed, "h": h, "nd": nd, "run_id": case_id(seed, h, nd),
                    **comparison, "classification_l1": stop_distance,
                    "social_transient_n": social["transient"] if isinstance(social, dict) else None,
                    "social_period_n": social["period"] if isinstance(social, dict) else None,
                })
        plot_field(h, groups, limit, population)
    write_csv(OUTPUT / "conditions.csv", rows)
    write_csv(OUTPUT / "differences_vs_nd1.csv", comparisons)
    (OUTPUT / "series.json").write_text(json.dumps(records, separators=(",", ":")) + "\n",
                                       encoding="utf-8")
    print(f"{len(rows)} conditions including {sum(bool(r['reused_pilot']) for r in rows)} reused")
    print(f"{sum(r['max_abs_difference'] > 0 for r in comparisons)} nonzero arrival differences")
    print(max(comparisons, key=lambda r: r["max_abs_difference"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()
    benchmark() if args.benchmark else sweep()
