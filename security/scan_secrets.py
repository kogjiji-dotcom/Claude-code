#!/usr/bin/env python3
"""シークレット/個人情報スキャナ (標準ライブラリのみ)。

使い方:
  python3 security/scan_secrets.py [パス ...]     # 省略時はカレント配下
  python3 security/scan_secrets.py --staged       # git のステージ済みファイルのみ
  python3 security/scan_secrets.py --no-pii ...   # メール/電話などの個人情報検出を外す
  python3 security/scan_secrets.py --json ...
終了コード: 0=検出なし / 1=検出あり / 2=使用エラー
行末に `secscan:ignore` を書くとその行は除外。検出値は必ずマスクして表示する。
"""
import os, re, sys, json, subprocess

# (name, regex, severity)  severity: high=シークレット, pii=個人情報
SECRET_PATTERNS = [
    ("AWS Access Key ID", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ("AWS Secret Key", r"(?i)aws.{0,20}(?:secret|private).{0,20}['\"=: ]+[A-Za-z0-9/+=]{40}\b"),
    ("GitHub Token", r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    ("GitHub Fine-grained PAT", r"\bgithub_pat_[A-Za-z0-9_]{50,}\b"),
    ("Anthropic API Key", r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"),
    ("OpenAI API Key", r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}\b"),
    ("Google API Key", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    ("Slack Token", r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b"),
    ("Slack Webhook", r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+"),
    ("Stripe Key", r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    ("Twilio SID/Key", r"\b(?:AC|SK)[0-9a-f]{32}\b"),
    ("SendGrid Key", r"\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}\b"),
    ("JWT", r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"),
    ("Private Key Block", r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY(?: BLOCK)?-----"),
    ("認証情報付きURL", r"\b[a-z][a-z0-9+.\-]*://[^\s/:@'\"]+:[^\s/@'\"]{3,}@[^\s'\"]+"),
    ("汎用シークレット代入",
     r"(?i)\b[\w.\-]*(?:api[_\-]?key|secret|token|passwd|password|private[_\-]?key|access[_\-]?key)[\w.\-]*\s*[:=]\s*['\"]?(?!(?:your|xxx|changeme|example|dummy|sample|none|null|true|false|\$|\{|<|%|\*))[A-Za-z0-9_\-/+=.!@#$%^&*]{12,}['\"]?"),
]
PII_PATTERNS = [
    ("メールアドレス", r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}\b"),
    ("電話番号(日本)", r"(?<![\d\-])(?:0\d{1,4}-\d{1,4}-\d{3,4}|0[789]0\d{8}|\+81[\- ]?\d{1,4}[\- ]?\d{1,4}[\- ]?\d{3,4})(?![\d\-])"),
    ("クレジットカード番号", r"(?<![\d\-])(?:\d{4}[ \-]?){3}\d{4}(?![\d\-])"),
]
SECRETS = [(n, re.compile(p), "high") for n, p in SECRET_PATTERNS]
PII = [(n, re.compile(p), "pii") for n, p in PII_PATTERNS]

EMAIL_ALLOW = re.compile(r"@(?:example\.(?:com|org|net)|test\.com|localhost|users\.noreply\.github\.com)$|^(?:noreply|no-reply)@", re.I)
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".DS_Store"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".pptx", ".xlsx", ".docx", ".zip", ".ico", ".woff", ".woff2", ".pyc", ".svg"}
# スキャナ自身・テスト用ダミーは除外
SKIP_FILES = {"scan_secrets.py", "test_security.sh"}
MAX_SIZE = 2_000_000

def luhn(s):
    d = [int(c) for c in s if c.isdigit()]
    if not 13 <= len(d) <= 19: return False
    t = 0
    for i, x in enumerate(reversed(d)):
        if i % 2: x = x * 2 - 9 if x * 2 > 9 else x * 2
        t += x
    return t % 10 == 0

def mask(v):
    v = v.strip()
    return v[:4] + "…(" + str(len(v)) + "文字)" if len(v) > 8 else "****"

def scan_text(text, pii=True):
    """[(line_no, name, severity, masked)] を返す。"""
    out = []
    pats = SECRETS + (PII if pii else [])
    for no, line in enumerate(text.splitlines(), 1):
        if "secscan:ignore" in line or len(line) > 5000: continue
        for name, rx, sev in pats:
            for m in rx.finditer(line):
                v = m.group(0)
                if name == "メールアドレス" and EMAIL_ALLOW.search(v): continue
                if name == "クレジットカード番号" and not luhn(v): continue
                out.append((no, name, sev, mask(v)))
    return out

def git_staged():
    r = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"], capture_output=True, text=True)
    return [p for p in r.stdout.splitlines() if p]

def iter_files(paths):
    for p in paths:
        if os.path.isfile(p): yield p; continue
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files: yield os.path.join(root, f)

def scan_file(path, pii=True):
    base = os.path.basename(path)
    if base in SKIP_FILES or os.path.splitext(base)[1].lower() in SKIP_EXT: return []
    try:
        if os.path.getsize(path) > MAX_SIZE: return []
        with open(path, "rb") as fh: raw = fh.read()
    except OSError: return []
    if b"\0" in raw[:4096]: return []
    return scan_text(raw.decode("utf-8", "replace"), pii)

def main(argv):
    pii, as_json, staged, paths = True, False, False, []
    for a in argv:
        if a == "--no-pii": pii = False
        elif a == "--json": as_json = True
        elif a == "--staged": staged = True
        elif a in ("-h", "--help"): print(__doc__); return 0
        elif a.startswith("-"): print("不明なオプション: " + a, file=sys.stderr); return 2
        else: paths.append(a)
    files = git_staged() if staged else list(iter_files(paths or ["."]))
    results = []
    for f in files:
        for no, name, sev, mv in scan_file(f, pii):
            results.append({"file": f, "line": no, "type": name, "severity": sev, "value": mv})
    if as_json: print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results: print(f"[{r['severity'].upper()}] {r['file']}:{r['line']}  {r['type']}  {r['value']}")
        print(f"\n{len(files)} ファイル走査 / {len(results)} 件検出")
    return 1 if results else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
