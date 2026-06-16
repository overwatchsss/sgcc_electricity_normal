#!/usr/bin/env python3
"""本地启动 Web 控制台：通过 API 只读数据库，供 dashboard HTML 展示。"""

import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from const import get_data_dir, load_project_env


def _check_deps() -> None:
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError:
        req = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "dev", "requirements-dashboard.txt"))
        print("[错误] 缺少 Web 控制台依赖（fastapi / uvicorn）。")
        print(f"       请执行：pip install -r {req}")
        print("       或在项目根目录执行：.\\dev\\run_dashboard.ps1（会自动安装）")
        sys.exit(1)


def _preflight() -> None:
    from dashboard_db import db_available, is_db_enabled

    if not is_db_enabled():
        print("[错误] 未启用数据库。请在项目根目录 .env 中设置 DB_TYPE=sqlite / mysql / postgresql")
        sys.exit(1)

    if not db_available():
        db_type = os.getenv("DB_TYPE", "sqlite").lower()
        if db_type == "sqlite":
            db_path = os.path.join(get_data_dir(), os.getenv("DB_NAME", "homeassistant.db"))
            print(f"[错误] SQLite 不可用或文件不存在：{db_path}")
            print("       请先运行数据同步（run_fetch_once.py）或确认 DB_NAME 配置正确。")
        elif db_type == "mysql":
            print("[错误] 无法连接 MySQL，请检查 .env 中 MYSQL_HOST / MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE")
        else:
            print("[错误] 无法连接 PostgreSQL，请检查 .env 中 PG_HOST / PG_USER / PG_PASSWORD / PG_DATABASE")
        sys.exit(1)

    print("[OK] 数据库连接正常")


def main() -> None:
    load_project_env()
    _check_deps()
    os.environ.setdefault("WEB_DASHBOARD", "true")
    # 本地脚本默认仅监听本机，避免误暴露；可在 .env 用 WEB_DASHBOARD_BIND 覆盖
    os.environ.setdefault("WEB_DASHBOARD_BIND", "127.0.0.1")

    _preflight()

    port = os.getenv("WEB_DASHBOARD_PORT", "8080")
    print(f"[INFO] Web 控制台：http://127.0.0.1:{port}/")
    print("[INFO] 请通过浏览器访问上述地址；不要直接双击打开 index.html（无法请求 API）。")
    print("[INFO] 按 Ctrl+C 停止服务\n")

    from web_dashboard import main as run_server

    run_server()


if __name__ == "__main__":
    main()
