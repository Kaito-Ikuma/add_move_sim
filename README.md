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
