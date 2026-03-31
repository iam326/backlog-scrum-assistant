import os
from pathlib import Path

def load_env():
    """カレントディレクトリまたはスクリプトディレクトリの.envを読み込む"""
    env_paths = [
        Path.cwd() / ".env",
        Path(__file__).parent / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        value = value.strip().strip('"').strip("'")
                        os.environ.setdefault(key.strip(), value)
            break

load_env()

BACKLOG_SPACE_URL = os.environ.get("BACKLOG_SPACE_URL", "")
BACKLOG_API_KEY = os.environ.get("BACKLOG_API_KEY", "")
PROJECT_KEY = os.environ.get("BACKLOG_PROJECT_KEY", "")
TEAM_PREFIX = os.environ.get("TEAM_PREFIX", "")
# スプリント開始曜日 (0=月, 1=火, ..., 4=金, 5=土, 6=日)
SPRINT_START_DOW = int(os.environ.get("SPRINT_START_DOW", "0"))
