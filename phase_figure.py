"""Draw the seed-102 phase sampling and saved arrival curves."""

from itertools import islice, repeat

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from field_comparison import OUTPUT as FIELD_OUTPUT, case_id
from phase_prediction import OUTPUT, read_json
from transport_diagnostics import load_pilot, restore_sample


def main():
    seed = 102
    series = read_json(FIELD_OUTPUT / "series.json")
    results = read_json(OUTPUT / "checkpoints" / f"seed_{seed}.json")
    sample = next(s for s in load_pilot()["samples"] if s["seed"] == seed)
    ring = restore_sample(sample)
    fig, axes = plt.subplots(2, 2, figsize=(12, 6.7), layout="constrained",
                             gridspec_kw={"height_ratios": (1, 1.15)})
    colors = {1: "#12676d", 2: "#b04427"}
    for col, (h, pid) in enumerate(((0.0, "P24"), (0.35, "P08"))):
        top, bottom = axes[:, col]
        run_ids = {nd: case_id(seed, h, nd) for nd in colors}
        record = results[run_ids[1]]
        start, period = record["cycle_start_n"], record["period_n"]
        states = list(islice(ring.evolve(sample["s"], repeat(h)), 13))
        person = ring.ids.index(pid)
        signs = [s[person] for s in states]
        top.axvspan(start, 12.35, color="#e8f0f1", zorder=0)
        top.step(range(13), signs, where="post", color="#283e4a", linewidth=1.8,
                 label=f"{pid} decision")
        for nd, marker, shift in ((1, "o", 0.14), (2, "s", -0.14)):
            n_values = range(nd, 13, nd)
            row = results[run_ids[nd]]
            for n, s in zip(range(row["first_periodic_n"], 13, nd),
                            (states[n] for n in range(row["first_periodic_n"], 13, nd))):
                phase_index = row["phases"].index((n - start) % period)
                if list(s) != row["sampled_vectors"][phase_index]:
                    raise RuntimeError("figure decision disagrees with saved phase vector")
            top.scatter(n_values, [signs[n]+shift for n in n_values], marker=marker,
                        s=28, color=colors[nd], label=f"Read by Nd={nd}", zorder=3)
        top.axvline(start, color="#728590", linestyle=":", linewidth=1)
        top.text(start + 0.18, 0.30, f"Cycle starts n={start}, p={period}", fontsize=9)
        top.set(title=f"h={h:g} | {pid}", xlim=(-0.3, 12.35), ylim=(-1.5, 1.65),
                xticks=range(13), yticks=[-1, 1], xlabel="Decision update n (read at n = Nd × t)")
        top.grid(axis="y", alpha=0.2)
        top.legend(loc="lower center", fontsize=8, ncol=3, bbox_to_anchor=(0.5, -0.02))
        top.set_yticks([-1, 1], labels=["−1", "+1"])
        for nd, linestyle in ((1, "-"), (2, "--")):
            rid = run_ids[nd]
            arrivals = series[rid]["arrivals"]
            bottom.step(range(len(arrivals)), arrivals, where="post",
                        label=rid, linewidth=2, linestyle=linestyle, color=colors[nd])
        for t in ((35, 88) if h == 0 else (18, 48)):
            y = series[run_ids[1]]["arrivals"][t]
            bottom.axvline(t, color="#89949a", lw=0.8, ls=":")
            bottom.annotate(f"t={t}", (t, y), xytext=(4, 8), textcoords="offset points")
        bottom.set(xlim=(0, 200), ylim=(-1, 21), yticks=[0, 4, 8, 12, 16, 20],
                   xlabel="Movement trial t (seconds)", ylabel="Cumulative arrivals")
        bottom.legend(loc="lower right", fontsize=8)
        bottom.grid(alpha=0.2)
    fig.suptitle("Seed 102 | Sampling decision phases and cumulative arrivals", fontsize=16)
    fig.savefig(OUTPUT / "seed_102_phases_and_arrivals.svg")
    plt.close(fig)


if __name__ == "__main__":
    main()
