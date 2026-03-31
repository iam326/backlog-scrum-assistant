import requests
from datetime import datetime, timezone, timedelta
from config import BACKLOG_SPACE_URL, BACKLOG_API_KEY

JST = timezone(timedelta(hours=9))


class BacklogClient:
    def __init__(self):
        self.base_url = BACKLOG_SPACE_URL
        self.api_key = BACKLOG_API_KEY

    def _get(self, path, params=None):
        params = params or {}
        params["apiKey"] = self.api_key
        resp = requests.get(f"{self.base_url}/api/v2{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path, data=None):
        params = {"apiKey": self.api_key}
        resp = requests.post(f"{self.base_url}/api/v2{path}", params=params, data=data)
        resp.raise_for_status()
        return resp.json()

    def get_project(self, project_key):
        return self._get(f"/projects/{project_key}")

    def get_statuses(self, project_key):
        return self._get(f"/projects/{project_key}/statuses")

    def get_issue_types(self, project_key):
        return self._get(f"/projects/{project_key}/issueTypes")

    def get_users(self, project_key):
        return self._get(f"/projects/{project_key}/users")

    def get_issues(self, project_id, status_ids=None, assignee_ids=None,
                   count=100, offset=0, sort="updated", order="desc",
                   updated_since=None, created_since=None, keyword=None):
        params = {
            "projectId[]": project_id,
            "count": count,
            "offset": offset,
            "sort": sort,
            "order": order,
        }
        if status_ids:
            for i, sid in enumerate(status_ids):
                params[f"statusId[{i}]"] = sid
        if assignee_ids:
            for i, aid in enumerate(assignee_ids):
                params[f"assigneeId[{i}]"] = aid
        if updated_since:
            params["updatedSince"] = updated_since
        if created_since:
            params["createdSince"] = created_since
        if keyword:
            params["keyword"] = keyword
        return self._get("/issues", params)

    def get_issue(self, issue_key):
        return self._get(f"/issues/{issue_key}")

    def get_issue_comments(self, issue_key, count=5):
        return self._get(f"/issues/{issue_key}/comments", {"count": count, "order": "desc"})

    def create_issue(self, project_id, summary, issue_type_id, priority_id=3, description="", assignee_id=None):
        data = {
            "projectId": project_id,
            "summary": summary,
            "issueTypeId": issue_type_id,
            "priorityId": priority_id,
            "description": description,
        }
        if assignee_id:
            data["assigneeId"] = assignee_id
        return self._post("/issues", data)

    def get_all_active_issues(self, project_id):
        """完了以外の全課題を取得"""
        all_issues = []
        offset = 0
        while True:
            issues = self.get_issues(project_id, count=100, offset=offset)
            if not issues:
                break
            # 完了(id=4)を除外
            active = [i for i in issues if i["status"]["id"] != 4]
            all_issues.extend(active)
            if len(issues) < 100:
                break
            offset += 100
        return all_issues

    def get_project_activities(self, project_id, activity_type_ids=None, count=100, min_id=None):
        """プロジェクトのアクティビティを取得"""
        params = {"count": count}
        if activity_type_ids:
            for i, tid in enumerate(activity_type_ids):
                params[f"activityTypeId[{i}]"] = tid
        if min_id is not None:
            params["minId"] = min_id
        return self._get(f"/projects/{project_id}/activities", params)

    def get_recent_updates(self, project_id, since_dt):
        """指定日時以降のアクティビティを全取得（課題追加/更新/コメント）"""
        # type 1=課題追加, 2=課題更新, 3=コメント
        all_activities = []
        min_id = None
        since_ts = since_dt.isoformat()
        while True:
            activities = self.get_project_activities(
                project_id, activity_type_ids=[1, 2, 3], count=100, min_id=min_id
            )
            if not activities:
                break
            for a in activities:
                if a["created"] >= since_ts:
                    all_activities.append(a)
                else:
                    return all_activities
            min_id = activities[-1]["id"] - 1
            if len(activities) < 100:
                break
        return all_activities

    @staticmethod
    def days_since(date_str):
        if not date_str:
            return None
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days

    @staticmethod
    def format_date(date_str):
        if not date_str:
            return "未設定"
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.astimezone(JST).strftime("%Y-%m-%d %H:%M")
