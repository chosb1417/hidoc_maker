"""이 PC 환경 점검 - 설정 탭의 '환경 점검'에서 씀

각 check_* 함수는 (준비됨 여부, 설명) 을 돌려줌. Claude Code 확인은 1초 안팎 걸리므로 화면에서는 스레드로 부름.
"""

import importlib
import sys
import tkinter
import winreg

# (import 이름, 용도)
REQUIRED_PACKAGES = [
    ("win32com.client", "한글 자동화"),
    ("win32clipboard", "하이웍스용 복사"),
    ("pdfplumber", "PDF 글자 읽기"),
    ("pypdfium2", "PDF 그림 변환"),
    ("PIL", "이미지 처리"),
    ("winrt.windows.media.ocr", "Windows OCR 연결"),
    ("anthropic", "Claude API"),
]


def check_python():
    version = sys.version.split()[0]
    if tkinter.TkVersion >= 9.0:
        return True, f"Python {version}, Tk {tkinter.TkVersion}"
    return False, f"Python {version}, Tk {tkinter.TkVersion} - Tk 9 이상(Python 3.14 이상) 권장. 실행.bat으로 실행하세요"


def check_hwp():
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "HWPFrame.HwpObject"))
        return True, "설치됨"
    except OSError:
        return False, "설치되어 있지 않음 - 한글 파일 저장은 안 되고 하이웍스용 복사만 가능"


def check_korean_ocr():
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine
    except ImportError:
        return False, "OCR 연결 패키지 없음 - 실행.bat으로 다시 실행하세요"
    if OcrEngine.try_create_from_language(Language("ko")) is None:
        return False, "한국어 OCR 없음 - 스캔본 견적서를 로컬 방식으로 읽을 수 없음 (Windows 설정 > 언어에서 한국어 추가)"
    return True, "사용 가능 (스캔본 견적서 로컬 읽기)"


def check_packages():
    missing = []
    for module, purpose in REQUIRED_PACKAGES:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(f"{module}({purpose})")
    if missing:
        return False, "없음: " + ", ".join(missing) + " - 실행.bat으로 다시 실행하면 설치됨"
    return True, f"{len(REQUIRED_PACKAGES)}개 모두 있음"


def check_claude_code():
    from .quote_reader import claude_code_status
    status = claude_code_status()
    if not status["exe"]:
        return False, "설치되어 있지 않음 (Claude Code 읽기 방식을 쓸 때만 필요)"
    if not status.get("loggedIn"):
        return False, "설치됨, 로그인 안 됨"
    if status.get("authMethod") != "claude.ai":
        return False, "구독이 아닌 방식(API 키 등)으로 로그인됨 - Claude Code 읽기 방식은 구독 로그인에서만 동작"
    plan = status.get("subscriptionType") or "구독"
    org = f", {status['orgName']}" if status.get("orgName") else ""
    return True, f"{status.get('email', '로그인됨')} ({plan}{org})"


CHECKS = [
    ("Python·Tk", check_python),
    ("한컴오피스 한글", check_hwp),
    ("Windows 한국어 OCR", check_korean_ocr),
    ("필요한 패키지", check_packages),
    ("Claude Code", check_claude_code),
]


def run_checks():
    """[(항목 이름, 준비됨 여부, 설명)]. 점검 중 오류가 나도 그 항목만 실패로 표시"""
    results = []
    for name, check in CHECKS:
        try:
            ok, detail = check()
        except Exception as e:  # 점검 자체의 예상 못 한 오류
            ok, detail = False, f"확인 중 오류: {type(e).__name__}: {e}"
        results.append((name, ok, detail))
    return results
