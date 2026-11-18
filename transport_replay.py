"""Select and replay the matched pair on a common movement clock."""

import argparse
import csv
from dataclasses import replace
from html import escape
import json

from coupled import replay, save
from coupled_demo import render_html, replay_data
from field_comparison import OUTPUT as FIELD_OUTPUT, case_id, compact
from movement import REASONS
from transport_diagnostics import ROOT, calculate, load_pilot, plot_trajectories


OUTPUT = ROOT / "outputs" / "transport_replay"


def select_pair(rows):
    eligible = [r for r in rows if int(r["nd"]) != 1]
    differing = [r for r in eligible if int(r["max_abs_difference"])]
    if differing:
        key = lambda r: (-int(r["max_abs_difference"]), int(r["first_peak_t"]),
                         int(r["seed"]), float(r["h"]), int(r["nd"]))
        return min(differing, key=key), "max_absolute_arrival_difference"
    eligible = [r for r in eligible if int(r["seed"]) == 102 and float(r["h"]) == 0.35]
    return min(eligible, key=lambda r: (-int(r["classification_l1"]), int(r["nd"]))), "stops_l1"


def write_html(path, panels, seed, h):
    documents = []
    for data in panels:
        html = render_html(data).replace('</style>', '''
body{margin:10px;padding:0;font-size:14px}
h1,nav,small{display:none}
header{display:block;margin:8px 0}
h2{font-size:14px;margin:0 0 5px}
section{margin:5px 0;padding:8px}
.row{grid-auto-flow:row;grid-auto-columns:auto;gap:2px}
#ring{grid-template-columns:repeat(12,minmax(0,1fr))}
#road{grid-template-columns:repeat(13,minmax(0,1fr))}
.slot{padding:2px 0;font-size:11px;border-radius:3px;line-height:1.2}
</style>''')
        label = escape(data["run_id"], quote=True)
        documents.append(f'<iframe title="{label}" srcdoc="{escape(html, quote=True)}"></iframe>')
    head = f"""<!doctype html>
<html lang="ja"><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>同じ移動時刻で Nd を比較</title>
<style>
body{{font:16px system-ui;margin:20px auto;padding:0 16px;max-width:1500px;background:#eef4f4;color:#142d39}}
h1{{margin:0 0 4px}} p{{margin:8px 0}} button,input{{font:inherit}} output{{font-weight:bold}}
.controls{{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0;align-items:center}}
#slider{{min-width:160px;flex:1}} #time{{width:5em}}
main{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}
iframe{{width:100%;height:480px;border:1px solid #9cb6bd;border-radius:7px}}
@media(max-width:850px){{main{{grid-template-columns:1fr}}}}
</style>
<h1>同じ移動時刻で Nd を比較</h1>
<p>seed {seed} ｜ h={h:g} ｜ 移動1試行 = 1秒</p>
<p>固定ID順の社会層では、移動試行に使った意思を表示します。破線は退出済みです。</p>
<div class="controls"><button id="play">再生</button><button id="pause">一時停止</button>
<button id="next">1試行進む</button>
<label>t=<input id="time" type="number" min="0" max="{len(panels[0]['frames']) - 1}" value="0"></label>
<input id="slider" aria-label="移動試行" type="range" min="0" max="{len(panels[0]['frames']) - 1}" value="0"></div>
<main>{''.join(documents)}</main>
"""
    controls = """
<script>
const at = id => document.getElementById(id);
const panes = [...document.querySelectorAll("iframe")];
const limit = Number(at("slider").max);
let t = 0, timer = null;
function draw(value) {
  t = Math.max(0, Math.min(limit, Math.trunc(value)));
  panes.forEach(pane => pane.contentWindow.draw?.(t));
  at("time").value = at("slider").value = t;
}
function pause() { clearInterval(timer); timer = null; }
panes.forEach(pane => pane.addEventListener("load", () => draw(t)));
at("play").onclick = () => {
  if (timer !== null) return;
  if (t === limit) draw(0);
  timer = setInterval(() => { draw(t + 1); if (t === limit) pause(); }, 320);
};
at("pause").onclick = pause;
at("next").onclick = () => { pause(); draw(t + 1); };
at("time").onchange = e => { pause(); draw(Number(e.target.value)); };
at("slider").oninput = e => { pause(); draw(Number(e.target.value)); };
draw(0);
</script></html>
"""
    path.write_text(head + controls, encoding="utf-8")


def write_video(path, panels, seed, h):
    from PIL import Image, ImageDraw, ImageFont
    from video_export import WIDTH, HEIGHT, encode_mp4

    font_path = "/System/Library/Fonts/Helvetica.ttc"
    small, normal, headline = [ImageFont.truetype(font_path, s) for s in (13, 19, 31)]

    def render(pair):
        image = Image.new("RGB", (WIDTH, HEIGHT), "#eef4f4")
        draw = ImageDraw.Draw(image)

        def text(x, y, value, font=normal):
            draw.text((x, y), value, font=font, fill="#142d39")

        t = pair[0]["t"]
        text(36, 18, f"Synchronous evacuation | seed {seed} | h = {h:g} | t = {t} s", headline)
        for panel, frame, top in zip(panels, pair, (66, 378), strict=True):
            positions = frame["positions"]
            draw.rounded_rectangle((26, top, 1254, top + 298), 12, fill="white")
            text(43, top + 10, f"{panel['run_id']}   |   Decision update n = {frame['n']}")
            for i, (pid, state) in enumerate(zip(panel["ids"], frame["intentions"], strict=True)):
                x = 45 + i * 49
                color = "#ccecea" if state == 1 else "#fbe1d9"
                draw.rectangle((x, top + 42, x + 46, top + 69), fill=color,
                               outline="#5e7580" if pid not in positions else None)
                text(x + 4, top + 49, f"{pid[1:]}{'+' if state == 1 else '−'}", small)
            occupied = {pos: pid for pid, pos in positions.items()}
            for i in range(panel["length"] + 1):
                x, y = 45 + i % 17 * 68, top + 83 + i // 17 * 40
                pid = occupied.get(i + 1)
                exit_cell = i == panel["length"]
                color = "#ffedb9" if exit_cell else "#ccecea" if pid else "#e1eaed"
                draw.rounded_rectangle((x, y, x + 64, y + 34), 4, fill=color)
                text(x + 3, y + 1, "Exit" if exit_cell else str(i + 1), small)
                if exit_cell:
                    pid = " ".join(frame["exit_ids"])
                if pid:
                    text(x + 25, y + 14, pid, small)
            c = frame["counts"]
            stop = c or dict.fromkeys(("intention_stop", "exclusion_stop", "move"), "—")
            text(43, top + 253, f"Intention stop {stop['intention_stop']}   |   "
                 f"Exclusion stop {stop['exclusion_stop']}   |   Moves {stop['move']}   |   "
                 f"Cumulative arrivals {frame['cumulative_exits']}")
        return image.tobytes()

    pairs = zip(*(panel["frames"] for panel in panels), strict=True)
    encode_mp4(path, map(render, pairs), ticks=8)


def main(mp4=False):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (FIELD_OUTPUT / "differences_vs_nd1.csv").open(newline="") as stream:
        selected, metric = select_pair(list(csv.DictReader(stream)))
    series = json.loads((FIELD_OUTPUT / "series.json").read_text())
    seed, h, chosen_nd = int(selected["seed"]), float(selected["h"]), int(selected["nd"])
    pilot = load_pilot()
    sample = next(s for s in pilot["samples"] if s["seed"] == seed)
    horizon = pilot["settings"]["limit"]
    cases, panels = {}, []
    for nd in (1, chosen_nd):
        rid = case_id(seed, h, nd)
        case = calculate(pilot, sample, h, nd, rid)
        cases[nd] = case
        if compact(case.trials, horizon, pilot["settings"]["m"]) != series[rid]:
            raise RuntimeError(f"representative does not match summary: {rid}")
        path = OUTPUT / f"{rid}.json"
        save(path, case.log)
        log, frames = replay(path)
        if frames != case.frames:
            raise RuntimeError(f"representative replay mismatch: {rid}")
        movement = [f for f in frames if f.phase != "decision"]
        last = movement[-1]
        movement.extend(replace(last, t=t, counts=dict.fromkeys(REASONS, 0))
                        for t in range(last.t + 1, horizon + 1))
        panels.append(replay_data(log, movement))
    write_html(OUTPUT / "compare.html", panels, seed, h)
    plot_trajectories(OUTPUT / "trajectories.svg", cases, seed, h, horizon)
    save(OUTPUT / "selection.json", {
        "metric": metric, "selected": selected, "baseline": case_id(seed, h, 1),
        "arrival_tiebreak": ["earliest peak t", "smallest seed", "smallest h", "smallest Nd"],
        "classification_l1_definition": "sum over trials and the three classes of absolute count differences",
        "fallback_tiebreak": "smallest Nd",
    })
    if mp4:
        write_video(OUTPUT / "compare.mp4", panels, seed, h)
    print(f"{len(panels)} verified representative logs; common movement clock through t={horizon}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mp4", action="store_true")
    main(parser.parse_args().mp4)
