# 情報漏洩防止 運用ルール

## 構成
| 層 | ファイル | 役割 |
|---|---|---|
| 検出 | `security/scan_secrets.py` | シークレット/個人情報スキャン |
| 実行時ガード | `.claude/hooks/guard.py` + `.claude/settings.json` | Claude Code のツール実行前後で遮断/警告 |
| 権限 | `.claude/settings.json` の `permissions.deny` | 機密ファイル Read/Edit/Write の拒否 |
| 防止 | `.gitignore` / `security/pre-commit` | コミット混入防止 |
| 検証 | `security/test_security.sh` | 上記の動作テスト |

## 使い方
```
python3 security/scan_secrets.py [パス]      # 全体スキャン (終了コード1=検出あり)
python3 security/scan_secrets.py --no-pii .  # 個人情報(メール/電話/カード)を除外
python3 security/scan_secrets.py --json .    # JSON出力
sh security/install_git_hook.sh              # git init 後に pre-commit 導入
bash security/test_security.sh               # 動作テスト
```
誤検知は行末に `secscan:ignore` を付ける。検出値は常にマスク表示。

## ガードの挙動
- deny: `.env`/鍵/`.ssh`/`.aws` 等の Read・Edit・Write、Bash での参照、`env`/`printenv` 全出力、シークレットを含む Write/Edit/コマンド/WebFetch
- ask(確認): `curl -d/-F/-T`、`scp`/`rsync`/`nc`、`git push`、`git add -A`/`.`、メール送信
- PostToolUse: 出力や書込ファイルにシークレットがあれば Claude に警告 (ブロックは不可)
- 例外: `.env.example` `.sample` `.template` `.pub` は許可。hook 自体がエラーでも作業は止めない (fail-open)

## 運用チェックリスト
コミット/共有前
- [ ] `scan_secrets.py` を実行し 0 件、または全件説明可能
- [ ] `.env` 等は `.gitignore` 済み。設定値は環境変数/シークレットマネージャ経由
- [ ] ログ・エラー出力・テストデータに実データ(顧客名、メール、電話)がない
- [ ] 外部送信(メール、API、アップロード)は宛先と内容を目視確認

依存関係・権限
- [ ] 新規ライブラリ追加時はライセンスと既知脆弱性を確認 (法務 AI 連携)
- [ ] APIキー/トークンは最小権限・期限付き。使い回さない
- [ ] `.claude/settings.local.json` の広い allow (例: `Read(//Users/kurosuzu/**)`) を定期的に見直す。deny が優先されるが範囲は最小に

漏洩が疑われる場合
1. 該当キーを即時無効化(ローテーション)。履歴から消すだけでは不十分
2. 影響範囲を特定し CEO AI/秘書 AI に報告、`shared/memory.md` セクション8へ記録
3. 個人情報なら法務 AI が報告義務(個人情報保護委員会等)を判断

## 既知の制限
- 正規表現ベース。難読化・分割・base64 化された値、新形式のキーは検出不可。汎用代入パターンは誤検知/見逃しあり
- Bash ガードは文字列ベース。`python -c` やスクリプト経由の間接アクセス、変数展開で組み立てたパスは防げない。コマンド中の `.env` という文字列だけでも deny される(誤遮断)
- PostToolUse は事後警告のみで、出力が既に会話に入った後。Read 結果の遮断は deny 設定に依存
- 個人情報検出は メール/日本の電話/Luhn 通過カード番号のみ。氏名・住所・マイナンバー等は対象外
- `settings.local.json` や ユーザー全体設定で hooks が無効化されると効かない。バイナリ/2MB超/画像・Office 文書は走査対象外
- 現在 git リポジトリではないため pre-commit は `git init` 後に導入が必要
- `shared/memory.md` には社内メールアドレスが含まれる(PII 検出対象)。共有・公開前に確認
