# AI Company — Claude Code Workspace

## 概要

このワークスペースは AI 企業の組織構造を Claude Code のマルチエージェントで再現したものです。
CEO AI がオーケストレーターとなり、8 つの部門 AI を並列・同時に稼働させます。

## 組織構造

```
CEO AI (ceo.md)
├── 秘書 AI        @secretary   .claude/agents/secretary.md
├── 財務 AI        @finance     .claude/agents/finance.md
├── 人事 AI        @hr          .claude/agents/hr.md
├── 開発 AI        @engineering .claude/agents/engineering.md
├── マーケティング AI @marketing   .claude/agents/marketing.md
├── 法務 AI        @legal       .claude/agents/legal.md
├── 営業 AI        @sales       .claude/agents/sales.md
└── サポート AI     @support     .claude/agents/support.md
```

## エージェントの呼び出し方

### 単独呼び出し

特定の部門に作業を依頼する場合:

```
@engineering コードをレビューして
@finance 今月の予算を確認して
@legal この契約書をレビューして
```

### 並列呼び出し（同時稼働）

複数部門を同時に動かす場合は、**1 つのメッセージで複数の @メンション** を使う:

```
@engineering と @finance と @legal を同時に呼んで、
新機能リリースの技術リスク・コスト・法的リスクをそれぞれ報告させて
```

または CEO AI に委ねる:

```
新機能リリースの可否を判断して（CEO AI が自動で関係部門を並列起動）
```

### バックグラウンド実行

長時間タスクを並列で走らせる場合は Ctrl+B またはプロンプトで「バックグラウンドで実行して」と指示する。

## ファイル構成

```
Claude code/
├── CLAUDE.md              ← このファイル（組織概要・使い方）
├── ceo.md                 ← CEO AI の役割・オーケストレーション定義
├── agents/                ← 各部門の詳細ドキュメント（人間向け参照用）
│   ├── secretary.md
│   ├── finance.md
│   ├── hr.md
│   ├── engineering.md
│   ├── marketing.md
│   ├── legal.md
│   ├── sales.md
│   └── support.md
└── .claude/
    └── agents/            ← Claude Code が読み込むサブエージェント定義
        ├── secretary.md
        ├── finance.md
        ├── hr.md
        ├── engineering.md
        ├── marketing.md
        ├── legal.md
        ├── sales.md
        └── support.md
```

## 並列起動パターン集

| シナリオ | 同時起動する部門 |
|---|---|
| 新機能リリース判断 | engineering + finance + legal + marketing |
| 採用決定 | hr + finance + legal |
| 新規契約締結 | legal + finance |
| キャンペーン承認 | marketing + finance + legal |
| インシデント対応 | engineering + legal + secretary（報告） |
| 商談・値引き承認 | sales + finance + legal |
| 顧客クレーム・障害対応 | support + engineering + legal + secretary（報告） |
| 四半期レビュー | 全部門 |
