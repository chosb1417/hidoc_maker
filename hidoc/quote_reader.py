"""견적서(PDF·이미지)를 읽어 견적처와 견적내역을 뽑아냄

read_quote(path, mode, api_key) 로 호출.
- "local": PDF 글자 읽기(pdfplumber), 글자가 없으면 Windows OCR(한국어) + 규칙으로 품목 찾기. 무료
- "claude": Claude API 가 문서를 직접 읽음. 인터넷과 API 키 필요, 견적서 내용이 Anthropic 으로 전송됨
- "claude_code": 이 PC에 로그인된 Claude Code(claude -p)가 읽음. 본인 Claude 구독 사용량에서 차감
결과: {"vendor": str, "target": str, "items": [{name, qty, price, vat, note}], "warnings": [str]}
"""

import base64
import glob
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .money import split_amount
from .settings import get_setting

# 읽기 방식: 화면 표시 -> read_quote 의 mode (설정 read_mode 에는 오른쪽 값이 저장됨)
READ_MODES = {"로컬 (무료)": "local", "Claude Code (구독)": "claude_code", "Claude API": "claude"}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif", ".webp"}
OCR_WIDTH = 3300  # OCR 전에 이미지 가로를 이만큼 키움 (A4 약 400dpi). 작은 글자·쉼표 인식이 좋아짐
MIN_TEXT_CHARS = 30  # PDF에서 뽑힌 글자가 이보다 적으면 스캔본으로 보고 OCR
ROW_TOLERANCE = 0.6  # 글자 높이의 이 비율 안에 있으면 같은 줄
UNITS = r"EA|ea|Ea|개|식|대|SET|set|Set|매|본|롤|박스|BOX|box|KG|kg|M|m|EA\.|ea\."
TOTAL_WORDS = ("합계", "총계", "소계", "공급가액", "부가세", "세액", "총액", "견적금액")  # 공백 뺀 줄 앞부분과 비교

CLAUDE_MODEL = "claude-opus-5-5"
CLAUDE_PROMPT = """첨부한 견적서에서 구매 품의서 작성에 필요한 내용을 뽑아 주세요.
- vendor: 견적을 낸 회사(공급자)의 상호. 견적을 받는 회사({company})는 아님. "㈜"는 "(주)"로 적음
- target: 무엇을 사는지 짧은 이름 (예: "서버용 SSD", "G.Eye-Parking H100 설계 및 제작")
- items: 견적 품목 한 줄마다 하나. 합계·소계·부가세 줄은 넣지 않음
  - name: 품명. 규격이 따로 있으면 품명 뒤에 한 칸 띄우고 붙임
  - qty: 수량 (정수)
  - price: 단가 (원, 정수)
  - vat: 단가에 부가세가 빠져 있으면 "별도", 들어 있으면 "포함", 면세·영세율이면 "없음"
  - note: 비고. 없으면 빈 문자열
- warnings: 사람이 확인해야 할 점. 할인 줄(items 에 넣지 말고 금액과 함께 적음), 소수 수량,
  흐려서 확실히 읽지 못한 글자, 견적서 합계와 품목 합이 다른 경우 등. 없으면 빈 목록"""
CLAUDE_SCHEMA = {
    "type": "object",
    "properties": {
        "vendor": {"type": "string"},
        "target": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "qty": {"type": "integer"},
                    "price": {"type": "integer"},
                    "vat": {"type": "string", "enum": ["별도", "포함", "없음"]},
                    "note": {"type": "string"},
                },
                "required": ["name", "qty", "price", "vat", "note"],
                "additionalProperties": False,
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["vendor", "target", "items", "warnings"],
    "additionalProperties": False,
}
# Claude Code 의 Read 도구가 그대로 읽는 형식. 나머지(bmp, tif)는 png 로 바꿔서 넘김
CLAUDE_CODE_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
CLAUDE_CODE_TIMEOUT = 300  # 초
# PATH 에 claude 가 없을 때 찾아볼 곳: 공식 설치 위치(방금 설치해 PATH 가 아직 안 바뀐 경우), VS Code 확장
CLAUDE_CODE_NATIVE = Path.home() / ".local" / "bin" / "claude.exe"
CLAUDE_CODE_GLOB = str(Path.home() / ".vscode" / "extensions" / "anthropic.claude-code-*" / "resources"
                       / "native-binary" / "claude.exe")
# Anthropic 공식 설치 명령 (code.claude.com/docs/en/setup). 관리자 권한 불필요
CLAUDE_CODE_INSTALL = "irm https://claude.ai/install.ps1 | iex"


class QuoteReadError(Exception):
    """사용자에게 그대로 보여줄 오류"""


class ClaudeCodeNotInstalled(QuoteReadError):
    """Claude Code 가 없음. 입력창이 설치할지 물어봄"""


class ClaudeCodeLoginRequired(QuoteReadError):
    """Claude Code 가 로그인되어 있지 않음. 입력창이 로그인 창을 띄울지 물어봄"""


def read_quote(path, mode="local", api_key=""):
    path = Path(path)
    if not path.is_file():
        raise QuoteReadError(f"파일을 찾을 수 없습니다.\n{path}")
    ext = path.suffix.lower()
    if ext != ".pdf" and ext not in IMAGE_EXTS:
        raise QuoteReadError("PDF 또는 이미지(png, jpg 등) 파일만 읽을 수 있습니다.")
    if mode == "claude":
        return _read_claude(path, api_key)
    if mode == "claude_code":
        return _read_claude_code(path)
    return _read_local(path)


# ---------------------------------------------------------------- 로컬: 글자 뽑기
def _read_local(path: Path):
    warnings = []
    if path.suffix.lower() == ".pdf":
        pages = _pdf_words(path)
        text = "".join(t for page in pages for *_, t in page)
        if len(re.sub(r"\s|\(cid:\d+\)", "", text)) < MIN_TEXT_CHARS or "(cid:" in text:
            pages = [_ocr_words(img) for img in _render_pdf(path)]
            warnings.append("스캔본이라 OCR로 읽었습니다. 숫자와 품명을 꼭 확인하세요.")
    else:
        from PIL import Image
        with Image.open(path) as img:
            pages = [_ocr_words(img)]
        warnings.append("이미지라 OCR로 읽었습니다. 숫자와 품명을 꼭 확인하세요.")
    rows = [row for page in pages for row in _group_rows(page)]
    result = _parse_rows(rows)
    result["warnings"] = warnings + result["warnings"]
    return result


def _pdf_words(path):
    """페이지별 [(x, 가운데 y, 높이, 글자)]"""
    import pdfplumber
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            pages.append([(w["x0"], (w["top"] + w["bottom"]) / 2, w["bottom"] - w["top"], w["text"])
                          for w in page.extract_words(x_tolerance=1.5)])
    return pages


def _render_pdf(path):
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(path))
    try:
        return [page.render(scale=OCR_WIDTH / page.get_width()).to_pil() for page in pdf]
    finally:
        pdf.close()


def _ocr_words(img):
    """Windows 내장 OCR(한국어)로 [(x, 가운데 y, 높이, 글자)]"""
    import asyncio
    from PIL import Image
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter

    engine = OcrEngine.try_create_from_language(Language("ko"))
    if engine is None:
        raise QuoteReadError("Windows 한국어 OCR을 쓸 수 없습니다.\n"
                             "설정 > 시간 및 언어 > 언어에서 한국어를 추가하거나, Claude API 방식을 쓰세요.")
    img = img.convert("RGBA")
    if img.width < OCR_WIDTH:
        img = img.resize((OCR_WIDTH, round(img.height * OCR_WIDTH / img.width)), Image.LANCZOS)
    limit = OcrEngine.max_image_dimension
    if max(img.size) > limit:
        ratio = limit / max(img.size)
        img = img.resize((int(img.width * ratio), int(img.height * ratio)))
    writer = DataWriter()
    writer.write_bytes(img.tobytes("raw", "BGRA"))
    bitmap = SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), BitmapPixelFormat.BGRA8,
                                                    img.width, img.height)

    async def recognize():
        return await engine.recognize_async(bitmap)

    result = asyncio.run(recognize())
    return [(w.bounding_rect.x, w.bounding_rect.y + w.bounding_rect.height / 2, w.bounding_rect.height, w.text)
            for line in result.lines for w in line.words]


def _group_rows(words):
    """높이가 비슷한 글자끼리 한 줄로 묶어 왼쪽부터 이어 붙인 문자열 목록"""
    rows = []
    for w in sorted(words, key=lambda w: w[1]):
        if rows and abs(w[1] - rows[-1][0]) <= max(w[2], rows[-1][1]) * ROW_TOLERANCE:
            rows[-1][2].append(w)
        else:
            rows.append([w[1], w[2], [w]])
    text = [" ".join(t for *_, t in sorted(ws)) for _, _, ws in rows]
    # OCR이 '1, 200' 처럼 쉼표 뒤를 띄우는 경우 붙임
    return [re.sub(r"(\d)[,.]\s+(\d{3})(?!\d)", r"\1,\2", t) for t in text]


# ---------------------------------------------------------------- 로컬: 규칙으로 해석
def _number(tok):
    """'1,200' '1.200' '₩1,200' '10EA' -> 정수, 숫자가 아니면 None"""
    tok = tok.strip("₩\\원()W")
    tok = re.sub(rf"(?<=\d)({UNITS})$", "", tok)
    # OCR이 쉼표를 t로, '0,'을 '이'로 잘못 읽는 경우
    tok = re.sub(r"(?<=\d)[tT](?=\d{3})", ",", tok)
    tok = re.sub(r"(?<=\d)이(?=\d{3})", "0,", tok)
    if re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+|\d+", tok):
        return int(re.sub(r"[,.]", "", tok))
    return None


def _company(text):
    text = text.replace("㈜", "(주)").strip(" :：.,·-")
    while text.startswith("(") and text.count("(") > text.count(")"):  # OCR이 붙인 짝 없는 괄호
        text = text[1:]
    ours = [name.lower() for name in get_setting("company_names")]  # 견적을 받는 우리 회사는 견적처가 아님
    return "" if any(name in text.lower() for name in ours) else text


def _find_vendor(rows):
    for r in rows:
        if re.search(r"귀\s*하|귀\s*중", r):  # 견적을 받는 쪽
            continue
        m = re.search(r"상\s*호(?:\s*\(\s*법인명\s*\))?\s*[:：]?\s*(.+)", r)
        if m:
            name = re.split(r"\s(?:대\s*표|성\s*명|등\s*록|사업자|주\s*소|전\s*화|TEL|Tel|업\s*태|종\s*목)", m.group(1))[0]
            if _company(name):
                return _company(name)
    pattern = r"(?:\(주\)|㈜|주식회사)\s*[가-힣A-Za-z0-9&.\-]+|[가-힣A-Za-z0-9&.\-]+\s*(?:\(주\)|㈜)"
    for r in rows:
        if re.search(r"귀\s*하|귀\s*중", r):
            continue
        for m in re.finditer(pattern, r):
            if _company(m.group(0)):
                return _company(m.group(0))
    return ""


def _is_tax(tax, supply):
    return abs(tax - supply * 0.1) <= 1


def _find_item(tokens, price_first):
    """한 줄에서 수량·단가 다음에 금액이 맞는 숫자를 찾아 품목으로. (품목, 세액구분 또는 None)

    수량 x 단가 = 금액 (뒤에 세액 칸이 있으면 '별도')
    수량 x 단가 = 공급가액 + 세액 (단가에 부가세가 들어 있으면 '포함')
    """
    nums = [(i, _number(t)) for i, t in enumerate(tokens)]
    nums = [(i, v) for i, v in nums if v is not None]
    for n in range(len(nums) - 2):
        (i, a), (_, b) = nums[n:n + 2]
        rest = [v for _, v in nums[n + 2:]]
        if not (a and b):
            continue
        if abs(a * b - rest[0]) <= 1:
            vat, used = ("별도", 2) if len(rest) > 1 and _is_tax(rest[1], rest[0]) else (None, 1)
        elif len(rest) > 1 and abs(a * b - rest[0] - rest[1]) <= 1 and _is_tax(rest[1], rest[0]):
            vat, used = "포함", 2
        else:
            continue
        qty, price = (b, a) if price_first else (a, b)
        name_toks = tokens[:i]
        if name_toks and _number(name_toks[0]) is not None:  # 맨 앞 번호(NO) 칸
            name_toks = name_toks[1:]
        name_toks = [t for t in name_toks if not re.fullmatch(UNITS, t)]
        # 금액 칸 뒤의 숫자(합계 등)를 지나 남은 글자를 비고로
        note_start = nums[-1][0] + 1 if len(nums) > n + 2 + used else nums[n + 1 + used][0] + 1
        note = " ".join(t for t in tokens[note_start:] if _number(t) is None)
        return {"name": " ".join(name_toks), "qty": qty, "price": price, "note": note}, vat
    return None, None


def _parse_rows(rows):
    warnings = []
    compact = [r.replace(" ", "") for r in rows]
    header = next((i for i, c in enumerate(compact) if "수량" in c and "단가" in c), None)
    price_first = header is not None and compact[header].index("단가") < compact[header].index("수량")
    start = header + 1 if header is not None else 0

    whole = " ".join(compact)
    if re.search(r"(부가세|부가가치세|VAT|vat)포함", whole):
        doc_vat = "포함"
    elif re.search(r"(부가세|부가가치세|VAT|vat)별도", whole):
        doc_vat = "별도"
    else:
        doc_vat = None

    items = []
    for r, c in zip(rows[start:], compact[start:]):
        if c.lstrip("0123456789.").startswith(TOTAL_WORDS):
            continue  # 합계·부가세 줄
        item, vat = _find_item(r.split(), price_first)
        if not item:
            continue
        item["vat"] = vat
        if not item["name"]:
            item["name"] = "(품목명 확인)"
            warnings.append("품목명을 읽지 못한 줄이 있습니다.")
        items.append(item)

    if any(it["vat"] is None for it in items):
        if doc_vat is None:
            warnings.append("부가세 포함 여부를 찾지 못해 '별도'로 넣었습니다.")
        for it in items:
            it["vat"] = it["vat"] or doc_vat or "별도"

    # 견적서에 적힌 합계와 비교
    if items:
        amounts = [split_amount(it["qty"], it["price"], it["vat"]) for it in items]
        supply, total = sum(s for s, _ in amounts), sum(s + t for s, t in amounts)
        quoted = {v for r, c in zip(rows, compact) if any(w in c for w in ("합계", "총액", "견적금액", "총계"))
                  for v in (_number(t) for t in r.split()) if v and v >= 1000}
        if quoted and not quoted & {supply, total}:
            warnings.append(f"견적서 합계({max(quoted):,}원)와 읽은 품목의 합계({total:,}원)가 다릅니다. "
                            "빠진 품목이나 잘못 읽은 숫자가 있는지 확인하세요.")

    return {"vendor": _find_vendor(rows), "target": "", "items": items, "warnings": warnings}


# ---------------------------------------------------------------- Claude API
def _read_claude(path: Path, api_key: str):
    import anthropic

    if not (api_key or os.environ.get("ANTHROPIC_API_KEY")):
        raise QuoteReadError("Claude API 키가 없습니다. [API 키…] 버튼으로 먼저 넣어 주세요.")
    if path.suffix.lower() == ".pdf":
        block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                 "data": base64.standard_b64encode(path.read_bytes()).decode()}}
    else:
        from PIL import Image
        buf = io.BytesIO()
        with Image.open(path) as img:
            img.convert("RGB").save(buf, "JPEG", quality=90)
        block = {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                              "data": base64.standard_b64encode(buf.getvalue()).decode()}}

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    try:
        response = client.beta.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # 안전 필터가 거절하면 서버가 다른 모델로 다시 시도
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": CLAUDE_SCHEMA}},
            messages=[{"role": "user", "content": [block, {"type": "text", "text": _claude_prompt()}]}],
        )
    except anthropic.AuthenticationError:
        raise QuoteReadError("Claude API 키가 올바르지 않습니다. [API 키…]로 다시 넣어 주세요.")
    except anthropic.PermissionDeniedError:
        raise QuoteReadError("이 API 키로는 사용할 수 없습니다. 키 권한이나 결제 상태를 확인하세요.")
    except anthropic.RateLimitError:
        raise QuoteReadError("요청이 많아 잠시 막혔습니다. 1분 뒤에 다시 시도하세요.")
    except anthropic.BadRequestError as e:
        raise QuoteReadError(f"Claude API가 요청을 거부했습니다.\n{e.message}")
    except anthropic.APIStatusError as e:
        raise QuoteReadError(f"Claude API 오류 ({e.status_code}). 잠시 뒤 다시 시도하세요.\n{e.message}")
    except anthropic.APIConnectionError:
        raise QuoteReadError("Claude API에 연결할 수 없습니다. 인터넷 연결을 확인하세요.")

    if response.stop_reason == "refusal":
        raise QuoteReadError("Claude가 이 문서 읽기를 거절했습니다. 로컬 방식으로 읽어 보세요.")
    if response.stop_reason == "max_tokens":
        raise QuoteReadError("견적서가 너무 길어 끝까지 읽지 못했습니다.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except ValueError:
        raise QuoteReadError("Claude API 응답을 해석하지 못했습니다. 다시 시도하세요.")
    return _from_claude(data)


def _claude_prompt():
    """견적을 받는 우리 회사 이름(설정 company_names)을 넣은 안내문"""
    return CLAUDE_PROMPT.format(company=", ".join(get_setting("company_names")))


def _from_claude(data):
    """CLAUDE_SCHEMA 형식 결과를 입력창용으로 정리"""
    items = [{"name": it["name"].strip(), "qty": max(1, int(it["qty"])), "price": max(0, int(it["price"])),
              "vat": it["vat"], "note": it["note"].strip()} for it in data["items"]]
    return {"vendor": _company(data["vendor"]), "target": data["target"].strip(),
            "items": items, "warnings": data["warnings"]}


# ---------------------------------------------------------------- Claude Code (구독)
def find_claude_code():
    """claude 실행 파일 경로. PATH 에 없으면 VS Code 확장 안에서 가장 최근 것. 없으면 None"""
    found = shutil.which("claude")
    if found:
        return found
    if CLAUDE_CODE_NATIVE.is_file():
        return str(CLAUDE_CODE_NATIVE)
    candidates = glob.glob(CLAUDE_CODE_GLOB)
    return max(candidates, key=os.path.getmtime) if candidates else None


def _run_claude_code(args, cwd=None, timeout=CLAUDE_CODE_TIMEOUT):
    # API 키 환경변수가 있으면 구독 대신 API 요금으로 결제되므로 빼고 실행
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    return subprocess.run(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))  # 검은 창이 뜨지 않게


def start_claude_code_install():
    """공식 설치 명령을 새 PowerShell 창에서 실행. 창이 닫히면 끝나는 Popen 을 돌려줌"""
    script = ("Write-Host 'Claude Code를 설치합니다. 1~2분 걸리고, 그동안 화면에 진행 표시가 없습니다...'; "
              f"{CLAUDE_CODE_INSTALL}; "
              "Write-Host ''; Read-Host '끝났습니다. Enter 키를 누르면 창이 닫히고 다음 단계로 넘어갑니다'")
    return subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                            creationflags=subprocess.CREATE_NEW_CONSOLE)


def start_claude_code_login():
    """Claude 구독 로그인 창(콘솔 + 브라우저)을 띄움. 창이 닫히면 끝나는 Popen 을 돌려줌"""
    exe = find_claude_code()
    if not exe:
        raise QuoteReadError("Claude Code를 찾을 수 없습니다.")
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    # 로그인 결과를 볼 수 있도록 끝난 뒤 키를 누를 때까지 창을 남겨 둠
    # /s: 바깥 따옴표만 벗겨서 경로에 공백이 있어도 그대로 전달
    return subprocess.Popen(f'cmd /s /c ""{exe}" auth login --claudeai & pause"', env=env,
                            creationflags=subprocess.CREATE_NEW_CONSOLE)


def claude_code_status():
    """Claude Code 설치·로그인 상태. {"exe": 경로 또는 None, "loggedIn", "authMethod", "subscriptionType", "email", ...}
    입력창(견적서 읽기 전)과 설정 탭(환경 점검)에서 함께 씀. 1초 안팎 걸림"""
    exe = find_claude_code()
    if not exe:
        return {"exe": None, "loggedIn": False}
    try:
        status = json.loads(_run_claude_code([exe, "auth", "status"], timeout=30).stdout or "{}")
    except (ValueError, OSError, subprocess.TimeoutExpired):
        status = {}
    return {"loggedIn": False, **status, "exe": exe}


def _read_claude_code(path: Path):
    status = claude_code_status()
    exe = status["exe"]
    if not exe:
        raise ClaudeCodeNotInstalled("이 PC에 Claude Code가 설치되어 있지 않습니다.\n"
                                     "설치 없이 쓰려면 읽기 방식을 '로컬 (무료)'로 바꾸세요.")
    # 구독 로그인인지 확인 (API 키로 로그인돼 있으면 API 요금이 나가므로 막음)
    if not status.get("loggedIn"):
        raise ClaudeCodeLoginRequired("Claude Code에 로그인되어 있지 않습니다.\n"
                                      "로그인하지 않고 쓰려면 읽기 방식을 '로컬 (무료)'로 바꾸세요.")
    if status.get("authMethod") != "claude.ai":
        raise QuoteReadError("Claude Code가 Claude 구독이 아닌 방식(API 키 등)으로 로그인되어 있습니다.\n"
                             "API 요금이 나가지 않도록 이 방식은 구독 로그인에서만 씁니다.")

    with tempfile.TemporaryDirectory(prefix="hidoc_") as tmp:
        if path.suffix.lower() not in CLAUDE_CODE_EXTS:
            from PIL import Image
            converted = Path(tmp) / "quote.png"
            with Image.open(path) as img:
                img.save(converted)
            path = converted
        prompt = f"Read 도구로 이 견적서 파일을 읽으세요: {path}\n\n{_claude_prompt()}"
        args = [exe, "-p", prompt,
                "--output-format", "json",
                "--json-schema", json.dumps(CLAUDE_SCHEMA, ensure_ascii=False),
                "--tools", "Read", "--allowedTools", "Read",  # 파일 읽기만 허용
                "--permission-mode", "dontAsk",
                "--no-session-persistence", "--strict-mcp-config",
                "--max-turns", "5", "--effort", "medium"]
        try:
            result = _run_claude_code(args, cwd=path.parent)
        except subprocess.TimeoutExpired:
            raise QuoteReadError(f"Claude Code가 {CLAUDE_CODE_TIMEOUT // 60}분 안에 끝나지 않았습니다. 다시 시도하세요.")

    try:
        out = json.loads(result.stdout)
    except ValueError:
        raise QuoteReadError(f"Claude Code 실행에 실패했습니다.\n{(result.stderr or result.stdout)[-500:]}")
    if out.get("is_error") or not out.get("structured_output"):
        msg = out.get("result") or out.get("subtype") or "알 수 없는 오류"
        if "limit" in str(msg).lower():
            msg = f"Claude 구독 사용 한도에 도달했습니다. 잠시 뒤에 다시 시도하세요.\n{msg}"
        raise QuoteReadError(f"Claude Code가 견적서를 읽지 못했습니다.\n{str(msg)[:500]}")
    return _from_claude(out["structured_output"])
