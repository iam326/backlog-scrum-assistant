# Backlog Scrum Assistant

スクラムマスターの日常業務を支援するCLIツール。
Backlog APIからデータを取得し、[Claude Code](https://docs.anthropic.com/en/docs/claude-code)のスラッシュコマンドと連携してAI分析を行う。

## 前提条件

- Python 3.10+
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) がインストール済み
- Backlog APIキー（Backlog > 個人設定 > API > 新しいAPIキーを発行）

## セットアップ

```bash
# 1. リポジトリをクローン
git clone <repository-url>
cd backlog-scrum-assistant

# 2. 依存パッケージのインストール
pip install requests click

# 3. 環境変数の設定
cp .env.example .env
# .env を編集してBacklog APIキー等を設定

# 4. 動作確認
python3 cli.py morning

# 5. Claude Codeをこのディレクトリで起動
claude
```

## スラッシュコマンド（Claude Code上で実行）

| コマンド | タイミング | 内容 |
|---------|----------|------|
| `/scrum-checkin` | 朝会前 | チェックインお題を5つ生成→選択→履歴保存 |
| `/scrum-morning` | 朝会前 | Backlogの直近アクティビティをメンバー別にAI要約 |
| `/scrum-daily` | 朝会+チーム内共有後 | 文字起こし→議事録保存+Backlog差分検出+メンバープロフィール更新 |
| `/scrum-weekly-prep` | リファインメント前 | 顧客向け議題案を生成（中長期スケジュール、スコープ調整等） |
| `/scrum-weekly` | リファインメント後 | 文字起こし→スプリントサマリ+議題生成+メンバープロフィール更新 |
| `/scrum-retro-prep` | ふりかえり前 | 今週の動きからKPT議題案を生成 |
| `/scrum-retro` | ふりかえり後 | 文字起こし+miroスクショ→KPT整理+メンバープロフィール更新 |

## CLIコマンド（直接実行）

```bash
# 朝会前：直近のBacklog変更をメンバー別に出力
python3 cli.py morning

# 朝会後：文字起こしとBacklog課題の突き合わせデータ出力
python3 cli.py sync -f transcript.txt

# リファインメント前：スプリントサマリ+シグナル検出+議題候補
python3 cli.py weekly

# チェックインお題の履歴管理
python3 cli.py checkin
python3 cli.py checkin-save "お題テキスト"

# 議事録の保存（種別: standup / team / refinement / retro / other）
python3 cli.py save-daily standup -f transcript.txt
python3 cli.py save-daily team -f team_transcript.txt

# 議事録のキーワード検索
python3 cli.py search-daily "キーワード"
python3 cli.py search-daily "キーワード" -m メンバー名
```

## ディレクトリ構成

```
backlog-scrum-assistant/
├── .claude/commands/     ← スラッシュコマンド定義
├── cli.py                ← メインCLI
├── backlog_client.py     ← Backlog APIクライアント
├── config.py             ← 設定読み込み（.envから）
├── .env                  ← 環境変数（gitignore対象）
├── .env.example          ← 環境変数テンプレート
└── data/
    ├── checkin/           ← チェックインお題履歴
    ├── daily/             ← 日次議事録（日付別）
    │   └── YYYY-MM-DD/
    │       ├── standup.md     ← 朝会
    │       ├── team.md        ← チーム内共有
    │       ├── refinement.md  ← リファインメント
    │       └── retro.md       ← ふりかえり
    └── members/           ← メンバープロフィール（蓄積型）
        ├── _template.md
        └── [メンバー名].md
```

## 環境変数

| 変数名 | 必須 | 説明 |
|--------|------|------|
| `BACKLOG_SPACE_URL` | Yes | BacklogスペースのURL（例: `https://your-space.backlog.com`） |
| `BACKLOG_API_KEY` | Yes | Backlog APIキー（個人設定 > API から発行） |
| `BACKLOG_PROJECT_KEY` | Yes | 対象プロジェクトキー（例: `PROJ`） |
| `TEAM_PREFIX` | No | チームメンバーフィルタ（担当者名のプレフィックス一致で絞り込み）。未設定で全メンバー表示 |
| `SPRINT_START_DOW` | No | スプリント開始曜日（0=月〜6=日、デフォルト: 0） |

## 設計思想

- **CLIはデータ取得に特化** — Backlog APIからのデータ取得・整形のみを行い、AI推論のためのAPIキーは不要
- **AI分析はClaude Codeが担当** — スラッシュコマンド経由でCLI実行→結果をAIが分析・要約・差分検出
- **メンバープロフィールが育つ** — 使い続けるほどチェックイン回答、作業傾向、コミュニケーション特性、コンディション推移が蓄積される
- **議事録が資産になる** — 日次で文字起こしを保存し、過去の発言をキーワード検索できる
