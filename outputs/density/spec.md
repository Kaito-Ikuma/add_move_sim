# P0 仕様対応表

基準はローカル HEAD 6e199ee。原本は [理論ノート](../../../同期型移動層追加理論/output/pdf/movement_note.pdf)。既存のログ形式とコマンドは [README](../../README.md) に従う。下表のテストを含む既存18件を `python3 -B -m unittest -v` で今回再実行し全件合格。

|仕様|原本の節・式|実装|対応テストと今回の確認|
|---|---|---|---|
|固定ラベルの規格化核|§2.2 (2.7–2.11)、§6 (6.8)以下|ring_kernel, SocialRing.sample|test_kernel_and_seeded_directed_disorder、左右各1/2、自己参照なし|
|固定乱れ|§2 (2.5–2.6)|SocialRing.sample|同テスト、同seedの再現と有向結合を確認|
|同点保持|§2 (2.4)直後の同期規則|SocialRing.update|test_ties_and_synchronous_swap、零場で旧意思を保持|
|意思の同期更新|§2 (2.2–2.4)|SocialRing.update|同テスト、相互コピーで逐次更新との差を確認|
|意思Nd回の後に移動1回|§10 (10.1–10.5)、§16 (16.1)|coupled.run|test_last_decision_drives_move_and_saved_frames_match、位置固定中の最終意思を使用|
|旧配置による排他|§11 (11.3–11.7)、§12 (12.1–12.4)、§15 (15.1–15.8)|Corridor.step|test_adjacent_people_use_old_occupancy、隣接後方者は停止。§15の連続捕捉時間の全列挙はこのテストの対象外|
|周期境界|§13 (13.1)、付録C|Corridor.step|test_periodic_flows、3密度で流量0.25、0.50、0.25|
|吸収境界|§11.3 (11.11–11.13)|Corridor.step|test_exit_blocks_follower_for_the_same_trial、退出を1移動に算入|
|退出後のノード保持|§4.2（本文）、§16 (16.1)|SocialRing.update, coupled.run|test_independence_at_every_update_and_influence_after_exit、退出者の反転が在系者に伝播|
|共通ログの再生|§17.1 (17.1–17.3) は計測時計。JSON形式は実装仕様|trajectory.read_run, coupled.replay|test_saved_open_trajectory_matches_runtime_and_hand_calculation と結合ログの往復テスト、位置・意思・人数が一致|

保存記録を照合した対象は既存の退出分解と位相予測の表。以前の220条件全体の独立追跡は今回再実行していない。§16の臨界スケーリングと§17の本掃引は未検証。
