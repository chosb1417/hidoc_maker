"""저장 폴더 구조, 파일 이름, 붙임 파일 복사

저장경로/hidoc_output/기업명/      (저장 경로를 어디로 고르든 hidoc_output 폴더를 만듦: settings.output_dir)
    [사업자등록증]기업명.확장자, [통장사본]기업명.확장자   (기업 공통 서류)
    YYMMDD/[품의서]기업명_YYMMDD.hwp, [견적서]기업명_YYMMDD.확장자 ...
"""

import filecmp
import re
import shutil
from pathlib import Path

from .settings import get_setting, output_dir


def attach_types() -> list[str]:
    """붙임 종류 드롭다운 목록 (설정 attach_types)"""
    return list(get_setting("attach_types"))


def company_docs() -> set[str]:
    """기업 폴더 바로 아래에 날짜 없이 저장하는 기업 공통 서류 (설정 company_docs)"""
    return set(get_setting("company_docs"))


def company_folders(save_dir=None) -> list[str]:
    """저장 경로\\hidoc_output 안의 기업 폴더 이름들. 최근에 쓴 폴더가 앞. 폴더가 없으면 []
    (견적처 드롭다운 목록. 폴더 이름은 safe_filename 을 거친 이름이라 공백은 _ 로 되어 있음)"""
    root = output_dir(save_dir)
    try:
        folders = [p for p in root.iterdir() if p.is_dir()]
    except OSError:
        return []
    return [p.name for p in sorted(folders, key=lambda p: p.stat().st_mtime, reverse=True)]


def attach_line(kind: str, count: int, name: str = "") -> str:
    """('견적서', 1) -> '견적서 1부.', ('견적서', 1, 'AMP') -> '견적서_AMP 1부.'
    이름은 같은 종류가 여러 개라 구별해야 할 때만 넣음 (부르는 쪽에서 판단)"""
    return f"{kind}_{name} {count}부." if name else f"{kind} {count}부."


def safe_filename(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", text).strip("_")[:40] or "제목없음"


def unique_path(path: Path, taken: set) -> Path:
    """이미 있는 파일이거나 이번에 쓴 이름이면 (2), (3)... 을 붙임"""
    n, cand = 2, path
    while cand in taken or cand.exists():
        cand = path.with_name(f"{path.stem}({n}){path.suffix}")
        n += 1
    taken.add(cand)
    return cand


def copy_name(kind: str, name: str, src: str, date: str) -> str:
    """복사될 파일 이름: 기업 공통 서류는 [종류]기업명.확장자, 나머지는 [종류]기업명_YYMMDD.확장자"""
    result = f"[{kind}]{safe_filename(name)}"
    if kind not in company_docs():
        result += f"_{date}"
    return result + Path(src).suffix


def copy_attachments(attaches: list[tuple[str, str, str]], company_dir: Path, folder: Path, date: str,
                     taken: set) -> list[str]:
    """(종류, 이름, 원본 경로) 목록을 복사하고, 기업 폴더 기준 결과 목록을 돌려줌.
    기업 공통 서류는 기업 폴더에(같은 파일이 이미 있으면 그대로 둠), 나머지는 날짜 폴더에 저장"""
    copied = []
    shared = company_docs()
    for kind, name, src in attaches:
        if not src:
            continue
        src = Path(src)
        if kind in shared:
            dest = company_dir / copy_name(kind, name, src, date)
            if dest.exists() and filecmp.cmp(src, dest, shallow=False):
                copied.append(f"{dest.relative_to(company_dir)} (같은 파일이 있어 유지)")
                continue
            dest = unique_path(dest, taken)
        else:
            dest = unique_path(folder / copy_name(kind, name, src, date), taken)
        shutil.copy2(src, dest)
        copied.append(str(dest.relative_to(company_dir)))
    return copied
