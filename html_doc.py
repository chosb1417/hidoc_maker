"""하이웍스 등 웹 편집기에 붙여넣을 품의서 HTML - 클립보드(HTML Format)에 넣음

한글에서 복사하면 웹 편집기에서 정렬이 풀리므로, HTML을 직접 만들어 복사.
하이웍스는 글자 크기·굵기가 지정되지 않은 글자(공백 포함)에 첫 줄 서식(큰 글씨)을 씌우므로
- 모든 글자와 공백을 크기·굵기를 지정한 span 안에 넣음
- 표 너비는 % 와 width 속성, 굵게는 <b>, 정렬은 align 속성으로도 함께 지정
- 테두리 없는 칸(제목, 붙임)은 표 대신 문단으로 작성
copy_html(doc, items) 로 호출.
"""

from html import escape

import win32clipboard

FONT = "font-family:'맑은 고딕','Malgun Gothic',sans-serif;"
BASE_PX = 16
NB = "&nbsp;"
FIT = "fit"  # 표 칸 너비: 내용에 딱 맞게
INDENT_NB = 8  # 1단계 들여쓰기 = 공백 8칸 (약 40px). margin 보다 하이웍스에서 확실히 유지됨


def _text(s, size=BASE_PX, bold=False):
    s = escape(s).replace("  ", NB * 2) or NB
    s = f'<span style="{FONT}font-size:{size}px;font-weight:{"bold" if bold else "normal"};">{s}</span>'
    return f"<b>{s}</b>" if bold else s


def _sp(n):
    """공백 n칸. span 밖의 공백은 하이웍스가 첫 줄 서식(큰 글씨)을 씌우므로 반드시 span 안에"""
    return f'<span style="{FONT}font-size:{BASE_PX}px;font-weight:normal;">{NB * n}</span>'


def _p(s="", align="left", size=BASE_PX, bold=False, raw=None, indent=False):
    """한 줄 문단. raw 를 주면 이미 만든 HTML 을 그대로 넣음. indent 면 1단계 들여쓰기"""
    body = raw if raw is not None else _text(s, size, bold)
    if indent:
        body = _sp(INDENT_NB) + body
    return f'<p align="{align}" style="margin:0;text-align:{align};">{body}</p>'


def _td(s, width=None, align="center", bold=False, size=12, colspan=1):
    """width: 표 너비에 대한 %, FIT 이면 내용에 딱 맞게, None 이면 남는 폭을 차지"""
    span = f' colspan="{colspan}"' if colspan > 1 else ""
    if width == FIT:
        attr, style = ' width="1%" nowrap', "width:1%;white-space:nowrap;padding:3px 8px;"
    elif width:
        attr, style = f' width="{width:g}%"', f"width:{width:g}%;padding:3px 4px;"
    else:
        attr, style = "", "padding:3px 4px;"
    return (f'<td align="{align}" valign="middle"{attr}{span} '
            f'style="{style}text-align:{align};border:1px solid #000;">'
            f"{_text(s, size, bold)}</td>")


def build_html(doc: dict, items: list[dict]) -> str:
    from purchase_request import split_amount, won_to_korean, eul_reul

    amounts = [split_amount(it["qty"], it["price"], it["vat"]) for it in items]
    total = sum(s + t for s, t in amounts)
    vat_note = " VAT포함" if doc.get("vat_note") else ""
    # NO, 품목, 수량, 단가, 공급가액, 세액, 합계, 비고 - 품목이 남는 폭을 모두 차지, 금액 칸은 숫자에 딱 맞게
    widths = [5, None, 6, FIT, FIT, FIT, FIT, 8]
    out = []

    out.append(_p("품 의 서", "center", 27, True))
    out += [_p(), _p()]

    # 제목: 표 대신 문단 + 밑줄
    out.append(_p(raw=_text("제    목", bold=True) + _sp(6) + _text(f"[품의서]  {doc['title']}")))
    out.append('<hr size="1" noshade color="#000000" style="border:0;border-top:1px solid #000;margin:4px 0;">')
    out += [_p(), _p()]

    out.append(_p(f"{doc['target']}{eul_reul(doc['target'])} 아래와 같이 구매하고자 하오니 재가하여 주시기 바랍니다."))
    out += [_p(), _p(), _p()]
    out.append(_p("-   아      래   -", "center"))
    out += [_p(), _p()]

    out.append(_p(f"1. 견 적 처 : {doc['vendor']}", indent=True))
    out.append(_p(f"2. 견적 금액 : 금{total:,}원(금{won_to_korean(total)}원){vat_note}", indent=True))
    out.append(_p("3. 견적내역", indent=True))

    rows = ["".join(_td(h, w, bold=True) for h, w in zip(
        ["NO", "품목", "수량", "단가", "공급가액", "세 액", "합 계", "비고"], widths))]
    for i, (it, (supply, tax)) in enumerate(zip(items, amounts), 1):
        nums = (it["price"], supply, tax, supply + tax)
        rows.append(_td(str(i), widths[0]) + _td(it["name"], widths[1]) + _td(f"{it['qty']:,}", widths[2])
                    + "".join(_td(f"{v:,}", w, "right") for v, w in zip(nums, widths[3:7]))
                    + _td(it["note"], widths[7]))
    sums = [sum(it["price"] for it in items), sum(s for s, _ in amounts), sum(t for _, t in amounts), total]
    rows.append(_td("총계", colspan=3)
                + "".join(_td(f"{v:,}", w, "right", True, 13) for v, w in zip(sums, widths[3:7]))
                + _td("", widths[7]))
    # 표는 페이지 폭에 가득이므로 단위는 오른쪽 정렬 문단으로 (하이웍스는 caption 정렬을 무시함)
    out.append(_p("(단위 : 개, 원)", "right", 10))
    out.append(f'<table width="100%" border="1" cellspacing="0" cellpadding="3" '
               f'style="width:100%;border-collapse:collapse;">'
               + "".join(f"<tr>{r}</tr>" for r in rows) + "</table>")
    out.append(_p())

    out.append(_p(f"4. 지급방식 : {doc['payment']}", indent=True))
    for ln in doc["payment_detail"]:
        out.append(_p(ln if ln.startswith("-") else f"- {ln}", indent=True))
    out += [_p(), _p()]

    # 붙임: 표 대신 문단. 둘째 줄부터는 '붙    임 :' 너비만큼 공백
    attach = doc["attach"]
    for i, ln in enumerate(attach):
        if i == len(attach) - 1 and not ln.endswith("끝."):
            ln += " 끝."
        label = _text("붙    임 :") + _sp(4) if i == 0 else _sp(16)
        out.append(_p(raw=label + _text(ln), indent=True))

    return "\n".join(out)


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


def copy_html(doc: dict, items: list[dict]):
    html = build_html(doc, items)
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.RegisterClipboardFormat("HTML Format"), _cf_html(html))
        # HTML 편집(소스) 모드에 붙여넣을 수 있도록 코드도 일반 텍스트로 넣음
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, html)
    finally:
        win32clipboard.CloseClipboard()
    return html
