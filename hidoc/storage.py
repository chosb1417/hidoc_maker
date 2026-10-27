"""저장 폴더 구조, 파일 이름, 붙임 파일 복사

저장경로/기업명/
    [사업자등록증]기업명.확장자, [통장사본]기업명.확장자   (기업 공통 서류)
    YYMMDD/[품의서]기업명_YYMMDD.hwp, [견적서]기업명_YYMMDD.확장자 ...
"""

import filecmp
import re
import shutil
from pathlib import Path

ATTACH_TYPES = ["사업자등록증", "통장사본", "견적서", "거래명세서", "전자세금계산서", "계약서", "발주서", "검수확인서"]
DEFAULT_ATTACH = ["사업자등록증", "통장사본", "견적서", "거래명세서", "전자세금계산서"]
# 기업 폴더 바로 아래에 날짜 없이 저장하는 기업 공통 서류
COMPANY_DOCS = {"사업자등록증", "통장사본"}


def attach_line(kind: str, name: str, count: int) -> str:
    """('견적서', '엠에스산업', 1) -> '[견적서]엠에스산업 1부.'"""
    return f"[{kind}]{name} {count}부."


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
    if kind not in COMPANY_DOCS:
        result += f"_{date}"
    return result + Path(src).suffix


def copy_attachments(attaches: list[tuple[str, str, str]], company_dir: Path, folder: Path, date: str,
                     taken: set) -> list[str]:
    """(종류, 이름, 원본 경로) 목록을 복사하고, 기업 폴더 기준 결과 목록을 돌려줌.
    기업 공통 서류는 기업 폴더에(같은 파일이 이미 있으면 그대로 둠), 나머지는 날짜 폴더에 저장"""
    copied = []
    for kind, name, src in attaches:
        if not src:
            continue
        src = Path(src)
        if kind in COMPANY_DOCS:
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
