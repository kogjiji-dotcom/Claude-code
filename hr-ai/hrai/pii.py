"""個人情報パターンの検出とマスク。氏名の完全検出は不可能なので「さん/様」付きのみ対象。"""
import re

PATTERNS = [
    ("メール", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("電話", re.compile(r"0\d{1,4}-\d{1,4}-\d{3,4}|\b0\d{9,10}\b")),
    ("郵便番号", re.compile(r"〒?\d{3}-\d{4}")),
    ("生年月日", re.compile(r"(?:19|20)\d{2}[/年.-]\d{1,2}[/月.-]\d{1,2}日?")),
    ("マイナンバー等", re.compile(r"(?<!\d)\d{12}(?!\d)")),
    ("氏名", re.compile(r"[一-龥ぁ-んァ-ヶA-Za-zＡ-Ｚ]{1,6}(?:さん|様|氏)")),
]


def find(text):
    return sorted({label for label, rx in PATTERNS if rx.search(text)})


def mask(text):
    found = find(text)
    for label, rx in PATTERNS:
        text = rx.sub(f"[{label}]", text)
    return text, found
