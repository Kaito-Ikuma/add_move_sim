# 同期型移動層

Python 3.10 以上の標準ライブラリで実行できます。このフォルダで次のコマンドを実行してください。

```sh
python3 -B -m unittest -v
python3 -B sample_run.py
python3 -B sample_run.py --replay
```

2番目のコマンドは `sample_trajectory.json` を生成し、保存後に読み直した結果を実行時の結果と照合します。3番目は保存済みログを読み込み、在系者の位置、意思停止・排他停止・移動の人数、累積退出人数を表示します。

## 移動層の使い方

`movement.py` の `Corridor(length, boundary).step(people, intentions)` に、固定ID順の参加者列と同じ順序の意思列を渡します。境界は周期境界の `"periodic"` と高台側吸収境界の `"absorbing"` です。更新前の占有だけで判定し、同じID順の更新後状態 `Step.people` と全員分の判定 `Step.attempts` を返します。退出者も参加者列と意思列の同じ添字に残ります。外部の意思層は全員分の意思を更新した後、その最後の意思列を次の試行に渡せます。

周期境界の流量は総移動回数をセル数と更新数で、一人当たり移動率は総移動回数を人数と更新数で割って求めます。全員が前進を試みる周期系の検算には、Fukś (1999) の式 (26) に `m=1` を代入した流量 `min(ρ, 1−ρ)` を使います。 [論文本文](https://arxiv.org/pdf/comp-gas/9902001) · [掲載情報](https://journals.aps.org/pre/abstract/10.1103/PhysRevE.60.197)

## 保存ログと再生

サンプルは吸収境界、通路長5、初期位置 A=2、B=4、C=5 の6試行です。意思列は検算用に外部指定しています。C は第1試行で S=+1 により退出し、第2試行で S=−1 が記録されます。

JSON の `settings` に通路長・境界・意思の出所、`initial` に時刻0の配置、`trials` に各試行の時刻と固定IDごとの意思・更新前後の在系フラグ・旧位置と新位置・判定理由・退出イベントが入ります。退出した試行は `move`、新位置 `L+1`、`exited: true` です。以後は `outside`、両位置が `null`、`exited: false` です。三分類の集計は試行直前の在系者を対象にし、退出は移動に含めます。

再生側は `trajectory.py` の `read_run(Path(...))` から、時刻0を含む `Frame` の列を取得できます。各フレームの `positions` は更新後の在系IDからセル番号への対応、`counts` はその試行の三分類、`cumulative_exits` は更新後の累積退出人数です。時刻0の `counts` は `None` です。

## 固定乱れの意思層

`decisions.py` は初期の固定ID順で周期リングと有向結合を一度構築します。`coupled.py` は各移動試行の前に意思を Nd 回更新し、最後の意思を既存の移動層へ渡します。意思更新の入力は旧意思と外場で、退出後も全員がリングに残ります。参照した仕様は依頼文に記載された `movement_note(1).pdf` 第2、4.2、10–11節の式と規則です。PDF本体はローカルで確認できませんでした。

`python3 -B -m unittest -v` で既存6件と結合4件を検証できます。意思層単体と初期位置の異なる吸収系2本で、全意思更新の状態が完全一致しました。手計算例では第1試行で退出した A が次の更新で反転し、その反転がさらに次の更新で在系中の B の意思を変えます。

## 発表用の再生と研究図

```sh
python3 -B coupled_demo.py
python3 -B coupled_demo.py --replay-only --mp4
open outputs/demo/replay.html
```

`outputs/demo/` に形式2の `coupled_trajectory.json`、自己完結の `replay.html`、研究図 `research.svg` を出力します。2番目のコマンドは計算をやり直さず保存ログから再出力します。`--mp4` は macOS、Pillow、FFmpeg が利用できる場合に指定すると `replay.mp4` を生成します。

デモは手指定の固定乱れで、通路長8、5人、Nd=3、一定外場 h=0 です。run_id は `demo-coupled-01`。初期の通路は左から A、B、C、D、E の順（セル2、3、4、6、8）です。15試行で5人が退出し、初期状態を含む61フレームの位置・意思・集計が保存前後で完全一致しました。HTMLの時刻指定では n が意思更新直後、t が移動試行直後を指します。両者の間はスライダーでも確認できます。MP4 は H.264 / yuv420p で、FFmpeg の全フレーム復号を確認済みです。

## Nd の予備比較

`python3 -B nd_pilot.py` を実行すると、`outputs/nd_pilot/` に比較表 `comparison.csv`、試行別の三分類・累積退出と各標本の初期条件・固定乱れを記録した `observations.json`、代表図 `representative.svg` を出力します。代表図は最小の標本 seed 101 を選び、全 Nd の累積退出と実移動人数を重ねています。

M=24、R=4、σ=0.2、初期密度0.5（人口区間48セル）、通路長64セル、吸収境界で、Nd=1,2,3,4,8 を seed 101–103 の3標本で比較しました。外場は一定の h=0.35、セル長は1 m、移動間隔は1 s、意思更新間隔は 1/Nd s としたモデル上の設定です。μ は平均0.45・標準偏差0.25、φ は平均0・標準偏差0.45の独立な正規乱数とし、有向結合の標準偏差 σJ は0.7です。初期化は別の乱数列（seed+1000）で、区間内の24セルを一様に重複なく抽出し、昇順で固定IDに割り当て、各人の意思を等確率で±1に設定しました。同じ標本の全 Nd でこれらを共有し、共通の意思更新番号の履歴が一致することを確認しています。

15本とも200試行まで観測し、90%・全員到達時刻は全条件で欠測（CSV は空欄、JSON は `null`）でした。90%の閾値は22人です。seed 101、102、103 の未到達人数はそれぞれ24、8、24人で、標本内の累積退出曲線は全 Nd で一致しました。三分類の時系列には Nd による違いがありました。一定外場で連続する意思状態が初めて同一になった更新番号 `fixed_verified_n` は seed 101 が3、103が6で、102では観測中に固定点を確認できませんでした。

## 個人軌道の診断と一定外場の対応比較

作業フォルダで次を順に実行します。図の生成には Matplotlib、動画には macOS のフォント、Pillow、FFmpeg を使います。

```sh
python3 -B -m unittest -v
python3 -B transport_diagnostics.py
python3 -B field_comparison.py --benchmark
python3 -B field_comparison.py
python3 -B transport_replay.py --mp4
open outputs/transport_replay/compare.html
```

- `outputs/transport_diagnostics/` の `results.md` に既存15条件の日本語結果表、`diagnostics.json` に最初の差を生じたID・判定・位置、列先頭の各試行の履歴、意思周期と物理周期、`pilot_102_trajectories.svg` に代表個人軌道図を保存しました。既存の三分類と累積退出は全3,000試行で再現値に一致しました。
- `outputs/field_comparison/` の `conditions.csv` は60条件の到達時刻・人数・停止人回、`differences_vs_nd1.csv` は全時刻での基準との差、`arrivals_h*.svg` は外場別の3標本の曲線です。`series.json` は試行ごとの集計です。時刻は移動試行番号と秒が同値で、未到達時刻はCSVの空欄です。最初の新条件の実測は `benchmark.json` にあり、計算と集計ログ保存で約0.027秒、集計ログ1,901バイトでした。
- `outputs/transport_replay/` の `compare.html`、`compare.mp4`、`trajectories.svg` で同じ移動時刻の Nd=1・2 を比較できます。形式2の全履歴ログはこの2条件だけに保存しました。`selection.json` に選定方法、`scenes.md` に説明用の時刻とIDがあります。

外場は h=0, 0.35, 0.70, 1.05 に固定し、既存の実現乱れ・初期意思・初期位置を全条件で共有しました。15条件の既存集計を再利用し、新規45条件を計算しました。最大の累積退出差は seed 102・h=0 の16人で、t=88に初めて最大になりました。seed 101・h=0.70 では t=17 の1人差があり、t=200 では全 Nd が23人で一致しました。h=0.35 と1.05は全3標本で退出曲線が一致しました。

## 意思周期からの最終退出人数の予測

```sh
python3 -B -m unittest -v
python3 -B phase_prediction.py priority
python3 -B phase_prediction.py existing
python3 -B phase_prediction.py new
python3 -B phase_figure.py
```

`outputs/phase_prediction/` に優先15条件、既存60条件、新規160条件の比較CSV、導出と日本語結果メモ `results.md`、発表図 `seed_102_phases_and_arrivals.svg` を出力します。図には Matplotlib を使用します。固定ID別の正位相、負だけを読むID、周期開始時の配置、独立計算の終了理由は `checkpoints/seed_*.json` にあります。同じコマンドを再実行すると保存済みの条件を使い、未済条件から続けます。検証の上限は意思探索4,096更新、移動の独立計算4,096試行で、200試行時点の値と確定した最終値は別列です。
