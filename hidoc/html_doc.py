"""하이웍스 등 웹 편집기에 붙여넣을 품의서 HTML - 클립보드(HTML Format)에 넣음

양식은 hidoc/templates/hiworks/ 의 HTML 조각. 사용자가 준 하이웍스 원본(hidoc/templates/레퍼런스.html,
비교용이라 절대 수정하지 않음)을 그대로 복사하고 바뀌는 부분만 {{빈칸}}으로 바꾼 것이라,
여기서는 빈칸에 글자만 채우고 양식(글꼴·크기·빈 줄·들여쓰기)은 건드리지 않음.
- page.html: 전체. {{title}} {{target}} {{vendor}} {{amount}} {{rows}} {{sum_*}} {{items_4}} {{attach}}
- row.html: 견적내역 한 줄 (레퍼런스의 둘째 품목 줄)
- item_line.html: 4번부터 항목 한 줄 (지급방식·구매처)
- attach_first.html / attach_next.html: 붙임 첫 줄('붙 임 :' 포함) / 둘째 줄부터
copy_html(doc, items) 로 호출. 복사할 때마다 프로그램 폴더의 hidoc_output/preview.html 에도 저장 (Live Server 로 미리보기).
"""

from html import escape
from pathlib import Path

import win32clipboard

from .money import eul_reul, payment_lines, split_amount, won_to_korean
from .settings import DEFAULT_SAVE_DIR, output_dir

PREVIEW_PATH = output_dir(DEFAULT_SAVE_DIR) / "preview.html"  # 개발용 미리보기라 저장 경로 설정과 상관없이 프로그램 폴더
TEMPLATE_DIR = Path(__file__).parent / "templates" / "hiworks"


def _template(name):
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def _fill(template, **values):
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def build_html(doc: dict, items: list[dict]) -> str:
    amounts = [split_amount(it["qty"], it["price"], it["vat"]) for it in items]
    total = sum(s + t for s, t in amounts)
    vat_note = " VAT포함" if doc.get("vat_note") else ""

    row = _template("row.html")
    rows = []
    for i, (it, (supply, tax)) in enumerate(zip(items, amounts), 1):
        note = f'<span style="font-size: 14px;">{escape(it["note"])}</span>' if it["note"] else "<br>"
        rows.append(_fill(row, no=str(i), name=escape(it["name"]), qty=f"{it['qty']:,}", price=f"{it['price']:,}",
                          supply=f"{supply:,}", tax=f"{tax:,}", total=f"{supply + tax:,}", note=note))

    # 4번부터 항목(지급방식·구매처): 입력하지 않았으면 빠짐
    line = _template("item_line.html")
    items_4 = "\n".join(_fill(line, line=escape(ln)) for ln in
                        payment_lines(doc["payment"], doc["payment_detail"], doc.get("shop", "")))

    attach = list(doc["attach"])
    if attach and not attach[-1].endswith("끝."):
        attach[-1] += " 끝."
    first, nxt = _template("attach_first.html"), _template("attach_next.html")
    attach_html = "\n".join(_fill(first if i == 0 else nxt, line=escape(ln)) for i, ln in enumerate(attach))

    return _fill(_template("page.html"),
                 title=escape(doc["title"]),
                 target=escape(f"{doc['target']}{eul_reul(doc['target'])}"),
                 vendor=escape(doc["vendor"]),
                 amount=f"금{total:,}원(금{won_to_korean(total)}원){vat_note}",
                 rows="\n".join(rows),
                 sum_price=f"{sum(it['price'] for it in items):,}",
                 sum_supply=f"{sum(s for s, _ in amounts):,}",
                 sum_tax=f"{sum(t for _, t in amounts):,}",
                 sum_total=f"{total:,}",
                 items_4=items_4,
                 attach=attach_html)


def _cf_html(fragment: str) -> bytes:
    """클립보드 HTML Format: 앞머리에 바이트 위치를 적어야 함"""
    head = "Version:0.9\r\nStartHTML:{:010d}\r\nEndHTML:{:010d}\r\nStartFragment:{:010d}\r\nEndFragment:{:010d}\r\n"
    pre = '<html><head><meta charset="utf-8"></head><body><!--StartFragment-->'
    post = "<!--EndFragment--></body></html>"
    start_html = len(head.format(0, 0, 0, 0).encode())
    start_frag = start_html + len(pre.encode())
    end_frag = start_frag + len(fragment.encode())
    end_html = end_frag + len(post.encode())
    return (head.format(start_html, end_html, start_frag, end_frag) + pre + fragment + post).encode()


def save_preview(fragment: str):
    """브라우저 미리보기용. 하이웍스 작성 화면과 같은 폭의 흰 종이에 그림
    (양식의 문서 여백 위 18px·좌우 23px, 제목 표 931.5px 기준. 견적내역 표가 910px 고정이라 이보다 좁으면 넘침)"""
    page = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>품의서 미리보기</title>'
            '<style>body{background:#e5e5e5;margin:0;padding:24px;}'
            '.paper{background:#fff;width:932px;margin:0 auto;padding:18px 23px;box-shadow:0 1px 4px #0003;}</style>'
            f'</head><body><div class="paper">\n{fragment}\n</div></body></html>')
    PREVIEW_PATH.parent.mkdir(exist_ok=True)
    PREVIEW_PATH.write_text(page, encoding="utf-8")


def copy_html(doc: dict, items: list[dict]):
    html = build_html(doc, items)
    save_preview(html)
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.RegisterClipboardFormat("HTML Format"), _cf_html(html))
        # HTML 편집(소스) 모드에 붙여넣을 수 있도록 코드도 일반 텍스트로 넣음
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, html)
    finally:
        win32clipboard.CloseClipboard()
    return html
