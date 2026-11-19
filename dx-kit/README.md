# dxkit — 他社に導入できる AI 業務自動化キット

問い合わせ対応と書類入力という「人手が多く、ルールが明確」な2業務から始め、労働コストを下げる最小構成です。
Python 3 標準ライブラリのみ。`ANTHROPIC_API_KEY` があれば Claude、無ければ規則ベースのモックで動作します。

## 設計方針
| 方針 | 実装 |
|---|---|
| 安全第一 | LLM は「提案」のみ。自動/確認/エスカレーションの判定は `config/company.json` の決定論ルール |
| 根拠のある回答 | ナレッジ（`knowledge/*.md`）に該当が無ければ自動返信しない |
| 人間は例外処理に集中 | 返金・クレーム・法務・不具合は常に担当部署へルーティング |
| 説明可能 | 全判断を `out/audit.jsonl` に追記、`roi` で削減効果を算出 |
| 送信しない | 出力は `out/queue_{auto,review,escalate}.json`。実送信は既存のメール/チャット連携側で行う |

## 導入手順（目安: 半日）
1. `config/company.json` を自社用に編集（社名・ルーティング先・禁止キーワード・時給）
2. `knowledge/` に自社 FAQ を見出し(`# 見出し`)付き Markdown で置く
3. `export ANTHROPIC_API_KEY=...`（任意）
4. `python3 -m dxkit.cli triage samples/inquiries.jsonl`
5. 最初の2週間は `auto` も全件目視 → 誤りが無ければ `auto_reply.enabled` を本番運用へ
6. `python3 -m dxkit.cli intake 書類*.txt` / `python3 -m dxkit.cli roi`

## 拡張ポイント
- 入力: Gmail/Slack/フォーム → JSONL (`id, from, subject, body`) に変換するだけ
- 書類: OCR/PDF 抽出テキストを `intake` に渡す（`parse()` を差し替えれば LLM 抽出にも対応）
- 次の候補業務: 見積書下書き、議事録要約、社内ヘルプデスク

## テスト
`python3 -m unittest discover -s tests`

## 注意
- 個人情報を外部 API に送る場合は、自社の規程・Anthropic との契約条件を確認すること
- ROI の係数はサンプル値。自社の実測値に置き換えること
