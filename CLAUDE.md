# Backlog Scrum Assistant

スクラムマスター支援CLIツール。Backlog APIデータ取得 + Claude Code AI分析。

## プロジェクト構成

- `cli.py` — メインCLI（click）。morning / sync / weekly / checkin / save-daily / search-daily コマンド
- `backlog_client.py` — Backlog REST APIクライアント
- `config.py` — .envから環境変数を読み込み
- `.claude/commands/` — スラッシュコマンド定義（7つ）
- `data/` — チェックイン履歴、日次議事録、メンバープロフィール

## スクラムイベントの流れ

### 朝会のある日
1. **朝会前** → `/scrum-checkin` でお題生成、`/scrum-morning` でBacklog活動確認
2. **朝会（顧客・他ベンダー同席）** → チェックイン → 作業報告
3. **チーム内共有（自社メンバーのみ）** → チーム内相談、顧客前では言えない話
4. **朝会+チーム内共有後** → `/scrum-daily` で文字起こし処理

### リファインメントの日
1. **リファインメント前** → `/scrum-checkin` + `/scrum-morning` + `/scrum-weekly-prep` で議題準備
2. **リファインメント（顧客・他ベンダー同席）** → チェックイン → 全体議論 → 作業報告 + 次スプリント計画
3. **リファインメント後** → `/scrum-weekly` で文字起こし処理

### ふりかえりの日
1. 通常の朝会 + チーム内共有
2. **ふりかえり前** → `/scrum-retro-prep` で議題案生成
3. **ふりかえり（自社メンバーのみ）** → KPT等（miro使用）
4. **ふりかえり後** → `/scrum-retro` で文字起こし+miroスクショ処理

## メンバープロフィール（data/members/）

スラッシュコマンドが文字起こしを処理するたびに自動更新される。以下の観点：
- ひととなり（チェックインから）
- 仕事の傾向（報告スタイル、タスクの進め方）
- コミュニケーションの特徴（議論スタイル、質問傾向）
- 顧客対応メモ（顧客との会議での傾向、チーム内共有で出た懸念）
- コンディション推移（発言量・トーンの変化）

## 議事録の種別（save-daily の MEETING_TYPE）
- `standup` — 朝会（顧客同席）
- `team` — チーム内共有（自社メンバーのみ）
- `refinement` — リファインメント
- `retro` — ふりかえり
- `other` — その他

## ステータスフロー（Backlog）
ステータス名はBacklogのプロジェクト設定に依存する。CLIの `weekly` コマンドでは「完了」「処理済み」を完了扱い、「処理中」「Blocked」等を進行中扱い、「未対応」「PBL」「SBL」をバックログ扱いとしている。プロジェクト固有のステータスがある場合は `cli.py` の分類ロジックを調整すること。

## スプリント
- SPRINT_START_DOW で開始曜日を設定（0=月〜6=日）
