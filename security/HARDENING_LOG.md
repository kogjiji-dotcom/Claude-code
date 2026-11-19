# 情報漏洩防止ガード 強化ログ (10 ラウンド)

対象: `.claude/hooks/guard.py` / `.claude/settings.json` / `security/scan_secrets.py` / `security/test_security.sh` / `security/SECURITY.md`
前提: `.claude/settings.local.json` は変更しない(各ラウンド終了時に md5 で不変を確認)。偽シークレットはテスト実行時に組み立てる。外部送信・git 操作なし。
開始時点のテスト: 23/23 成功。

Claude Code hooks の仕様確認(公式ドキュメント, 2026-10 時点で確認できた範囲):
- PreToolUse: `permissionDecision` = allow/deny/ask/defer。exit 2 は強制ブロック。exit 1 等は「非ブロッキングエラー(処理続行)」。
- PostToolUse: `updatedToolOutput` で Claude に見える出力を置換可能(ツールの出力スキーマに合わない値は無視される)。`decision:"block"`+`reason` も可。
- timeout 超過した PreToolUse command hook は既定でブロックしない(=フェイルオープン)。`onFailure:"block"` で変更可能だが最小バージョン未確認のため不採用。
- matcher は `|` 区切りの完全一致リスト、記号を含むと未アンカーの正規表現。MCP ツールは `mcp__<server>__<tool>`。
- `disableAllHooks` / `--settings` で hooks 自体は無効化できる(guard では防げない。残存リスク)。

---

## ラウンド 1: フェイルモードの設計(止まらない・黙って素通りしない)

### リスク
- guard.py 内の例外・タイムアウト・不正 JSON は全て「素通り」だった(危険度に関係なく fail-open)。
- `scan_secrets` の import 失敗で hook 全体が機能停止。
- `guard.py` が無い/移動した場合、`python3 guard.py` は終了コード 2 で**全ツールをブロック**し、修復作業も不可能になる(作業停止リスク)。
- `PYTHONPATH` 等の環境変数経由で別モジュールが読まれる余地。
- 巨大入力で正規表現が遅延(ReDoS 的)すると timeout で無音の素通り。
- ブロック/警告の履歴が残らず、誤遮断の検証ができない。

### 対策案と判断
| 案 | 判断 | 理由 |
|---|---|---|
| A. 例外時は縮退モード(内蔵の最小検出: 高信頼度キー形式+機密パス)。ヒットなら deny、なければ許可 | 採用 | 危険度の高い「確実なシークレット/機密パス」だけフェイルクローズ。それ以外は作業を止めない |
| B. 例外時は全面 deny(完全 fail-closed) | 不採用 | バグ1つで全作業が停止。修復用の Edit/Bash も止まり自己ロックアウト |
| C. settings.json のラッパーで guard.py/python3 不在時は exit 0 | 採用 | python の「スクリプト不在」は exit 2=全ブロックになるため。fail-open を明示的に選択(R10 で改ざん検知を追加) |
| D. `python3 -I`(環境変数・ユーザーsite を無視) | 採用 | 低コストで差し替え耐性向上。guard 側で security/ を明示 path 追加 |
| E. 内部タイムアウト(8s, SIGALRM)で縮退モードへ + hook timeout 10/15s | 採用 | 無音の timeout 素通りを避け、縮退検出は必ず実行 |
| F. 2MB 超の書込は ask(未走査で通さない) | 採用 | 「走査できなかった」を許可と同義にしない |
| G. `onFailure:"block"` | 不採用 | 対応バージョン不明。非対応版で挙動不定、かつ A と思想が衝突 |
| H. 監査ログ(`security/guard_audit.log` / `guard_errors.log`、値は残さず種別のみ・自動で末尾100行に切詰め) | 採用 | 誤遮断の棚卸しと hook 故障の検知。`*.log` は .gitignore 済み |

### 実装
- guard.py を再構成: `main()` が全例外を `fallback()` へ。`LITE_SECRETS`(内蔵 9 形式)と機密パス判定は `scan_secrets` 非依存。
- settings.json の hook command をラッパー化(merge、既存 deny 等は無変更)、`timeout` を pre=10 / post=15。
- テスト環境用に `GUARD_LOG_DIR` で監査ログ出力先を差し替え可能(hook プロセスの環境変数であり、エージェントの Bash からは設定できない)。

### 判断表: 危険度別フェイルモード
| 事象 | 動作 | 理由 |
|---|---|---|
| 想定内の検出 | deny/ask (exit 0 + JSON) | 通常動作 |
| 内部例外・不正 JSON・非オブジェクト入力 | 縮退検出でヒット→deny / 無ければ許可 | 確実な危険のみ止め、業務継続を優先 |
| scan_secrets 読込失敗 | 縮退検出(同上) | 同上 |
| timeout(内部 8s) | 縮退検出 | 同上 |
| guard.py 不在 / python3 不在 | 許可(ラッパー) | 全停止の回避。テストと R10 の改ざん検知で補う |
| guard.py の構文エラー | python が exit 1 → 非ブロッキング | 検知はテスト(py_compile)で担保 |

### テスト結果
39/39 成功(新規 16 件: 不正JSON/非オブジェクト入力/縮退モード/ラッパー/timeout設定/コンパイル/監査ログ)。途中、テスト側のクォート不具合(波括弧展開)を 1 件修正。

## ラウンド 2: パス正規化と機密パスの網羅

### リスク
- 機密パス正規表現が**大文字小文字を区別**。macOS(APFS 既定)は区別しないため大文字の `.ENV` / `.SSH/` / `ID_RSA` で素通り。
- `..` 経由、`~`、相対パス、**シンボリックリンク**(`notes.txt -> .env`)は文字列判定のため素通り。
- 命名の網羅漏れ: `.envrc`、`id_rsa_backup`、`.claude/.credentials.json`(先頭ドット)、`client_secret*.json`、`terraform.tfstate`、`*.tfvars`、`kubeconfig`、各種 `*_history`(貼り付けた秘密が残る)、`~/.config/gh`・`gcloud`、ブラウザプロファイル等。
- Grep は `path` しか見ておらず、ディレクトリ全体を `output_mode=content` で検索すると機密ファイルの内容行が出る。`glob:".env*"` も未対策。
- ディレクトリ自体(`~/.ssh` 末尾スラッシュ無し)が対象外。

### 対策案と判断
| 案 | 判断 | 理由 |
|---|---|---|
| 大文字小文字無視(re.I) | 採用 | 実害の大きい迂回で、誤検知増は無視できる(`Foo.KEY` 等は元々対象) |
| `~`展開・cwd 基準の絶対化・`..` 解決・realpath を併用(元表記も判定) | 採用 | hook 入力の `cwd` が使え、実現容易 |
| 命名の追加(上記)、`.pub`/`.example` 等の SAFE は維持 | 採用 | 追加分は秘密を含む可能性が高い名前のみ |
| Grep/Glob: `glob` が機密名を狙う場合は deny | 採用 | `*`→空/x/.x 置換で判定、`*` 単体は誤遮断しない |
| Grep `content`/`count` でツリー内(幅優先・4000件・深さ6)に機密ファイルがあれば ask | 採用 | 秘密が出力に入る唯一の経路。無い環境では一切プロンプトが出ない。`glob`/`type` 指定で絞れば通る |
| Glob のパターン(名前列挙のみ)を遮断 | 不採用 | ファイル名だけで内容は漏れない。誤遮断のコストが大きい |
| Unicode 正規化(全角 `．ｅｎｖ`)対策 | 不採用 | ファイルシステム上は別名になり実害なし |
| ripgrep の .gitignore 尊重を前提にして Grep ask を省く | 不採用 | Claude Code 側の挙動に依存し検証不能。ask のコストは小さい |
| permissions.deny に新名称を追加(マージ、既存は無変更) | 採用 | hook が無効化された場合の二重防御。Edit/Write は鍵・.envrc 等に限定 |

### 実装
guard.py: `SENSITIVE_PATH` 拡張(re.I)、`path_variants()/path_sensitive()`、`glob_sensitive()`、`find_sensitive_in_tree()`。settings.json: deny を 22→57 件(既存全件保持)。
注意: 既存の `Read(**/.env.*)` は `.env.example` も拒否する(hook は許可)。厳しい側なので維持。

### テスト結果
71/71 成功(新規 32 件。大文字/`..`/相対/`~`/symlink/各命名/誤検知しない名前(environment.md, credentials_helper.py, monkey.txt)/Grep 各モード)。settings.local.json は md5 不変。

## ラウンド 3: Bash コマンドの構文解析(文字列マッチから脱却)

### リスク
- 旧実装は空白/記号で割るだけ。`cat .e""nv`、`cat '.env'`、`$'\x2eenv'`、`cat .en*`、`cat {.env,x}`、`f=.en; cat ${f}v`、`bash -c "cat .env"`、`$(...)` 内、`python -c "open('.e'+'nv')"` で素通り。
- ヒアドキュメント本文を丸ごと「コマンド」と見なしており、ドキュメント作成(`cat > x.md <<EOF ... .env ...`)が誤遮断された(実際にこの作業中も発生)。
- `grep -r KEY .` / `tar` / `cp -r` が機密ファイルを含むツリーに対して実行されても検知できない。
- 誤遮断: `ls .env`、`test -f .env`、`git commit -m "...env..."`、`echo ".env は ignore"` まで deny。

### 対策案と判断
| 案 | 判断 | 理由 |
|---|---|---|
| shlex(punctuation_chars)でトークン化し、クォート除去・`;|&()<>` 分割・コマンド名/引数/リダイレクト先を構造化 | 採用 | 標準ライブラリのみ。クォート分割系の迂回がほぼ無効化される |
| ANSI-C(`$'..'`)展開、バッククォートを `$( )` に正規化、改行を区切り化 | 採用 | 低コスト |
| ブレース展開・`~`・既知変数・同一コマンド内の代入(`f=...; ${f}`)の伝播・実ファイルシステムへの glob 展開 | 採用 | 実在ファイルに展開された場合のみ判定するので誤遮断が増えない |
| `bash -c`/`eval`/`$(...)` の再帰解析(深さ3)、`python/node/ruby -c/-e` はインライン文字列を解析(`'a'+'b'` 連結解除) | 採用 | 典型的な迂回経路 |
| ヒアドキュメント: 消費コマンドが interpreter ならコード、それ以外はデータとして扱う | 採用 | 文書作成の誤遮断を解消しつつ、`python - <<EOF` の迂回を防ぐ |
| 内容を出さないコマンド(ls/stat/test/[/echo/printf、git の check-ignore・commit -m 等)の引数は許可。ただし `$()` 内・xargs へのパイプ・リダイレクト付き echo は対象 | 採用 | 誤遮断の主因を解消。`echo .env \| xargs cat` 等の迂回は閉じる |
| 再帰 grep(-r)/rg --hidden/tar/zip/cp -r/rsync で対象ツリーに機密ファイルがあれば ask | 採用 | 機密が無い環境ではプロンプトは出ない(R2 と同じ探索器) |
| 任意変数展開の完全シミュレーション(`$(cmd)` の結果、関数、ループ、`read`) | 不採用 | 静的解析では原理的に不可能。R4 で「動的組み立て自体」を ask する方針で補う |
| スクリプトファイル(`python3 x.py`)の中身を検査して機密パス参照を遮断 | 不採用 | `load_dotenv('.env')` のような正当なアプリコードを大量に誤遮断する。費用対効果が低い |

### 実装
guard.py に `_prep / split_heredocs / tokenize / build_segments / split_cmd / word_candidates / analyze_bash` 等を追加し、pre の Bash 判定を `analyze_bash` に置換(旧 `bash_sensitive_token` は縮退モード専用に残置)。

### テスト結果
118/118 成功(新規 47 件、迂回 31 種 + 誤遮断低減 12 種)。途中で2件不合格 → 修正: ①クォート内 `"$(cat ..)"` を echo の例外で見逃していた(全単語で `$()` 解析するよう変更)、②テストが実環境の ~/.ssh 有無に依存(偽 HOME を使うよう変更)。実運用で使う典型コマンド(find/pip/git/python -c/open 等)が許可のままであることも確認、hook 実行時間は約30ms。

## ラウンド 4: 資格情報の取得・環境変数・動的組み立て

### リスク
- 旧 `ENV_DUMP` は `env`/`printenv`/`set` の一部形だけ。`printenv AWS_SECRET_ACCESS_KEY`(単体指定)、`echo $GITHUB_TOKEN`、`declare -x`、`ps eww`、`python -c "print(dict(os.environ))"`、`node -e 'console.log(process.env)'` は素通り。さらにヒアドキュメント内の文字列でも誤発火していた。
- ファイルを読まずに秘密を取り出す正規コマンド(キーチェーン、`gh auth token`、`gcloud auth print-access-token`、`aws configure get`、`kubectl get secret` 等)が未対策。
- 文字列を実行時に組み立てる迂回(`curl | sh`、`base64 -d | bash`、`$(printf '\x2e..')`、`eval "$X"`、`exec(b64decode(..))`)は静的解析では解けない。

### 対策案と判断
| 案 | 判断 | 理由 |
|---|---|---|
| env/printenv/export -p/declare -x/set/compgen -e/ps eww/launchctl を構造化判定(コマンド名+引数)で deny/ask | 採用 | `env FOO=1 cmd`・`set -e`・`printenv PATH`・`ps aux` は許可のまま |
| 表示系コマンド(echo/printf/cat/tee/base64 等)に秘密らしき変数名(*TOKEN*/*SECRET*/*PASSWORD*/*API_KEY*…)の展開を渡すのを deny。here-string も同様 | 採用 | 値を会話に出す唯一の目的の操作。`curl -H "Bearer $TOKEN"`(値を表示しない利用)は許可のまま |
| 資格情報取得コマンド表(deny: keychain/gh auth token/gcloud print-*-token/aws configure get/gpg --export-secret。ask: AWS secretsmanager・kubectl secret・docker inspect・op/pass/vault 等) | 採用 | 表駆動で保守が容易。deny は「値そのものを出す」もの、ask は用途次第のもの |
| インラインコード: 環境変数の一括出力は deny、秘密名の環境変数参照は ask、`exec/eval/chr/b64decode/getattr` 等の難読化兆候は ask | 採用 | 正当な `python -c` は通る。難読化兆候は誤検知もありうるため ask 止まり |
| `curl|sh`、`base64 -d|sh`、`$()` 内のデコード/rev/printf エスケープ、eval+変数 を ask | 採用 | 動的組み立ては解析不能なので、人間確認に回す(deny にすると運用阻害が大きい) |
| `/dev/tcp`・`/dev/udp` を deny、`/proc/*/environ` を機密パス化 | 採用 | 正当用途がほぼ無い |
| 全変数の値をシミュレートして `$(...)` 結果を静的に求める | 不採用 | 原理的に不可能(R3 と同じ) |
| `history`、`defaults read`、`git config --list`、`git remote -v` の ask | 不採用 | 非対話シェルでは履歴が空/頻用コマンドで誤遮断が多い。トークン混入は PostToolUse の検出(R9 で置換)で補う |
| `python3 script.py` の中身で env 参照を検査 | 不採用 | 正当なアプリコードを大量に誤遮断 |

### 実装
guard.py: `CRED_RULES`、`bash_rules()`(コマンド別)、`whole_cmd_rules()`(パイプ/コマンド置換/here-string/dev/tcp)、`INLINE_*` 正規表現。旧 `ENV_DUMP` は撤去。`SENSITIVE_PATH` に `/proc/*/environ` を追加。

### テスト結果
163/163 成功(新規 45 件。deny/ask/許可の三方向を各系統で確認)。途中1件不合格: `print(os.environ.get('HOME'))` を一括出力と誤判定 → 引数終端 `[,)]` を要求するよう修正。

<!-- END -->
