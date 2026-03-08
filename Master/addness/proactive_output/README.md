# proactive_output

最終更新: 2026-03-08

このフォルダは legacy の成果物出力先です。

## 位置づけ

- 現在は Mac Mini Orchestrator の秘書自律ワークがここに成果物を保存する
- 実装上の出力元は `System/mac_mini/agent_orchestrator/scheduler.py` の `_run_secretary_proactive_work`
- 考え方としての正本入口は `Master/output/`

## 使い分け

- 自動処理がここに出したファイルは、そのまま消さない
- 完了した自律ワークは `Master/output/` にもレビューが自動ミラーされる
- 再利用判断に効くものは `Master/output/` にレビュー付きで残す
- 勝ち筋や NG に圧縮できたら `Master/rules/` に引き上げる

## 次の移行方針

- いきなり保存先を変えず、まず `Master/output/` にレビューを蓄積する
- 参照コードの整理が済んだら、保存先を `Master/output/` へ寄せる
- その後に `proactive_output/` は互換レイヤーへ縮小する
