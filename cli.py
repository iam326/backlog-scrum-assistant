#!/usr/bin/env python3
"""Backlog Scrum Assistant — スクラムマスターの朝会・リファインメント・ふりかえりを支援するCLI

Backlog APIからデータを取得・整形して出力する。
AI分析はClaude Codeのスラッシュコマンド経由で実施する。
"""

import sys
from pathlib import Path
import click
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from config import BACKLOG_SPACE_URL, BACKLOG_API_KEY, PROJECT_KEY, TEAM_PREFIX, SPRINT_START_DOW
from backlog_client import BacklogClient

JST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).parent / "data"

# 会議の種別（save-dailyコマンドで使用）
MEETING_TYPES = ["standup", "team", "refinement", "retro", "other"]


def validate_config():
    missing = []
    if not BACKLOG_SPACE_URL:
        missing.append("BACKLOG_SPACE_URL")
    if not BACKLOG_API_KEY:
        missing.append("BACKLOG_API_KEY")
    if not PROJECT_KEY:
        missing.append("BACKLOG_PROJECT_KEY")
    if missing:
        click.echo(f"エラー: 以下の環境変数が未設定です: {', '.join(missing)}", err=True)
        click.echo("  .env.example を参考に .env ファイルを作成してください。", err=True)
        sys.exit(1)


def is_team_member(name):
    """TEAM_PREFIX が設定されていればプレフィックス一致でフィルタ。未設定なら全員対象。"""
    if not TEAM_PREFIX:
        return True
    return name.startswith(TEAM_PREFIX)


def read_input(file):
    """ファイルまたはstdinからテキストを読み込む。どちらもなければエラー。"""
    if file:
        return Path(file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    click.echo("テキストをstdinから渡すか、-f でファイルを指定してください。", err=True)
    click.echo("  例: python3 cli.py <command> -f transcript.txt", err=True)
    click.echo("  例: pbpaste | python3 cli.py <command>", err=True)
    sys.exit(1)


def format_activity(a):
    """Backlogアクティビティを読みやすいテキストに整形する。"""
    user = a["createdUser"]["name"]
    activity_type = a["type"]
    content = a.get("content", {})
    key = f"{a['project']['projectKey']}-{content.get('key_id', '?')}"
    summary = content.get("summary", "")
    time = BacklogClient.format_date(a["created"])

    # type 1: 課題追加
    if activity_type == 1:
        return f"[{time}] {user} が課題を追加: [{key}] {summary}"

    # type 2: 課題更新
    if activity_type == 2:
        changes = content.get("changes", [])
        change_strs = []
        for c in changes:
            field = c.get("field_text", c.get("field", ""))
            old_val = c.get("old_value", "")
            new_val = c.get("new_value", "")
            if field in ("ステータス", "status"):
                change_strs.append(f"ステータス: {old_val} → {new_val}")
            elif field in ("担当者", "assigner"):
                change_strs.append(f"担当者: {old_val} → {new_val}")
            elif len(str(new_val)) < 100:
                change_strs.append(f"{field}を変更")
        comment_text = content.get("comment", {}).get("content", "")
        parts = [f"[{time}] {user} が [{key}] {summary} を更新"]
        if change_strs:
            parts.append(f"  変更: {', '.join(change_strs)}")
        if comment_text:
            short = comment_text[:150].replace('\n', ' ')
            parts.append(f"  コメント: {short}")
        return "\n".join(parts)

    # type 3: コメント追加
    if activity_type == 3:
        comment_text = content.get("comment", {}).get("content", "")
        short = comment_text[:200].replace('\n', ' ') if comment_text else ""
        return f"[{time}] {user} が [{key}] {summary} にコメント: {short}"

    return f"[{time}] {user}: 不明なアクティビティ (type={activity_type})"


def get_sprint_start():
    """現在のスプリント開始日を返す（SPRINT_START_DOWに基づく）。"""
    now = datetime.now(JST)
    days_since_start = (now.weekday() - SPRINT_START_DOW) % 7
    return (now - timedelta(days=days_since_start)).replace(hour=0, minute=0, second=0, microsecond=0)


def fetch_all_issues(client, project_id):
    """プロジェクトの全課題を取得する。"""
    all_issues = []
    offset = 0
    while True:
        batch = client.get_issues(project_id, count=100, offset=offset)
        if not batch:
            break
        all_issues.extend(batch)
        if len(batch) < 100:
            break
        offset += 100
    return all_issues


def format_issue_line(issue):
    """課題を1行のテキストに整形する。"""
    status = issue["status"]["name"]
    days = BacklogClient.days_since(issue.get("updated"))
    assignee = issue["assignee"]["name"] if issue.get("assignee") else "未割当"
    days_str = f"{days}日前更新" if days is not None else ""
    warn = " ⚠️" if days is not None and days >= 5 else ""
    desc = issue.get("description", "") or ""
    done = desc.count("- [x]")
    total = done + desc.count("- [ ]")
    prog = f" [{done}/{total}]" if total > 0 else ""
    return f"  [{issue['issueKey']}] {issue['summary']} — {assignee} / {status}（{days_str}）{prog}{warn}"


# ============================================================
# CLI定義
# ============================================================

@click.group()
@click.version_option(version="2.0.0", prog_name="scrum")
def cli():
    """Backlog Scrum Assistant — スクラムマスターの日常業務を支援するCLI"""
    pass


@cli.command()
def morning():
    """朝会前の準備：前営業日〜現在までのBacklog変更と、各メンバーのアクティブ課題を出力する。"""
    validate_config()
    client = BacklogClient()
    project = client.get_project(PROJECT_KEY)
    project_id = project["id"]

    now = datetime.now(JST)
    # 月曜なら金曜の9:00から、それ以外は前日の9:00から
    if now.weekday() == 0:
        since = now - timedelta(days=3)
    else:
        since = now - timedelta(days=1)
    since = since.replace(hour=9, minute=0, second=0, microsecond=0)

    click.echo(f"# 朝会準備レポート", err=True)
    click.echo(f"# 対象期間: {since.strftime('%Y-%m-%d %H:%M')} 〜 {now.strftime('%Y-%m-%d %H:%M')}", err=True)
    click.echo(f"# データ取得中...", err=True)

    activities = client.get_recent_updates(project_id, since.astimezone(timezone.utc))
    team_activities = [a for a in activities if is_team_member(a["createdUser"]["name"])]

    # アクティブ課題も取得
    active_issues = client.get_all_active_issues(project_id)
    issues_by_member = defaultdict(list)
    for i in active_issues:
        if i.get("assignee") and is_team_member(i["assignee"]["name"]):
            issues_by_member[i["assignee"]["name"]].append(i)

    # アクティビティをメンバー別に分類
    activities_by_member = defaultdict(list)
    for a in team_activities:
        activities_by_member[a["createdUser"]["name"]].append(a)

    # 全チームメンバー名を収集
    all_users = client.get_users(PROJECT_KEY)
    team_names = sorted(set(
        [u["name"] for u in all_users if is_team_member(u["name"])]
    ))

    click.echo(f"対象期間: {since.strftime('%Y-%m-%d %H:%M')} 〜 {now.strftime('%Y-%m-%d %H:%M')}")
    click.echo(f"アクティビティ: {len(team_activities)}件\n")

    for name in team_names:
        acts = activities_by_member.get(name, [])
        issues = issues_by_member.get(name, [])

        click.echo(f"## {name}（アクティビティ: {len(acts)}件 / アクティブ課題: {len(issues)}件）\n")

        if acts:
            click.echo("### 直近のアクティビティ\n")
            touched_keys = set()
            for a in acts:
                content = a.get("content", {})
                key = f"{a['project']['projectKey']}-{content.get('key_id', '?')}"
                touched_keys.add(key)
                click.echo(format_activity(a))
                click.echo()
            click.echo(f"関わった課題: {', '.join(sorted(touched_keys))}\n")
        else:
            click.echo("### 直近のアクティビティ\n")
            click.echo("  （なし）\n")

        if issues:
            # 処理中・Blockedを優先表示
            priority_statuses = ("処理中", "Blocked", "保留")
            priority = [i for i in issues if i["status"]["name"] in priority_statuses]
            if priority:
                click.echo("### 進行中・ブロック中の課題\n")
                for i in priority:
                    click.echo(format_issue_line(i))
                click.echo()

        click.echo("---\n")


@cli.command()
@click.option("--file", "-f", type=click.Path(exists=True), help="文字起こしファイルのパス")
def sync(file):
    """朝会後の差分チェック：文字起こしとBacklog上の課題状況を突き合わせる。

    文字起こしテキストとBacklogのアクティブ課題を並べて出力する。
    差分の分析はClaude Codeが行う。
    """
    validate_config()
    transcript = read_input(file)

    client = BacklogClient()
    project = client.get_project(PROJECT_KEY)

    click.echo("# 朝会同期チェック", err=True)
    click.echo("# Backlogデータ取得中...", err=True)

    active_issues = client.get_all_active_issues(project["id"])
    team_issues = [i for i in active_issues
                   if i.get("assignee") and is_team_member(i["assignee"]["name"])]

    click.echo("=== 文字起こし ===\n")
    click.echo(transcript)
    click.echo("\n=== Backlog上のアクティブ課題（チームメンバー） ===\n")

    by_member = defaultdict(list)
    for i in team_issues:
        by_member[i["assignee"]["name"]].append(i)

    for name in sorted(by_member.keys()):
        issues = by_member[name]
        click.echo(f"## {name}（{len(issues)}件）\n")
        for i in issues:
            click.echo(format_issue_line(i))
        click.echo()


@cli.command()
def weekly():
    """リファインメント準備：今スプリントのサマリ・シグナル・議題候補を出力する。"""
    validate_config()
    client = BacklogClient()
    project = client.get_project(PROJECT_KEY)

    now = datetime.now(JST)
    sprint_start = get_sprint_start()
    sprint_start_str = sprint_start.strftime("%Y-%m-%d")

    click.echo(f"# リファインメント準備レポート", err=True)
    click.echo(f"# スプリント期間: {sprint_start_str} 〜 {now.strftime('%Y-%m-%d')}", err=True)
    click.echo(f"# データ取得中...", err=True)

    all_issues = fetch_all_issues(client, project["id"])

    def team_filter(issue):
        return issue.get("assignee") and is_team_member(issue["assignee"]["name"])

    completed = [i for i in all_issues
                 if i["status"]["name"] in ("完了", "処理済み")
                 and i.get("updated", "") >= sprint_start_str
                 and team_filter(i)]
    in_progress = [i for i in all_issues
                   if i["status"]["name"] in ("処理中", "Blocked", "Marge待ち", "STG検証中", "PRDリリース待ち")
                   and team_filter(i)]
    backlog = [i for i in all_issues
               if i["status"]["name"] in ("未対応", "PBL", "SBL")
               and team_filter(i)]

    click.echo(f"スプリント期間: {sprint_start_str} 〜 {now.strftime('%Y-%m-%d')}")
    click.echo(f"完了: {len(completed)}件 / 進行中: {len(in_progress)}件 / バックログ: {len(backlog)}件\n")

    # 完了
    click.echo("## 今スプリント完了課題\n")
    if completed:
        for i in completed:
            click.echo(f"  [{i['issueKey']}] {i['summary']} — {i['assignee']['name']}")
    else:
        click.echo("  （なし）")
    click.echo()

    # 進行中
    click.echo("## 進行中の課題\n")
    if in_progress:
        for i in in_progress:
            click.echo(format_issue_line(i))
    else:
        click.echo("  （なし）")
    click.echo()

    # シグナル検出
    click.echo("## 気になるシグナル\n")
    signals = []

    blocked = [i for i in in_progress if i["status"]["name"] in ("Blocked", "保留")]
    if blocked:
        signals.append(f"Blocked/保留の課題: {len(blocked)}件")
        for i in blocked:
            signals.append(f"  [{i['issueKey']}] {i['summary']} — {i['assignee']['name']}")

    stale = [i for i in in_progress
             if i["status"]["name"] in ("STG検証中", "PRDリリース待ち", "Marge待ち")
             and (BacklogClient.days_since(i.get("updated")) or 0) >= 5]
    if stale:
        signals.append(f"\n待ち状態で5日以上経過: {len(stale)}件")
        for i in stale:
            days = BacklogClient.days_since(i.get("updated"))
            signals.append(f"  [{i['issueKey']}] {i['summary']} — {i['status']['name']}（{days}日）")

    no_estimate = [i for i in backlog if not i.get("estimatedHours")]
    if no_estimate:
        signals.append(f"\n見積もり未設定のバックログ: {len(no_estimate)}/{len(backlog)}件")

    sparse = [i for i in backlog
              if len(i.get("description", "") or "") < 50
              or (i.get("description", "") or "").count("// ") > 3]
    if sparse:
        signals.append(f"\n説明が不十分な課題: {len(sparse)}件")
        for i in sparse[:10]:
            signals.append(f"  [{i['issueKey']}] {i['summary']}")

    click.echo("\n".join(signals) if signals else "  特になし")
    click.echo()

    # リファインメント候補
    click.echo("## リファインメント議題候補\n")
    candidates = []
    for i in backlog:
        desc = i.get("description", "") or ""
        reasons = []
        if not i.get("estimatedHours"):
            reasons.append("見積もりなし")
        if len(desc) < 50:
            reasons.append("説明が短い")
        if "完了条件" not in desc and "完了基準" not in desc:
            reasons.append("完了条件なし")
        if desc.count("// ") > 3:
            reasons.append("テンプレのまま")
        if reasons:
            candidates.append((i, reasons))

    candidates.sort(key=lambda x: len(x[1]), reverse=True)
    for i, reasons in candidates[:15]:
        click.echo(f"  [{i['issueKey']}] {i['summary']}")
        click.echo(f"    理由: {', '.join(reasons)}")
    click.echo()


@cli.command()
def checkin():
    """チェックインのお題候補を出力する。

    過去に使ったお題（data/checkin/history.txt）を表示し、
    メンバープロフィールがあればそれも出力する。
    実際のお題生成はClaude Codeが行う。
    """
    checkin_dir = DATA_DIR / "checkin"
    checkin_dir.mkdir(parents=True, exist_ok=True)

    history_file = checkin_dir / "history.txt"
    past_topics = []
    if history_file.exists():
        past_topics = [line.strip() for line in history_file.read_text(encoding="utf-8").splitlines() if line.strip()]

    now = datetime.now(JST)
    weekday_ja = ["月", "火", "水", "木", "金", "土", "日"][now.weekday()]

    click.echo(f"日付: {now.strftime('%Y-%m-%d')}（{weekday_ja}）")
    click.echo(f"過去に使ったお題: {len(past_topics)}件\n")

    if past_topics:
        click.echo("## 過去のお題（直近10件）\n")
        for t in past_topics[-10:]:
            click.echo(f"  - {t}")
        click.echo()

    members_dir = DATA_DIR / "members"
    if members_dir.exists():
        profiles = [p for p in sorted(members_dir.glob("*.md")) if p.name != "_template.md"]
        if profiles:
            click.echo(f"## メンバープロフィール（{len(profiles)}名）\n")
            for p in profiles:
                content = p.read_text(encoding="utf-8")
                click.echo(f"### {p.stem}")
                # 「ひととなり」セクションを抽出
                in_section = False
                for line in content.split("\n"):
                    if line.startswith("## ひととなり"):
                        in_section = True
                        continue
                    if in_section and line.startswith("## "):
                        break
                    if in_section and line.strip() and not line.startswith("<!--"):
                        click.echo(f"  {line}")
                click.echo()


@cli.command(name="checkin-save")
@click.argument("topic")
def checkin_save(topic):
    """使ったチェックインお題を履歴に保存する。

    TOPIC: 使用したお題テキスト
    """
    checkin_dir = DATA_DIR / "checkin"
    checkin_dir.mkdir(parents=True, exist_ok=True)

    history_file = checkin_dir / "history.txt"
    now = datetime.now(JST)
    with open(history_file, "a", encoding="utf-8") as f:
        f.write(f"{now.strftime('%Y-%m-%d')} | {topic}\n")

    click.echo(f"保存しました: {topic}")


@cli.command(name="save-daily")
@click.argument("meeting_type", type=click.Choice(MEETING_TYPES))
@click.option("--file", "-f", type=click.Path(exists=True), help="文字起こしファイル")
@click.option("--date", "-d", default=None, help="日付（YYYY-MM-DD、デフォルト: 今日）")
def save_daily(meeting_type, file, date):
    """文字起こしを日付別に保存する。

    MEETING_TYPE: standup（朝会）/ team（チーム内共有）/ refinement / retro / other
    """
    text = read_input(file)

    now = datetime.now(JST)
    target_date = date or now.strftime("%Y-%m-%d")

    day_dir = DATA_DIR / "daily" / target_date
    day_dir.mkdir(parents=True, exist_ok=True)

    filepath = day_dir / f"{meeting_type}.md"
    filepath.write_text(f"# {meeting_type} — {target_date}\n\n{text}", encoding="utf-8")

    click.echo(f"保存しました: {filepath}")


@cli.command(name="search-daily")
@click.argument("keyword")
@click.option("--member", "-m", help="特定メンバーの発言のみ検索")
@click.option("--days", "-d", default=30, help="遡る日数（デフォルト: 30）")
def search_daily(keyword, member, days):
    """過去の議事録をキーワード検索する。

    KEYWORD: 検索キーワード
    """
    daily_dir = DATA_DIR / "daily"
    if not daily_dir.exists():
        click.echo("議事録データがありません。save-daily コマンドで議事録を保存してください。")
        return

    now = datetime.now(JST)
    results = []

    for day_dir in sorted(daily_dir.iterdir(), reverse=True):
        if not day_dir.is_dir():
            continue
        try:
            dir_date = datetime.strptime(day_dir.name, "%Y-%m-%d").replace(tzinfo=JST)
            if (now - dir_date).days > days:
                break
        except ValueError:
            continue

        for md_file in day_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            if keyword not in content:
                continue
            if member and member not in content:
                continue

            lines = content.split("\n")
            for i, line in enumerate(lines):
                if keyword in line:
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    results.append({
                        "date": day_dir.name,
                        "type": md_file.stem,
                        "context": "\n".join(lines[start:end]),
                    })

    click.echo(f"# 検索結果: 「{keyword}」（直近{days}日）\n")
    click.echo(f"ヒット: {len(results)}件\n")

    for r in results:
        click.echo(f"## {r['date']} / {r['type']}\n")
        click.echo(r["context"])
        click.echo("\n---\n")


if __name__ == "__main__":
    cli()
