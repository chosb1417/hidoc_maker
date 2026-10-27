"""폴더 위치와 이 PC 설정(settings.json)

settings.json 에 없는 값은 DEFAULTS 를 씀. 설정 탭에 보이는 값과, 화면에는 숨기고 기본값으로 두는 값이 있음.
숨긴 값도 settings.json 에 같은 키로 적으면 바뀜 (예: "company_names": ["지아이랩", "gailab"]).
"""

import json
import os
import winreg
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent  # hidoc_maker 폴더
DEFAULT_SAVE_DIR = ROOT_DIR  # 저장 경로 기본값. 실제 저장은 그 안의 hidoc_output 폴더 (output_dir)
OUTPUT_DIR_NAME = "hidoc_output"  # 저장 경로를 어디로 고르든 그 안에 항상 이 폴더를 만들어 저장
SETTINGS_PATH = ROOT_DIR / "settings.json"


def _downloads_dir() -> str:
    """Windows 에 등록된 다운로드 폴더 (사용자가 D: 등으로 옮겼을 수 있음). 못 찾으면 사용자 폴더"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
            path = Path(os.path.expandvars(winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")[0]))
        if path.is_dir():
            return str(path)
    except OSError:
        pass
    fallback = Path.home() / "Downloads"
    return str(fallback if fallback.is_dir() else Path.home())


DEFAULTS = {
    # 설정 탭에 보이는 값
    "save_dir": str(DEFAULT_SAVE_DIR),  # 출력: 저장 경로. 이 안의 hidoc_output\기업명\… 에 저장
    "quote_dir": _downloads_dir(),  # 입력: 견적서 선택 창 시작 폴더
    "attach_dir": _downloads_dir(),  # 입력: 붙임 파일 선택 창 시작 폴더
    "read_mode": "local",  # 견적서 읽기 방식: local / claude_code / claude
    "anthropic_api_key": "",
    # 화면에는 숨기는 값 (기본값으로 사용)
    "company_names": ["지아이랩", "gailab"],  # 우리 회사. 견적서에서 견적처 후보로 보지 않음
    "payment_example": "선금 50% , 잔금 50%",  # 지급방식 칸이 비어 있을 때 보이는 예시 글자
    "attach_types": ["사업자등록증", "통장사본", "견적서", "거래명세서", "전자세금계산서", "계약서", "발주서", "검수확인서"],
    "company_docs": ["사업자등록증", "통장사본"],  # 기업 폴더 바로 아래에 날짜 없이 저장하는 기업 공통 서류
}


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


def output_dir(save_dir=None) -> Path:
    """실제로 저장하는 폴더 = 저장 경로\\hidoc_output. 저장 경로가 이미 hidoc_output 폴더면 겹치지 않게 그대로"""
    base = Path(save_dir or get_setting("save_dir"))
    return base if base.name.lower() == OUTPUT_DIR_NAME else base / OUTPUT_DIR_NAME


def get_setting(key: str):
    """settings.json 값, 없거나 비어 있으면 기본값"""
    value = load_settings().get(key)
    return DEFAULTS[key] if value in (None, "", []) else value
