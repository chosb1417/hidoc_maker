"""폴더 위치와 이 PC 설정(settings.json: 저장 경로, 견적서 읽기 방식, Claude API 키)"""

import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent  # hidoc_maker 폴더
DEFAULT_SAVE_DIR = ROOT_DIR / "output"
SETTINGS_PATH = ROOT_DIR / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(data: dict):
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def update_settings(**values):
    """기존 설정은 두고 주어진 값만 바꿔 저장"""
    save_settings({**load_settings(), **values})
