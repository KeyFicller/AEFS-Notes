"""Capstone 各项目共用的函数。"""

import os
from pathlib import Path

# common.py 在 codes/capstone/ 下，再往上两级是仓库根。
REPO_ROOT = Path(__file__).resolve().parents[2]


def load_local_env(project_dir: Path | str | None = None) -> None:
    """把本地 env 文件补进环境变量。已存在的变量优先，不覆盖调用方显式传入的值。

    先读 project_dir/.env（如果给了项目目录），再读仓库里的 deskpet/local.env。
    同一变量先出现的文件生效。
    """
    paths: list[Path] = []
    if project_dir is not None:
        paths.append(Path(project_dir) / ".env")
    paths.append(REPO_ROOT / "deskpet" / "local.env")
    for path in paths:
        _apply_env_file(path)


def _apply_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
