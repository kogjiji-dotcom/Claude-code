#!/usr/bin/env python3
"""Claude Code hook: 機密ファイル/シークレット/外部送信のガード。
  guard.py pre   (PreToolUse)  : 危険操作を deny / ask
  guard.py post  (PostToolUse) : ツール出力・書込内容に機密があれば Claude に警告

フェイルモード方針 (危険度別・詳細は security/HARDENING_LOG.md ラウンド1):
  - 想定内の判定           : JSON で deny / ask を返し exit 0
  - 内部例外/タイムアウト/JSON 不正/scan_secrets 読込失敗
        -> 「縮退モード」: guard 自身に内蔵した最小検出(高信頼度キー形式 + 機密パス)だけ実施。
           ヒットすれば deny (フェイルクローズ)、ヒットしなければ許可 (フェイルオープン)。
  - guard.py 自体が無い/python3 が無い -> settings.json のラッパーで許可 (作業停止の回避)
  exit 2 を自発的に返すのは post (事後警告) のみ。pre は JSON の permissionDecision で制御する。
"""
import sys, os, re, json, time, signal

HERE = os.path.dirname(os.path.abspath(__file__))
SEC_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "security"))
sys.path.insert(0, SEC_DIR)
try:
    import scan_secrets as ss
except Exception:           # 縮退: 内蔵の最小検出に切り替える
    ss = None

MAX_STDIN = 8_000_000
MAX_SCAN = 2_000_000        # これを超える入力は「未走査」として ask (黙って通さない)
TIME_BUDGET = 8             # hook timeout(10s) より短く。超過時は縮退モードへ

# ---------------------------------------------------------------- ログ (内容は残さない)
def _log(name, msg):
    try:
        d = os.environ.get("GUARD_LOG_DIR") or SEC_DIR
        p = os.path.join(d, name)
        if os.path.exists(p) and os.path.getsize(p) > 200_000:
            with open(p) as f: tail = f.readlines()[-100:]
            with open(p, "w") as f: f.writelines(tail)
        msg = LITE_SECRETS.sub("[redacted]", msg)
        with open(p, "a") as f: f.write(time.strftime("%Y-%m-%dT%H:%M:%S ") + msg[:300].replace("\n", " ") + "\n")
    except Exception:
        pass

# ---------------------------------------------------------------- 内蔵の最小検出 (ss に依存しない)
LITE_SECRETS = re.compile(
    r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{50,}\b|"
    r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b|\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}\b|\bxox[abprs]-[A-Za-z0-9\-]{10,}\b|"
    r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY|\bAIza[0-9A-Za-z_\-]{35}\b|\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}\b")

SENSITIVE_PATH = re.compile(
    r"(?:^|/)(?:\.env(?:\.[\w.\-]+)?|\.envrc|\.dev\.vars|id_(?:rsa|dsa|ecdsa|ed25519)(?:[_.\-][\w.\-]*)?|"
    r"[._]netrc|\.npmrc|\.pypirc|\.pgpass|\.my\.cnf|\.s3cfg|\.boto|\.vault[_\-]pass\w*|\.htpasswd|\.dockercfg|"
    r"\.?credentials(?:\.json|\.db|\.tfrc\.json)?|application_default_credentials\.json|client_secrets?[\w\-]*\.json|"
    r"secrets?\.(?:json|ya?ml|toml|env)|service[-_]?account[\w\-]*\.json|kubeconfig|"
    r"terraform\.tfstate(?:\.backup)?|[\w.\-]+\.tfvars|\.git-credentials|"
    r"\.(?:\w+_)?history|\.zhistory|\.lesshst|"
    r"[\w.\-]+\.(?:pem|key|p12|p8|pfx|jks|keystore|ppk|kdbx|gpg))$"
    r"|(?:^|/)\.(?:ssh|aws|gnupg|kube|docker|azure|password-store|terraform\.d)/"
    r"|(?:^|/)\.config/(?:gcloud|gh|op)/|(?:^|/)proc/(?:\d+|self|thread-self)/environ$"
    r"|(?:^|/)Library/(?:Keychains|Cookies|Mail|Messages|Safari)/"
    r"|(?:^|/)Library/Application Support/(?:Google/Chrome|BraveSoftware|Microsoft Edge|Firefox)/", re.I)
SAFE_PATH = re.compile(r"\.(?:example|sample|template|dist)$|\.pub$", re.I)

def is_sensitive(path):
    p = path.replace("\\", "/")
    if p.startswith("file://"): p = p[7:]
    return bool(SENSITIVE_PATH.search(p) or SENSITIVE_PATH.search(p.rstrip("/") + "/")) and not SAFE_PATH.search(p)

def path_variants(path, cwd=""):
    """元の表記 / ~展開+絶対化+.. 解決 / シンボリックリンク解決後 を返す。"""
    p = path.replace("\0", "")
    if p.startswith("file://"): p = p[7:]
    out = [p]
    try:
        q = os.path.expanduser(p)
        if not os.path.isabs(q) and cwd: q = os.path.join(cwd, q)
        q = os.path.normpath(q); out.append(q)
        out.append(os.path.realpath(q))
    except Exception:
        pass
    return out

def path_sensitive(path, cwd=""):
    """機密なら該当表記を返す (symlink 先・.. ・~ も判定)。"""
    for v in path_variants(path, cwd):
        if is_sensitive(v): return v
    return None

def glob_sensitive(g):
    """Grep/Glob の glob 指定が機密ファイル名を狙っているか。"""
    g = g.lstrip("!")
    if not g: return False
    for rep in ("", "x", ".x"):
        c = re.sub(r"[*?]", rep, g)
        c = re.sub(r"\{([^{},]*)(?:,[^{}]*)*\}", r"\1", c)
        if is_sensitive("./" + c): return True
    return False

SKIP_WALK = {".git", "node_modules", ".venv", "venv", "__pycache__", ".cache"}
def find_sensitive_in_tree(root, glob_filter="", max_entries=4000, max_depth=6):
    """root 配下 (幅優先・上限あり) に機密ファイルがあれば最初の1件を返す。"""
    import fnmatch
    q, n = [(root, 0)], 0
    while q:
        cur, dep = q.pop(0)
        try: it = list(os.scandir(cur))
        except OSError: continue
        for e in it:
            n += 1
            if n > max_entries: return None
            if is_sensitive(e.path):
                if not glob_filter or fnmatch.fnmatch(e.name, glob_filter.lstrip("!").split("/")[-1]): return e.path
            try: isd = e.is_dir(follow_symlinks=False)
            except OSError: isd = False
            if isd and e.name not in SKIP_WALK and dep < max_depth: q.append((e.path, dep + 1))
    return None

def bash_sensitive_token(cmd):
    for tok in re.split(r"[\s;|&<>()='\"`]+", cmd):
        if tok and is_sensitive(tok if "/" in tok else "./" + tok): return tok
    return None

# ================================================================ Bash 構文解析 (R3)
import shlex, glob as _glob, fnmatch, codecs, shutil

PUNCT = set("();<>|&")
KEYWORDS = {"if", "then", "else", "elif", "fi", "do", "done", "while", "until", "{", "}", "!", "time", "coproc"}
WRAPPERS = {"sudo", "doas", "env", "command", "exec", "nohup", "nice", "timeout", "xargs", "stdbuf",
            "caffeinate", "builtin", "setsid", "watch", "parallel", "ionice", "chroot", "unbuffer"}
# 内容を出力しない/名前だけを扱うコマンド: 機密パス名が引数にあっても許可 (誤遮断の低減)
META_CMDS = {"ls", "stat", "test", "[", "[[", "echo", "printf", "which", "type", "realpath", "dirname",
             "basename", "readlink", "pwd", "true", "false", ":"}
GIT_META = {"check-ignore", "ls-files", "status", "commit", "tag", "branch", "log", "remote", "config", "stash"}
INTERPRETERS = {"python", "python3", "python2", "node", "nodejs", "ruby", "perl", "php", "bash", "sh", "zsh",
                "dash", "ksh", "osascript", "lua", "deno", "bun", "pwsh", "Rscript", "swift"}
INLINE_FLAGS = {"-c", "-e", "-E", "-r", "-m", "--eval", "-p", "-x", "-l"}   # -c(py/sh) -e(node/ruby/perl) -r(php)
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
CODE_SPLIT = re.compile(r"""[\s;|&<>()='"`,\[\]{}:+@]+""")

def _ansi_c(m):
    try:
        s = codecs.decode(m.group(1).encode("latin-1", "backslashreplace"), "unicode_escape")
    except Exception:
        return m.group(0)
    return "'" + s.replace("'", "'\\''") + "'"

def _prep(cmd):
    """ANSI-C クォート展開、未クォート改行→';'、バッククォート→$( )。"""
    cmd = re.sub(r"\$'((?:[^'\\]|\\.)*)'", _ansi_c, cmd)
    out, q, esc, bt = [], None, False, False
    for ch in cmd:
        if esc: out.append(ch); esc = False; continue
        if ch == "\\" and q != "'": out.append(ch); esc = True; continue
        if q:
            if ch == q: q = None
            out.append(ch); continue
        if ch in "'\"": q = ch; out.append(ch); continue
        if ch == "\n": out.append(" ; "); continue
        if ch == "`": out.append(" ) " if bt else " $( "); bt = not bt; continue
        out.append(ch)
    return "".join(out)

HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][\w\-]*)\1")
def split_heredocs(cmd):
    """ヒアドキュメント本文を分離。-> (本文を除いたコマンド, [(消費コマンド名, 本文)])"""
    lines, out, docs, i = cmd.split("\n"), [], [], 0
    while i < len(lines):
        ln = lines[i]; out.append(ln); i += 1
        for m in HEREDOC.finditer(ln):
            pre_txt = ln[:m.start()]
            mm = re.search(r"(?:^|[;&|(]\s*)(?:\w+=\S*\s+)*(?:(?:sudo|env|exec|command|nohup)\s+(?:-\S+\s+)*)*([^\s;&|()<>]+)[^;&|()]*$", pre_txt)
            name = os.path.basename(mm.group(1)) if mm else ""
            body = []
            while i < len(lines) and lines[i].strip() != m.group(2):
                body.append(lines[i]); i += 1
            i += 1
            docs.append((name, "\n".join(body)))
    return "\n".join(out), docs

def tokenize(cmd):
    try:
        lx = shlex.shlex(_prep(cmd), posix=True, punctuation_chars=True)
        lx.whitespace_split = True; lx.commenters = ""
        return list(lx)
    except ValueError:
        return [t for t in re.split(r"[\s;|&<>()]+", cmd) if t]

def build_segments(tokens):
    """-> [{'words':[...], 'redirs':[target...], 'depth':n}]"""
    segs, cur, redirs, depth, want_redir = [], [], [], 0, None
    def flush():
        nonlocal cur, redirs
        if cur or redirs: segs.append({"words": cur, "redirs": redirs, "depth": depth})
        cur, redirs = [], []
    for t in tokens:
        if t and set(t) <= PUNCT:
            if "<" in t or ">" in t:
                want_redir = t; continue
            flush(); depth = max(0, depth + t.count("(") - t.count(")")); want_redir = None; continue
        if want_redir is not None:
            if want_redir not in ("<<", "<<<", "<<-"): redirs.append(t)
            want_redir = None; continue
        cur.append(t)
    flush()
    return segs

def split_cmd(words):
    """先頭の予約語/代入/ラッパーを飛ばし (コマンド名, 引数, 代入dict) を返す。"""
    i, assigns = 0, {}
    while i < len(words):
        w = words[i]
        m = re.match(r"^([A-Za-z_]\w*)=(.*)$", w, re.S)
        if m: assigns[m.group(1)] = m.group(2); i += 1; continue
        if w in KEYWORDS: i += 1; continue
        if os.path.basename(w) in WRAPPERS:
            i += 1
            while i < len(words) and (words[i].startswith("-") or re.match(r"^\d+[smhd]?$", words[i])
                                      or re.match(r"^[A-Za-z_]\w*=", words[i])):
                m = re.match(r"^([A-Za-z_]\w*)=(.*)$", words[i], re.S)
                if m: assigns[m.group(1)] = m.group(2)
                i += 1
            continue
        break
    if i >= len(words): return "", [], assigns
    name = os.path.basename(words[i]).lower() if words[i] not in ("[", "[[") else words[i]
    args = words[i + 1:]
    if name in ("export", "declare", "local", "readonly", "typeset"):
        for a in args:
            m = re.match(r"^([A-Za-z_]\w*)=(.*)$", a, re.S)
            if m: assigns[m.group(1)] = m.group(2)
    return name, args, assigns

def subst_env(w, env):
    def rep(m):
        n = m.group(1) or m.group(2)
        return env.get(n, os.environ.get(n, "") if n in ("HOME", "PWD", "USER", "TMPDIR") else "")
    return re.sub(r"\$\{(\w+)[^}]*\}|\$(\w+)", rep, w)

def brace_expand(w, limit=64):
    res = [w]
    for _ in range(4):
        nxt, changed = [], False
        for x in res:
            m = re.search(r"\{([^{}]*,[^{}]*)\}", x)
            if m:
                changed = True
                for alt in m.group(1).split(","): nxt.append(x[:m.start()] + alt + x[m.end():])
            else: nxt.append(x)
        res = nxt[:limit]
        if not changed: break
    return res

def word_candidates(w, env, cwd):
    """1つの引数から検査対象のパス候補を作る (= / : 以降、変数、{} 、~ 、glob 展開)。"""
    base = {w}
    for sep in "=:":
        if sep in w: base.update(w.split(sep)[1:])
    out = []
    for b in base:
        for e in {subst_env(b, env), re.sub(r"\$\{?\w+\}?", "", b)}:
            for x in brace_expand(e):
                out.append(x)
                if re.search(r"[*?\[]", x):
                    try:
                        xp = os.path.expanduser(x)
                        pat = xp if os.path.isabs(xp) else os.path.join(cwd or ".", xp)
                        for g in _glob.glob(pat)[:200]: out.append(g)
                    except Exception:
                        pass
    return out

def word_sensitive(w, env, cwd):
    for c in word_candidates(w, env, cwd):
        if not c: continue
        r = path_sensitive(c if ("/" in c or c.startswith("~")) else "./" + c, cwd) or path_sensitive(c, cwd)
        if r: return r
    return None

def find_substitutions(w):
    """単語内の $(...) とバッククォートの中身を取り出す (入れ子は括弧対応)。"""
    res, i = [], 0
    while True:
        i = w.find("$(", i)
        if i < 0: break
        d, j = 0, i + 1
        while j < len(w):
            if w[j] == "(": d += 1
            elif w[j] == ")":
                d -= 1
                if d == 0: break
            j += 1
        res.append(w[i + 2:j]); i = j
    res += re.findall(r"`([^`]*)`", w)
    return res

def inline_sensitive(code, env, cwd):
    """インラインコード/文字列から機密パスらしき文字列を探す (文字列連結の解除も試す)。"""
    variants = {code,
                re.sub(r"""['"]\s*\+\s*['"]""", "", code),
                re.sub(r"""(['"])\s+(['"])""", "", code),
                re.sub(r"""['"]\s*\+\s*['"]|['"]\s*,\s*['"]|['"]\s+['"]""", "", code)}
    for v in variants:
        for piece in CODE_SPLIT.split(v):
            if piece:
                r = word_sensitive(piece, env, cwd)
                if r: return r
    return None

TREE_RECURSIVE = {"grep", "egrep", "fgrep", "zgrep"}
ARCHIVERS = {"tar", "zip", "7z", "7za", "ditto", "rsync", "cp", "scp"}

def tree_risk(name, args, cwd):
    """再帰検索/アーカイブ/コピーが機密ファイルを含むツリーを対象にしていないか。"""
    flags = " ".join(a for a in args if a.startswith("-"))
    rec = False
    if name in TREE_RECURSIVE: rec = bool(re.search(r"(?:^|\s)-\w*[rR]|--recursive|-d\s*recurse", flags))
    elif name in ("rg", "ag", "ack"): rec = bool(re.search(r"--hidden|-u|--no-ignore|--unrestricted", flags))
    elif name in ("tar", "zip", "7z", "7za", "ditto"): rec = True
    elif name in ("cp", "rsync", "scp"): rec = bool(re.search(r"(?:^|\s)-\w*[rRa]|--recursive|--archive", flags))
    if not rec: return None
    dirs = []
    for a in args:
        if a.startswith("-"): continue
        p = os.path.normpath(os.path.join(cwd or ".", os.path.expanduser(a)))
        if os.path.isdir(p): dirs.append(p)
    if not dirs and name in TREE_RECURSIVE | {"rg", "ag", "ack"}: dirs = [cwd or "."]
    for dpath in dirs:
        f = find_sensitive_in_tree(dpath)
        if f: return f
    return None


# ---------------------------------------------------------------- 資格情報の取得・環境変数・動的組み立て (R4)
SECRET_NAME = r"[A-Za-z_]*(?:SECRET|TOKEN|PASSW(?:OR)?D|API_?KEY|PRIVATE|CREDENTIAL|ACCESS_?KEY|AUTH)[A-Za-z_0-9]*"
SECRET_VAR = re.compile(r"\$\{?" + SECRET_NAME + r"\}?", re.I)
SECRET_NAME_RE = re.compile(r"^" + SECRET_NAME + r"$", re.I)
PRINTERS = {"echo", "printf", "print", "cat", "tee", "base64", "xxd", "od", "hexdump", "rev", "tr", "cut", "head", "tail"}
# (コマンド名, 引数文字列の正規表現, level, 理由)
CRED_RULES = [
    ("security", r"find-(?:generic|internet)-password|dump-keychain|export\b|find-certificate\s.*-p", "deny", "macOS キーチェーンの取得"),
    ("gh", r"^auth\s+token|^auth\s+status\s.*(?:-t|--show-token)", "deny", "GitHub トークンの表示"),
    ("gcloud", r"print-(?:access|identity)-token", "deny", "GCP アクセストークンの表示"),
    ("aws", r"^configure\s+(?:get|export-credentials)", "deny", "AWS 認証情報の表示"),
    ("gpg", r"--export-secret|--armor\s+--export-secret", "deny", "秘密鍵のエクスポート"),
    ("aws", r"^configure\s+list|^sts\s+(?:get-session-token|assume-role)|^secretsmanager\s+get-secret-value|^ssm\s+get-parameters?\s.*--with-decryption", "ask", "AWS 認証情報/シークレットの取得"),
    ("kubectl", r"get\s+secrets?|describe\s+secrets?|config\s+view\s.*--raw|get\s+.*-o\s*(?:json|yaml)\s.*secret", "ask", "Kubernetes シークレットの取得"),
    ("docker", r"^inspect|^exec\s.*\b(?:env|printenv)\b|^login|^config", "ask", "Docker の環境変数/認証情報の取得"),
    ("git", r"^credential\s+(?:fill|approve|reject)", "ask", "git 認証情報ヘルパーの利用"),
    ("npm", r"^token|^config\s+(?:get|list)", "ask", "npm トークン/設定の取得"),
    ("op", r"^(?:read|item\s+get|signin|inject|run)", "ask", "1Password からの取得"),
    ("pass", r"^(?:show|-c|ls)", "ask", "pass からの取得"),
    ("vault", r"^(?:read|kv\s+get|login)", "ask", "Vault からの取得"),
    ("az", r"account\s+get-access-token|keyvault\s+secret\s+show", "ask", "Azure トークン/シークレットの取得"),
    ("heroku", r"^config|^auth:token", "ask", "Heroku 環境変数/トークンの取得"),
    ("vercel", r"^env", "ask", "Vercel 環境変数の取得"),
    ("flyctl", r"^(?:secrets|auth\s+token)", "ask", "Fly.io シークレット/トークンの取得"),
    ("doppler", r"^secrets|^run", "ask", "Doppler シークレットの取得"),
]
DYN_PIPE_SHELL = re.compile(r"\|\s*(?:sudo\s+)?(?:(?:ba|z|da|k)?sh)\b(?:\s+-s)?\s*(?:$|[;&|)])|\|\s*(?:python[\d.]*|node|ruby|perl|php)(?:\s+-)?\s*(?:$|[;&|)])")
DYN_DECODE = re.compile(r"base64\s+(?:-d|--decode|-D)\b|xxd\s+-r|\brev\b|openssl\s+(?:enc|base64)\b.*-d\b|printf\s+['\"][^'\"]*\\(?:x[0-9a-fA-F]{2}|[0-7]{2,3})|echo\s+-e\s+['\"][^'\"]*\\(?:x[0-9a-fA-F]{2}|[0-7]{2,3})")
INLINE_OBFUSC = re.compile(r"\b(?:exec|eval|compile|__import__|b64decode|fromhex|unhexlify|fromCharCode|atob|rot13)\b|getattr\(|\bchr\(|Buffer\.from|decode\(['\"](?:hex|base64)")
INLINE_ENV_DUMP = re.compile(
    r"os\.environ\s*(?:\)|\.(?:items|keys|values|copy)\b|,|$)|\b(?:dict|print|repr|str|json\.dumps|pprint)\(\s*os\.environ\s*[,)]|"
    r"process\.env\s*(?:\)|,|$)|Object\.(?:keys|values|entries)\(\s*process\.env|JSON\.stringify\(\s*process\.env|"
    r"\bENV\.(?:to_h|each|inspect|to_a|keys|map)|\b(?:puts|p|pp)\s+ENV\b|%ENV\b|\$_ENV|\$_SERVER|\bgetenv\(\s*\)|printenv")
INLINE_SECRET_ENV = re.compile(
    r"(?:environ(?:\.get)?\s*[\[(]\s*|getenv\(\s*|process\.env(?:\.|\s*\[\s*)|ENV\[\s*|ENV\.fetch\(\s*)['\"]?" + SECRET_NAME, re.I)

def bash_rules(name, args, words, env, depth_in_subst):
    """資格情報の取得/環境変数ダンプ/動的組み立て。-> [(level, reason)]"""
    F = []
    a = " ".join(args)
    # 環境変数の一括出力
    if not name and words and os.path.basename(words[0]) == "env":
        F.append(("deny", "環境変数の一括出力は禁止 (env)"))
    if name == "printenv":
        names = [x for x in args if not x.startswith("-")]
        if not names or any(SECRET_NAME_RE.match(n) for n in names):
            F.append(("deny", "環境変数(秘密の可能性)の出力は禁止 (printenv)"))
    if name in ("export", "declare", "typeset", "readonly") and (not args or all(x in ("-p", "-x", "-px", "-xp", "-gx") for x in args)):
        F.append(("deny", f"環境変数の一括出力は禁止 ({name})"))
    if name == "set" and not args: F.append(("deny", "環境変数の一括出力は禁止 (set)"))
    if name == "compgen" and re.search(r"(?:^|\s)-[a-z]*[ev]", a): F.append(("deny", "環境変数名の列挙 (compgen)"))
    if name == "launchctl" and re.match(r"^(?:getenv|export|print|dumpstate)", a): F.append(("ask", "launchctl による環境の取得"))
    if name == "ps" and any(x in ("e", "ee", "eww", "-E", "auxe", "auxeww", "axe", "axeww") for x in args):
        F.append(("deny", "ps による他プロセスの環境変数表示"))
    # 秘密らしき変数名の展開を表示系コマンドへ渡す
    if name in PRINTERS and any(SECRET_VAR.search(x) for x in args):
        F.append(("deny", "秘密らしき環境変数の値を出力するコマンド"))
    # 資格情報取得系
    for cname, rx, lvl, why in CRED_RULES:
        if name == cname and re.search(rx, a): F.append((lvl, why))
    # インラインコード
    if name in INTERPRETERS and name not in SHELLS:
        for k, x in enumerate(args):
            if x in INLINE_FLAGS and k + 1 < len(args):
                code = args[k + 1]
                if INLINE_ENV_DUMP.search(code): F.append(("deny", "インラインコードによる環境変数の一括出力"))
                if INLINE_SECRET_ENV.search(code): F.append(("ask", "インラインコードが秘密らしき環境変数を参照 (値の表示/送信の恐れ)"))
                if INLINE_OBFUSC.search(code): F.append(("ask", "インラインコードに難読化/動的実行の兆候 (exec/eval/chr/base64 等)"))
    if name == "eval" and any("$" in x or "`" in x for x in args):
        F.append(("ask", "eval で動的に組み立てたコマンド"))
    return F

def whole_cmd_rules(cmd):
    F = []
    flat = _prep(cmd)
    if DYN_PIPE_SHELL.search(flat): F.append(("ask", "外部/変換出力をシェル・インタプリタへパイプ実行 (curl | sh, base64 -d | sh 等)"))
    for sub in find_substitutions(flat):
        if DYN_DECODE.search(sub): F.append(("ask", "コマンド置換内でのデコード/逆順/エスケープによる文字列組み立て (難読化の疑い)"))
    if re.search(r"<<<\s*[\"']?" + SECRET_VAR.pattern, flat, re.I): F.append(("deny", "秘密らしき環境変数を here-string で出力"))
    if re.search(r"/dev/(?:tcp|udp)/", flat): F.append(("deny", "/dev/tcp /dev/udp 経由の通信は禁止"))
    return F

def analyze_bash(cmd, cwd, depth=0, env=None):
    """Bash コマンドを構文解析して [(level, reason)] を返す。level: deny / ask"""
    F = []
    if depth > 3 or not cmd: return F
    env = dict(env or {})
    body, docs = split_heredocs(cmd)
    for name, text in docs:
        if os.path.basename(name) in INTERPRETERS:
            r = inline_sensitive(text, env, cwd)
            if r: F.append(("deny", f"スクリプト(ヒアドキュメント)が機密ファイルを参照: {os.path.basename(r)}"))
            F += analyze_bash(text, cwd, depth + 1, env) if os.path.basename(name) in SHELLS else []
    if depth == 0: F += whole_cmd_rules(body)
    segs = build_segments(tokenize(body))
    has_xargs = any(split_cmd(s["words"])[0] in ("xargs", "parallel") or
                    any(os.path.basename(w) in ("xargs", "parallel") for w in s["words"][:2]) for s in segs)
    # 代入を先に収集 (f=.en; cat ${f}v のような組み立て対策)
    for s in segs:
        env.update(split_cmd(s["words"])[2])
    for s in segs:
        words = s["words"]
        name, args, _ = split_cmd(words)
        writes_redirect = bool(s["redirs"])
        if name in ("test", "[", "[["): meta = True
        elif name in ("echo", "printf"): meta = not (writes_redirect or s["depth"] > 0 or has_xargs)
        elif name in META_CMDS: meta = s["depth"] == 0 and not has_xargs
        else: meta = False
        if name == "git" and args:
            sub = next((a for a in args if not a.startswith("-")), "")
            if sub in GIT_META:
                meta = True
                # -m/--message の引数は本文 (パスではない)
                keep, skip = [], False
                for a in args:
                    if skip: skip = False; continue
                    if re.match(r"^-\w*m$|^--message$", a): skip = True; continue
                    if a.startswith("--message=") or re.match(r"^-m.+", a): continue
                    keep.append(a)
                args = keep
        check = list(s["redirs"]) + ([] if meta else list(words if not name else args))
        for w in words + list(s["redirs"]):          # クォート内の $(...) も実行される
            for sub in find_substitutions(w):
                F += analyze_bash(sub, cwd, depth + 1, env)
        for w in check:
            r = word_sensitive(w, env, cwd)
            if r: F.append(("deny", f"コマンドが機密ファイルを参照: {w if len(w) < 60 else os.path.basename(r)}")); break
        # bash -c "..." / eval "..." の中身を再帰解析, python -c 等はインライン検査
        if name in SHELLS | {"eval"}:
            strs = []
            if name == "eval": strs = [" ".join(args)]
            else:
                for k, a in enumerate(args):
                    if a == "-c" or (a.startswith("-") and not a.startswith("--") and "c" in a):
                        if k + 1 < len(args): strs.append(args[k + 1])
            for st in strs: F += analyze_bash(st, cwd, depth + 1, env)
        if name in INTERPRETERS and name not in SHELLS:
            for k, a in enumerate(args):
                if a in INLINE_FLAGS and k + 1 < len(args):
                    r = inline_sensitive(args[k + 1], env, cwd)
                    if r: F.append(("deny", f"インラインコードが機密ファイルを参照: {os.path.basename(r)}"))
        F += bash_rules(name, args, words, env, s["depth"])
        tr = tree_risk(name, args, cwd)
        if tr: F.append(("ask", f"再帰検索/アーカイブ/コピーの対象に機密ファイルがあります: {os.path.basename(tr)}。対象を絞ってください。"))
    return F

def scan(text):
    """[(line, name, sev, masked)]。ss が無ければ縮退検出。"""
    if ss is not None: return ss.scan_text(text, pii=False)
    return [(0, "高信頼度キー形式", "high", "****") for _ in LITE_SECRETS.finditer(text)]

ENV_DUMP = re.compile(r"(?:^|[;&|]\s*|\$\(\s*)(?:env|printenv|export\s+-p|declare\s+-x|set)\s*(?:$|[;&|)])|/proc/[\w/]*environ|\bos\.environ\b\s*\)|\bprint\(.*os\.environ")
OUTBOUND = re.compile(r"\b(?:curl|wget|http|httpie)\b.*?(?:\s-d\b|\s--data\S*|\s-F\b|\s--form\b|\s-T\b|\s--upload-file\b|\s-X\s*(?:POST|PUT|PATCH))|\b(?:nc|ncat|netcat|scp|sftp|ftp|rsync)\b|\bgh\s+gist\s+create\b|\bgit\s+push\b|\baws\s+s3\s+(?:cp|sync|mv)\b|\bmail(?:x)?\b|\bsendmail\b")
GIT_ADD_ALL = re.compile(r"\bgit\s+add\s+(?:-A|--all|\.)(?:\s|$)|\bgit\s+commit\s+.*-a\b")

# ---------------------------------------------------------------- 出力
def out_pre(decision, reason, tool=""):
    _log("guard_audit.log", f"{decision} {tool} {reason}")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
          "permissionDecision": decision, "permissionDecisionReason": "[security-guard] " + reason}}, ensure_ascii=False))
    sys.exit(0)

# ---------------------------------------------------------------- PreToolUse
def pre(d):
    tool, ti = d.get("tool_name", ""), d.get("tool_input", {})
    if not isinstance(ti, dict): raise TypeError("tool_input is not an object")
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    cwd = d.get("cwd") or os.getcwd()
    if tool in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit") and path:
        hit = path_sensitive(path, cwd)
        if hit:
            out_pre("deny", f"機密ファイルへのアクセスを禁止: {os.path.basename(hit)}。値が必要ならユーザーに環境変数での設定を依頼。", tool)
    if tool in ("Grep", "Glob"):
        gp = ti.get("path") or ""
        if gp and path_sensitive(gp, cwd): out_pre("deny", "機密パスの検索を禁止", tool)
        gl = ti.get("glob") or ""
        if tool == "Grep" and gl and glob_sensitive(gl): out_pre("deny", "機密ファイル名を狙った検索を禁止", tool)
        if tool == "Grep" and ti.get("output_mode") in ("content", "count") and not ti.get("type"):
            root = os.path.normpath(os.path.join(cwd, os.path.expanduser(gp))) if gp else cwd
            if os.path.isdir(root):
                f = find_sensitive_in_tree(root, gl)
                if f: out_pre("ask", f"検索範囲に機密ファイルがあり内容が出力される恐れ: {os.path.basename(f)}。glob/type で除外するか対象を絞ってください。", tool)
    if tool in ("Write", "Edit", "MultiEdit"):
        text = ti.get("content") or ti.get("new_string") or "\n".join(e.get("new_string", "") for e in ti.get("edits", []))
        if len(text) > MAX_SCAN:
            out_pre("ask", "書込内容が大きすぎるためシークレット走査を実施できません。内容を確認してください。", tool)
        if not SAFE_PATH.search(path or ""):
            hits = scan(text)
            if hits:
                out_pre("deny", "書込内容にシークレットを検出: " + ", ".join(sorted({h[1] for h in hits})) + "。環境変数参照に置き換えること。", tool)
    if tool == "Bash":
        cmd = ti.get("command", "")
        found = analyze_bash(cmd, cwd)
        for lvl, why in found:
            if lvl == "deny": out_pre("deny", why, tool)
        hits = scan(cmd)
        if hits: out_pre("deny", "コマンド内にシークレットを検出: " + ", ".join(sorted({h[1] for h in hits})), tool)
        if GIT_ADD_ALL.search(cmd):
            out_pre("ask", "一括 git add/commit: 機密ファイルが含まれないか security/scan_secrets.py --staged で確認済みか?", tool)
        if OUTBOUND.search(cmd): out_pre("ask", "外部送信の可能性があるコマンド。送信内容と宛先を確認してください。", tool)
        for lvl, why in found:
            if lvl == "ask": out_pre("ask", why, tool)
    if tool == "WebFetch":
        u = ti.get("url", "") + ti.get("prompt", "")
        if scan(u): out_pre("deny", "URL/プロンプトにシークレットを検出 (外部送信防止)", tool)
    sys.exit(0)

# ---------------------------------------------------------------- PostToolUse
def post(d):
    tool, ti = d.get("tool_name", ""), d.get("tool_input", {})
    if not isinstance(ti, dict): ti = {}
    resp = d.get("tool_response", "")
    text = resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
    hits = scan(text.replace("\\n", "\n"))
    if tool in ("Write", "Edit", "MultiEdit"):
        p = ti.get("file_path", "")
        if ss is not None and p and os.path.isfile(p) and not SAFE_PATH.search(p): hits += ss.scan_file(p, pii=False)
    if hits:
        kinds = ", ".join(sorted({h[1] for h in hits}))
        _log("guard_audit.log", f"post-warn {tool} {kinds}")
        print(f"[security-guard] 警告: ツール結果/ファイルにシークレットらしき値を検出 ({kinds})。"
              "値を応答・ログ・コミットに含めないこと。必要ならユーザーに無効化(ローテーション)を促すこと。", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)

# ---------------------------------------------------------------- 縮退モード
def fallback(mode, raw, err):
    _log("guard_errors.log", f"{mode} {type(err).__name__}: {str(err)[:120]}")
    if mode == "pre":
        reason = None
        if LITE_SECRETS.search(raw):
            reason = "シークレットらしき値を検出 (guard 縮退モード)"
        else:
            for s in re.findall(r'"((?:[^"\\]|\\.)*)"', raw):
                if is_sensitive(s) or bash_sensitive_token(s):
                    reason = "機密ファイルへの参照を検出 (guard 縮退モード)"; break
        if reason: out_pre("deny", reason)
    print(f"[security-guard] hook error (縮退モードで通過): {type(err).__name__}", file=sys.stderr)
    sys.exit(0)

def _on_alarm(signum, frame): raise TimeoutError("guard time budget exceeded")

def main():
    mode = (sys.argv[1:] or ["pre"])[0]
    raw = ""
    try:
        raw = sys.stdin.read(MAX_STDIN)
        if hasattr(signal, "SIGALRM"):
            signal.signal(signal.SIGALRM, _on_alarm); signal.alarm(TIME_BUDGET)
        d = json.loads(raw)
        if not isinstance(d, dict): raise ValueError("input is not a JSON object")
        (pre if mode == "pre" else post)(d)
    except SystemExit:
        raise
    except BaseException as e:      # noqa: 例外は全て縮退モードへ
        fallback(mode, raw, e)

if __name__ == "__main__":
    main()
