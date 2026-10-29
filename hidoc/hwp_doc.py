"""한글(HWP) 품의서 생성 - 한컴오피스 자동화(COM) 사용

build_hwp(doc, items, path) 로 호출. 한글이 설치된 PC에서만 동작.
"""

import win32com.client as win32

from .money import eul_reul, payment_lines, split_amount, won_to_korean

FONT = "맑은 고딕"
BASE_PT = 12  # 기본 글자 크기 (16px = 12pt)
GAP_PT = 10  # 빈 줄 높이. 붙임 표가 다음 쪽으로 밀리지 않도록 기본 크기보다 작게
FONT_KEYS = ["Hangul", "Latin", "Hanja", "Japanese", "Other", "Symbol", "User"]
ALIGN = {"justify": 0, "left": 1, "right": 2, "center": 3}

# 견적내역 표 열 너비(mm): NO, 품목, 수량, 단가, 공급가액, 세액, 합계, 비고
COL_MM = [9, 45, 10, 20, 20, 18, 21, 12]
TEXT_WIDTH_MM = 170  # A4 210mm - 좌우 여백 20mm씩 (page_setup)
INDENT_MM = 10  # 1단계 들여쓰기 (1~4번 항목, 붙임)
TABLE_TEXT_SHIFT_MM = 4  # 표 안 글자가 셀·바깥 여백만큼 오른쪽으로 밀리는 거리 (PDF에서 잰 값)
CELL_MARGIN_MM = 1.0  # 셀 안쪽 좌우 여백
CELL_PAD_MM = CELL_MARGIN_MM * 2


class HwpWriter:
    def __init__(self):
        self.hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
        self.hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        self.hwp.XHwpWindows.Item(0).Visible = False
        self.act = self.hwp.HAction
        self.ps = self.hwp.HParameterSet

    def mm(self, v):
        return self.hwp.MiliToHwpUnit(v)

    def run(self, name):
        self.act.Run(name)

    # ---------------------------------------------- 글자 / 문단
    def char(self, size=10, bold=False):
        p = self.ps.HCharShape
        self.act.GetDefault("CharShape", p.HSet)
        p.Height = int(size * 100)
        p.Bold = int(bold)
        for k in FONT_KEYS:
            setattr(p, f"FaceName{k}", FONT)
            setattr(p, f"FontType{k}", 1)
        self.act.Execute("CharShape", p.HSet)

    def para(self, align="left", left_mm=0.0, spacing=160, right_mm=0.0):
        p = self.ps.HParaShape
        self.act.GetDefault("ParagraphShape", p.HSet)
        p.AlignType = ALIGN[align]
        p.LeftMargin = self.mm(left_mm) * 2  # 문단 여백은 HWPUNIT의 1/2 단위
        p.RightMargin = self.mm(right_mm) * 2
        p.Indentation = 0
        p.LineSpacingType = 0
        p.LineSpacing = spacing
        p.PrevSpacing = 0
        p.NextSpacing = 0
        self.act.Execute("ParagraphShape", p.HSet)

    def text(self, s):
        if not s:
            return
        p = self.ps.HInsertText
        self.act.GetDefault("InsertText", p.HSet)
        p.Text = s
        self.act.Execute("InsertText", p.HSet)

    def enter(self, n=1):
        for _ in range(n):
            self.run("BreakPara")

    def line(self, s="", size=BASE_PT, bold=False, align="left", left_mm=0.0, right_mm=0.0):
        """문단 하나 작성 후 줄바꿈"""
        self.para(align, left_mm, right_mm=right_mm)
        self.char(size if s else GAP_PT, bold)
        self.text(s)
        self.enter()

    # ---------------------------------------------- 페이지
    def page_setup(self, left=20, right=20, top=20, bottom=15):
        p = self.ps.HSecDef
        self.act.GetDefault("PageSetup", p.HSet)
        p.PageDef.LeftMargin = self.mm(left)
        p.PageDef.RightMargin = self.mm(right)
        p.PageDef.TopMargin = self.mm(top)
        p.PageDef.BottomMargin = self.mm(bottom)
        p.PageDef.HeaderLen = self.mm(0)
        p.PageDef.FooterLen = self.mm(0)
        p.HSet.SetItem("ApplyClass", 24)
        p.HSet.SetItem("ApplyTo", 3)
        self.act.Execute("PageSetup", p.HSet)

    # ---------------------------------------------- 표
    def table(self, rows, col_mm, row_mm=None):
        p = self.ps.HTableCreation
        self.act.GetDefault("TableCreate", p.HSet)
        p.Rows = rows
        p.Cols = len(col_mm)
        p.WidthType = 2
        p.WidthValue = self.mm(sum(col_mm))
        p.CreateItemArray("ColWidth", len(col_mm))
        for i, w in enumerate(col_mm):
            # ColWidth 에는 셀 안쪽 좌우 여백이 더해지므로 미리 뺌
            p.ColWidth.SetItem(i, self.mm(w - CELL_PAD_MM))
        if row_mm:
            p.HeightType = 1
            p.HeightValue = self.mm(row_mm * rows)
            p.CreateItemArray("RowHeight", rows)
            for i in range(rows):
                p.RowHeight.SetItem(i, self.mm(row_mm))
        p.TableProperties.TreatAsChar = 1
        p.TableProperties.CellMarginLeft = p.TableProperties.CellMarginRight = self.mm(CELL_MARGIN_MM)
        p.TableProperties.HorzRelTo = 0
        self.act.Execute("TableCreate", p.HSet)

    def cell(self, s, size=9, bold=False, align="center", move=True):
        """현재 셀에 쓰고 다음 셀로 이동"""
        self.para(align)
        self.char(size, bold)
        self.text(s)
        if move:
            self.run("TableRightCell")

    def select_cells(self, count):
        """현재 셀부터 오른쪽(다음) count개 셀 블록 선택"""
        self.run("TableCellBlock")
        self.run("TableCellBlockExtend")
        for _ in range(count - 1):
            self.run("TableRightCell")

    def borders(self, top=0, bottom=0, left=0, right=0):
        """선택한 셀 테두리 (0 = 없음, 1 = 실선)"""
        p = self.ps.HCellBorderFill
        self.act.GetDefault("CellBorder", p.HSet)
        p.BorderTypeTop, p.BorderTypeBottom = top, bottom
        p.BorderTypeLeft, p.BorderTypeRight = left, right
        p.TypeHorz = p.TypeVert = 0  # 선택 영역 안쪽 선
        self.act.Execute("CellBorder", p.HSet)

    def exit_table(self):
        """표 밖으로 나와 문서 끝(표 뒤)으로 이동"""
        self.run("Cancel")
        self.run("CloseEx")
        self.run("MoveDocEnd")

    def save(self, path, fmt="HWP"):
        return self.hwp.SaveAs(str(path), fmt, "")

    def close(self):
        try:
            self.hwp.Clear(1)
        finally:
            self.hwp.Quit()


def build_hwp(doc: dict, items: list[dict], path, pdf_path=None):
    amounts = [split_amount(it["qty"], it["price"], it["vat"]) for it in items]
    total = sum(s + t for s, t in amounts)

    w = HwpWriter()
    try:
        w.page_setup()

        w.line("품 의 서", size=20, bold=True, align="center")
        w.line()
        w.line()

        # 제목: 아래쪽 선만 있는 1x2 표
        w.para("left")
        w.table(1, [25, 145], row_mm=8)
        w.cell("제    목", size=BASE_PT, bold=True, align="left")
        w.cell(f"[품의서]  {doc['title']}", size=BASE_PT, align="left", move=False)
        w.run("TableLeftCell")
        w.select_cells(2)
        w.borders(bottom=1)
        w.exit_table()
        w.enter()
        w.line()
        w.line()

        w.line(f"{doc['target']}{eul_reul(doc['target'])} 아래와 같이 구매하고자 하오니 재가하여 주시기 바랍니다.")
        w.line()
        w.line()
        w.line()
        w.line("-   아      래   -", align="center")
        w.line()
        w.line()

        w.line(f"1. 견 적 처 : {doc['vendor']}", left_mm=INDENT_MM)
        vat_note = " VAT포함" if doc.get("vat_note") else ""
        w.line(f"2. 견적금액 : 금{total:,}원(금{won_to_korean(total)}원){vat_note}", left_mm=INDENT_MM)
        w.line("3. 견적내역", left_mm=INDENT_MM)
        # 표는 가운데. 단위는 표 오른쪽 끝에 맞춤
        w.line("(단위 : 개, 원)", size=7, align="right", right_mm=(TEXT_WIDTH_MM - sum(COL_MM)) / 2)

        # 견적내역 표
        w.para("center")
        w.table(len(items) + 2, COL_MM, row_mm=7)
        for h in ["NO", "품목", "수량", "단가", "공급가액", "세 액", "합 계", "비고"]:
            w.cell(h, bold=True)
        for i, (it, (supply, tax)) in enumerate(zip(items, amounts), 1):
            w.cell(str(i))
            w.cell(it["name"])
            w.cell(f"{it['qty']:,}")
            w.cell(f"{it['price']:,}", align="right")
            w.cell(f"{supply:,}", align="right")
            w.cell(f"{tax:,}", align="right")
            w.cell(f"{supply + tax:,}", align="right")
            w.cell(it["note"])
        # 총계 행: 앞 3칸 병합
        w.select_cells(3)
        w.run("TableMergeCell")
        w.run("Cancel")
        w.cell("총계")
        sums = [sum(it["price"] for it in items), sum(s for s, _ in amounts),
                sum(t for _, t in amounts), total]
        for v in sums:
            w.cell(f"{v:,}", size=10, bold=True, align="right")
        w.cell("", move=False)
        w.exit_table()
        w.enter()
        w.line()

        # 4. 지급방식·구매처: 입력하지 않았으면 항목을 빼고 빈 줄만 맞춤
        lines = payment_lines(doc["payment"], doc["payment_detail"], doc.get("shop", ""))
        for ln in lines:
            w.line(ln, left_mm=INDENT_MM)
        w.line()
        if lines:
            w.line()

        # 붙임: 테두리 없는 (붙임 수)x2 표, 첫 줄에만 '붙 임 :'
        attach = doc["attach"]
        if attach:
            # 붙임 글자가 1~4번 항목과 같은 위치에서 시작하도록 표 안쪽 여백만큼 덜 들여씀
            w.para("left", left_mm=INDENT_MM - TABLE_TEXT_SHIFT_MM)
            w.table(len(attach), [25, TEXT_WIDTH_MM - INDENT_MM - 25], row_mm=6)
            for i, ln in enumerate(attach):
                last = i == len(attach) - 1
                w.cell("붙    임 :" if i == 0 else "", size=BASE_PT, align="left")
                w.cell(ln + (" 끝." if last and not ln.endswith("끝.") else ""), size=BASE_PT, align="left", move=not last)
            w.run("TableColBegin")   # 행의 첫 셀
            w.run("TableColPageUp")  # 열의 맨 위 셀
            w.select_cells(len(attach) * 2)
            w.borders()
            w.exit_table()

        ok = w.save(path, "HWP")
        if pdf_path:
            w.save(pdf_path, "PDF")
        return ok
    finally:
        w.close()
