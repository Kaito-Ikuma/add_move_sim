"""Paired density experiment and audit of person-level travel times."""

import argparse
from itertools import repeat
import json
from time import perf_counter

from coupled import Clock, replay, run, save
from coupled_demo import replay_data
from field_comparison import case_id, compact, write_csv
from movement import Corridor, Person, REASONS
from nd_pilot import NDS, observations
from phase_prediction import decision_orbit, predict
from transport_diagnostics import ROOT, calculate, load_pilot, restore_sample
from transport_replay import write_html

OUT = ROOT / "outputs/density"
SPANS = (96, 48, 32)
FIELDS = (0., .35, .70)
LENGTH = 112


def person_counts(log, trials):
    length = log["settings"]["length"]
    records = {p["id"]: {"id": p["id"], "initial": p["position"], "final_cell": p["position"],
                         "distance": length + 1 - p["position"], "exit_t": None,
                         **dict.fromkeys(REASONS, 0)} for p in log["initial"]["people"]}
    for trial in log["trials"]:
        for row in trial["people"]:
            if row["active_before"]:
                person = records[row["id"]]
                person[row["reason"]] += 1
                person["final_cell"] = row["new_position"]
                if row["exited"]:
                    person["exit_t"] = trial["t"]
    for p in records.values():
        assert sum(p[key] for key in REASONS) == (p["exit_t"] or len(trials))
        assert p["move"] == p["final_cell"] - p["initial"]
        if p["exit_t"]:
            assert p["move"] == p["distance"]
    for key in REASONS:
        assert sum(p[key] for p in records.values()) == sum(t[key] for t in trials)
    return list(records.values())


def legacy():
    pilot = load_pilot()
    curves = json.loads((ROOT / "outputs/field_comparison/series.json").read_text())
    output = []
    for seed, h, choices in ((102, 0, (1, 2)), (101, .7, NDS)):
        for nd in choices:
            rid = case_id(seed, h, nd)
            if seed == 102:
                log, frames = replay(ROOT / "outputs/transport_replay" / f"{rid}.json")
                _, trials, _ = observations(log, frames)
            else:
                case = calculate(pilot, pilot["samples"][0], h, nd, rid)
                log, trials = case.log, case.trials
            assert compact(trials, 200, 24) == curves[rid]
            output.extend({"run_id": rid, **p} for p in person_counts(log, trials))
    write_csv(OUT / "legacy_people.csv", output)
    print("7 legacy conditions, 168 person histories verified")


def placement(ids, span):
    return tuple(Person(pid, 96 - ((len(ids)-1-i)*span // len(ids)))
                 for i, pid in enumerate(ids))


def pure(people):
    from dataclasses import asdict
    initial = people
    trials, records = [], []
    corridor = Corridor(LENGTH, "absorbing")
    for t in range(1, 201):
        step = corridor.step(people, (1,) * len(people))
        people = step.people
        exited = sum(not p.active for p in people)
        trials.append({"t": t, **step.counts, "cumulative_exits": exited})
        records.append({"t": t, "people": [asdict(row) for row in step.attempts]})
        if exited == len(people):
            break
    log = {"initial": {"people": [asdict(p) for p in initial]}, "trials": records,
           "settings": {"length": LENGTH}}
    return person_counts(log, trials), trials


def calculate_density(sample, ring, h, nd, span):
    rid = f"density-{sample['seed']}-h{h:.2f}-nd{nd}-span{span}"
    log, frames = run(rid, ring, Corridor(LENGTH, "absorbing"), placement(ring.ids, span),
                      sample["s"], Clock(nd, 200), lambda n: h, stop_when_empty=False)
    summary, trials, states = observations(log, frames)
    return log, frames, summary, trials, states


def density():
    from itertools import combinations
    pilot = load_pilot()
    summaries, persons, paired, curves = [], [], [], {}
    controls = {}
    controls_people, controls_trials = [], []
    for span in SPANS:
        rows, trials = pure(placement(pilot["samples"][0]["social_ring"]["ids"], span))
        controls[span] = rows
        controls_people.extend({"rho": 24/span, **p} for p in rows)
        controls_trials.extend({"rho": 24/span, **r} for r in trials)
    write_csv(OUT / "pure_people.csv", controls_people)
    write_csv(OUT / "pure_trials.csv", controls_trials)
    rankings = []
    for sample in pilot["samples"]:
        ring = restore_sample(sample)
        for h in FIELDS:
            orbit, cycle = decision_orbit(ring, sample["s"], h, 4096)
            reference = list(ring.evolve(sample["s"], repeat(h, 1600)))
            for nd in NDS:
                group = {}
                start = perf_counter()
                for span in SPANS:
                    log, frames, summary, trials, states = calculate_density(sample, ring, h, nd, span)
                    assert states == reference[:len(states)]
                    rid = log["run_id"]
                    details = person_counts(log, trials)
                    curve = compact(trials, 200, 24)
                    curves[rid] = curve
                    base = {"run_id": rid, "seed": sample["seed"], "h": h, "nd": nd, "rho": 24/span}
                    row = {**base, "span": span, "arrived_t200": curve["arrivals"][-1],
                           "first_exit": next((t for t,v in enumerate(curve["arrivals"]) if v), None),
                           "t90": summary["t90"], "t_all": summary["t_all"],
                           "final_predicted": predict(Corridor(LENGTH,"absorbing"),placement(ring.ids,span),
                                                      orbit,cycle,nd)["predicted_final"],
                           **{key: sum(curve[key]) for key in REASONS}}
                    summaries.append(row)
                    for p, free in zip(details, controls[span], strict=True):
                        persons.append({**base, **p, "pure_exit_t": free["exit_t"],
                                        "pure_exclusion": free["exclusion_stop"],
                                        "exit_delay_vs_pure": p["exit_t"]-free["exit_t"] if p["exit_t"] else None})
                    group[span] = (rid, details)
                if len(summaries)==3:
                    payload = json.dumps([summaries, persons, curves], separators=(",",":")).encode()
                    bench = OUT / "benchmark.json"
                    save(bench, {"seconds": perf_counter()-start, "conditions":3,
                                 "compact_summary_bytes":len(payload)})
                for lo, hi in combinations(SPANS, 2):
                    low, low_people = group[lo]
                    high, high_people = group[hi]
                    difference = max(abs(a-b) for a,b in zip(curves[low]["arrivals"],curves[high]["arrivals"]))
                    rankings.append((-difference,sample["seed"],h,nd,-lo,hi))
                    for a,b in zip(low_people,high_people,strict=True):
                        if a["exit_t"] and b["exit_t"]:
                            paired.append({"low":low,"high":high,"id":a["id"],
                                           **{key:b[key]-a[key] for key in ("exit_t",*REASONS)}})
    write_csv(OUT/"conditions.csv",summaries)
    write_csv(OUT/"people.csv",persons)
    write_csv(OUT/"paired_exits.csv",paired)
    (OUT/"series.json").write_text(json.dumps(curves,separators=(",",":")))
    neg,seed,h,nd,lo,hi=min(rankings)
    sample=next(s for s in pilot["samples"] if s["seed"]==seed)
    paths=[]
    for span in (-lo,hi):
        log,frames,*_=calculate_density(sample,restore_sample(sample),h,nd,span)
        path=OUT/(log["run_id"]+".json")
        save(path,log)
        assert replay(path)[1]==frames
        paths.append(path.name)
    save(OUT/"selection.json",{"seed":seed,"h":h,"nd":nd,"peak_abs_gap":-neg,"files":paths})
    print(len(summaries),len(persons),len(paired),paths)


def render():
    import csv
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    selection=json.loads((OUT/"selection.json").read_text())
    panels=[]
    fig,ax=plt.subplots(figsize=(8,4),layout="constrained")
    for name in selection["files"]:
        log,frames=replay(OUT/name)
        movement=[f for f in frames if f.phase!="decision"]
        assert len(movement) == 201
        panels.append(replay_data(log,movement))
        ax.step(range(201),[f.cumulative_exits for f in movement],where="post",label=log["run_id"])
    ax.set(xlabel="Movement time (s)",ylabel="Cumulative arrivals")
    ax.legend()
    fig.savefig(OUT/"replay_curves.svg")
    plt.close(fig)
    write_html(OUT/"compare.html",panels,selection["seed"],selection["h"],
               title=f"初期密度による到達の比較 · Nd={selection['nd']}")
    curves=json.loads((OUT/"series.json").read_text())
    with (OUT/"conditions.csv").open() as stream:
        rows=list(csv.DictReader(stream))
    for mode in ("arrivals","stops"):
        fig,axes=plt.subplots(9,5,figsize=(16,20),layout="constrained",sharex=True,sharey=True)
        for i,(seed,h) in enumerate((s,v) for s in (101,102,103) for v in FIELDS):
            for j,nd in enumerate(NDS):
                ax=axes[i,j]
                matched=[r for r in rows if int(r["seed"])==seed and float(r["h"])==h and int(r["nd"])==nd]
                for k,r in enumerate(matched):
                    if mode=="arrivals":
                        ax.step(range(201),curves[r["run_id"]]["arrivals"],where="post",
                                ls=("-","--",":")[k],label=r["rho"])
                    else:
                        a,b=int(r["intention_stop"]),int(r["exclusion_stop"])
                        ax.bar(k,a,color="#aa4c32",label="Intention" if k==0 else None)
                        ax.bar(k,b,bottom=a,color="#4373a0",label="Exclusion" if k==0 else None)
                if mode=="stops":
                    ax.set_xticks(range(3),["0.25","0.50","0.75"])
                if i==0: ax.set_title(f"Nd = {nd}")
                if j==0: ax.set_ylabel(f"Seed {seed}\nh = {h:g}")
                if i==8: ax.set_xlabel("Time (s)" if mode=="arrivals" else "Initial density")
        fig.legend(*axes[0,0].get_legend_handles_labels(),loc="outside upper right",ncol=3)
        fig.suptitle("Cumulative arrivals (people)" if mode=="arrivals" else "Waiting time (person-trials)")
        fig.savefig(OUT/(mode+".svg"))
        plt.close(fig)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("stage",choices=("legacy","density","render"))
    OUT.mkdir(exist_ok=True,parents=True)
    {"legacy":legacy,"density":density,"render":render}[parser.parse_args().stage]()
