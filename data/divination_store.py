"""解卦结果的本地文件存储

文件位置：
- JSON：data/divinations_json/{divination_id}.json
- Markdown：data/divinations_md/{divination_id}.md

设计原则：
- 简单优先：一个 ID 一对 JSON+MD 文件，便于人工查看与备份
- 后续可平滑替换为 SQLite / Redis，不影响调用方
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from schema.divination import DivinationResponse

# 拆分两个独立目录
_JSON_DIR = Path(__file__).parent / "divinations_json"
_MD_DIR = Path(__file__).parent / "divinations_md"


def _ensure_json_dir() -> None:
    _JSON_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_md_dir() -> None:
    _MD_DIR.mkdir(parents=True, exist_ok=True)


def _safe_id(divination_id: str) -> str:
    # 防止路径穿越
    return "".join(c for c in divination_id if c.isalnum() or c in ("-", "_"))


def _json_path(divination_id: str) -> Path:
    return _JSON_DIR / f"{_safe_id(divination_id)}.json"


def _md_path(divination_id: str) -> Path:
    return _MD_DIR / f"{_safe_id(divination_id)}.md"


# ---------------------- JSON ----------------------

def save(divination_id: str, response: DivinationResponse) -> Path:
    """保存解卦结果到 JSON 文件。"""
    _ensure_json_dir()
    path = _json_path(divination_id)
    path.write_text(
        response.model_dump_json(indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load(divination_id: str) -> Optional[DivinationResponse]:
    """根据 ID 读取解卦结果；不存在返回 None。"""
    path = _json_path(divination_id)
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return DivinationResponse.model_validate(raw)


def exists(divination_id: str) -> bool:
    return _json_path(divination_id).exists()


# ---------------------- Markdown ----------------------

def save_markdown(divination_id: str, content: str) -> Path:
    """保存格式化 Markdown 文件。"""
    _ensure_md_dir()
    path = _md_path(divination_id)
    path.write_text(content, encoding="utf-8")
    return path


def load_markdown(divination_id: str) -> Optional[str]:
    """读取 Markdown 文件；不存在返回 None。"""
    path = _md_path(divination_id)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def markdown_exists(divination_id: str) -> bool:
    return _md_path(divination_id).exists()


def get_markdown_path(divination_id: str) -> Path:
    return _md_path(divination_id)


# ---------------------- 列表与删除 ----------------------

def list_all() -> list[str]:
    """列出所有解卦 ID（按 JSON 文件修改时间倒序）。"""
    _ensure_json_dir()
    files = sorted(
        _JSON_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [p.stem for p in files]


def delete(divination_id: str) -> bool:
    """删除解卦记录（JSON + Markdown）；返回是否真的删除了。"""
    removed = False
    for path in (_json_path(divination_id), _md_path(divination_id)):
        if path.exists():
            path.unlink()
            removed = True
    return removed
