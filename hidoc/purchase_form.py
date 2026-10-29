"""구매 품의서 작성 화면 (메인 창 app.py 안에 들어가는 화면 조각)

구매 내용을 입력받아 한글(.hwp) 품의서 생성, 하이웍스용 복사, 견적서 불러오기를 함.
저장 폴더 구조는 storage.py 참고.
입력 부분은 창이 작으면 스크롤되고, 맨 아래 버튼 줄(저장 위치·하이웍스용 복사·한글 생성)은 항상 보임.
저장 경로와 견적서 읽기 방식은 설정 탭에서만 바꾸고 여기서는 보여 주기만 함.
"""

import os
import datetime as dt
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

from .money import VAT_MODES, split_amount
from .quote_reader import READ_MODES
from .settings import DEFAULT_SAVE_DIR, get_setting, output_dir
from .storage import (attach_line, attach_types, company_folders, copy_attachments, copy_name, safe_filename,
                      unique_path)
from .widgets import (FIELD_BORDER, FIELD_FOCUS, TABLE_FONT, add_placeholder, add_suggestions, ask_api_key,
                      ask_choice, stripe_rows, style_table)

NOTICE_COLOR = "#b45309"  # 주황: 안내·확인할 점
EDIT_COLS = ["name", "qty", "price", "vat", "note"]  # 견적내역 표에서 입력하는 열 (나머지는 계산값)
NEW_ROW = "new"  # 견적내역 표 맨 아래 '새 품목' 줄
NEW_ROW_TEXT = ("＋ 여기를 눌러 새 품목 입력",)
QUOTE_FILETYPES = [("견적서", "*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff"), ("모든 파일", "*.*")]


def set_edit_mode(add_btn, edit_btns, editing):
    """목록에서 줄을 고르면 [추가] 대신 [수정 저장][삭제][취소]를 보여 줌 (같은 줄이 두 번 추가되는 것 방지)"""
    for b in (add_btn, *edit_btns):
        b.pack_forget()
    for b in (edit_btns if editing else [add_btn]):
        b.pack(side="left", fill="x", expand=True, padx=(0, 2))


# ---------------------------------------------------------------- GUI
class PurchaseRequestForm(ttk.Frame):
    TREE_COLS = ["name", "qty", "price", "vat", "supply", "tax", "total", "note"]

    def __init__(self, master):
        super().__init__(master)
        self.target_var = tk.StringVar()
        self.title_var = tk.StringVar()
        self.vendor_var = tk.StringVar()
        self.payment_var = tk.StringVar()  # 비워 두면 품의서에서 4번 지급방식 항목을 뺌
        self.shop_var = tk.StringVar()  # 온라인 구매(쿠팡 등) 주소. 비워 두면 구매처 항목을 뺌
        self.vat_note_var = tk.BooleanVar(value=False)  # 견적금액 뒤 'VAT포함' 표기

        self._build_actions()  # 맨 아래 버튼 줄을 먼저 붙여야 창이 작아도 가려지지 않음
        self._build_scroller()
        self._build_info()
        self._build_items()
        self._build_attach()
        self.refresh_from_settings()

    def refresh_from_settings(self):
        """설정 탭에서 바꾼 값(저장 경로, 읽기 방식, 붙임 종류)을 반영. 메인 창이 이 화면을 보여 줄 때마다 부름"""
        mode_label = {v: k for k, v in READ_MODES.items()}.get(get_setting("read_mode"), "로컬 (무료)")
        self.read_mode_lbl.config(text=f"읽기 방식: {mode_label}  (설정 탭에서 변경)")
        self.save_lbl.config(text=f"{output_dir(self._save_dir())}\\기업명\\날짜 폴더에 저장")
        self.attach_kind_box.config(values=attach_types())
        self._refresh_vendors()

    @staticmethod
    def _save_dir():
        return get_setting("save_dir").strip() or DEFAULT_SAVE_DIR

    def _refresh_vendors(self):
        """견적처 드롭다운 목록 = 저장 경로\\hidoc_output 안의 기업 폴더"""
        self.vendor_box.config(values=company_folders(self._save_dir()))

    # ------------------------------------------------ 화면 틀
    def _build_actions(self):
        bar = ttk.Frame(self, padding=(10, 8, 10, 10))
        bar.pack(side="bottom", fill="x")
        ttk.Separator(self).pack(side="bottom", fill="x")
        ttk.Button(bar, text="한글 생성", style="Primary.TButton", command=self.generate).pack(side="right")
        ttk.Button(bar, text="하이웍스용 복사", style="Primary.TButton",
                   command=self.copy_for_web).pack(side="right", padx=8)
        ttk.Button(bar, text="저장 폴더 열기", command=self.open_folder).pack(side="left")
        self.save_lbl = ttk.Label(bar, foreground="gray")
        self.save_lbl.pack(side="left", padx=8)

    def _build_scroller(self):
        """입력 부분을 담는 스크롤 영역. 창이 충분히 크면 창 높이에 맞춰 늘어나고(견적내역 표가 커짐), 작으면 스크롤"""
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, yscrollincrement=20)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas)
        self.body_win = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.canvas.bind("<Configure>", self._fit_body)
        self.bind_all("<MouseWheel>", self._on_wheel, add="+")

    def _fit_body(self, _e=None):
        ch = self.canvas.winfo_height()
        need = self.body.winfo_reqheight()
        self.canvas.itemconfig(self.body_win, width=self.canvas.winfo_width(), height=max(need, ch))
        self.canvas.config(scrollregion=(0, 0, 0, max(need, ch)))
        if need > ch and not self.scrollbar.winfo_ismapped():
            self.scrollbar.pack(side="right", fill="y", before=self.canvas)
        elif need <= ch and self.scrollbar.winfo_ismapped():
            self.scrollbar.pack_forget()
            self.canvas.yview_moveto(0)

    def _on_wheel(self, e):
        """마우스 휠로 입력 부분 스크롤. 표·여러 줄 칸 위에서는 그 칸이 스스로 스크롤하므로 건드리지 않음"""
        if not self.winfo_ismapped() or not self.scrollbar.winfo_ismapped():
            return
        w = self.winfo_containing(e.x_root, e.y_root)
        if w is None or not str(w).startswith(str(self.canvas)) or isinstance(w, (ttk.Treeview, tk.Text, tk.Listbox)):
            return
        self.canvas.yview_scroll(-3 if e.delta > 0 else 3, "units")

    # ------------------------------------------------ 기본 정보
    def _build_info(self):
        frm = ttk.LabelFrame(self.body, text=" 기본 정보 ", padding=8)
        frm.pack(fill="x", padx=10, pady=(10, 5))
        rows = [
            ("구매대상", self.target_var, "예) G.Eye-Parking H100 Multi 설계 및 3대 제작 선금"),
            ("제목", self.title_var, "비워두면 '구매대상 + 구매의 건'으로 자동 작성"),
            ("견적처", self.vendor_var, "기업명 - ▼ 목록에서 기존 기업을 고르거나 새로 입력"),
            ("지급방식", self.payment_var, f"예) {get_setting('payment_example')}  (비우면 항목 뺌)"),
            ("지급 상세", None, None),
            ("구매처", self.shop_var, "온라인 구매 주소(URL) 예) 쿠팡 장바구니 주소  (비우면 항목 뺌)"),
        ]
        for i, (label, var, hint) in enumerate(rows):
            ttk.Label(frm, text=label, width=9).grid(row=i, column=0, sticky="nw", pady=2)
            if var is None:  # 지급방식 상세: 한 줄에 하나
                # 여러 줄 칸은 ttk 가 아니라서 테두리를 강조선(highlight)으로 한 줄 칸과 같게 그림
                self.detail_txt = tk.Text(frm, height=3, font=("맑은 고딕", 10), relief="flat", borderwidth=2,
                                          highlightthickness=1, highlightbackground=FIELD_BORDER,
                                          highlightcolor=FIELD_FOCUS)
                self.detail_txt.grid(row=i, column=1, sticky="ew", pady=2)  # 예시 글자 없음 (여러 줄 칸은 겹쳐 그려야 해서)
                continue
            if var is self.vendor_var:
                # 직접 입력도 되는 드롭다운. 목록은 hidoc_output 안의 기업 폴더 (열 때마다 새로 읽음)
                entry = self.vendor_box = ttk.Combobox(frm, textvariable=var, postcommand=self._refresh_vendors,
                                                       style="Wide.TCombobox")  # 화살표 버튼을 넓게
                # 입력하는 동안에도 같은 글자가 들어간 기존 기업을 칸 아래에 보여 줌
                add_suggestions(entry, var, lambda: company_folders(self._save_dir()))
            else:
                entry = ttk.Entry(frm, textvariable=var)
            entry.grid(row=i, column=1, sticky="ew", pady=2)
            add_placeholder(entry, hint)
        frm.columnconfigure(1, weight=1)

        row = len(rows)
        ttk.Label(frm, text="견적서", width=9).grid(row=row, column=0, sticky="w", pady=(6, 2))
        quote = ttk.Frame(frm)
        quote.grid(row=row, column=1, sticky="w", pady=(6, 2))
        self.quote_btn = ttk.Button(quote, text="견적서 불러오기…", command=self.load_quote)
        self.quote_btn.pack(side="left")
        self.read_mode_lbl = ttk.Label(quote, foreground="gray")
        self.read_mode_lbl.pack(side="left", padx=10)
        # 아래 줄: 읽는 동안은 진행 막대 + 상태(_busy), 끝나면 불러온 결과·확인할 점. 내용이 있을 때만 보임
        self.note_row = ttk.Frame(frm)
        self.note_row.grid(row=row + 1, column=1, sticky="w")
        self.quote_progress = ttk.Progressbar(self.note_row, mode="indeterminate", length=120)
        self.quote_note = ttk.Label(self.note_row, foreground=NOTICE_COLOR, justify="left", wraplength=860)
        self.quote_note.pack(side="left")
        self._set_note("")

    def _set_note(self, text, color=NOTICE_COLOR):
        self.quote_note.config(text=text, foreground=color)
        if text:
            self.note_row.grid()
        else:
            self.note_row.grid_remove()
        self.after_idle(self._fit_body)  # 줄이 생기고 없어지면 스크롤 높이도 바뀜

    # ------------------------------------------------ 견적내역
    def _build_items(self):
        frm = ttk.LabelFrame(self.body, padding=8,
                             text=" 견적내역  (칸을 누르면 바로 입력 · 세액: 별도 = 단가+10% / 포함 = 단가에 부가세 포함 / 없음 = 면세) ")
        frm.pack(fill="both", expand=True, padx=10, pady=5)

        heads = ["품목", "수량", "단가", "세액구분", "공급가액", "세액", "합계", "비고"]
        widths = [230, 60, 100, 70, 100, 90, 110, 100]
        tree_frm = ttk.Frame(frm)
        tree_frm.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frm, columns=self.TREE_COLS, show="headings", height=7)
        for c, h, w in zip(self.TREE_COLS, heads, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, minwidth=40, anchor={"name": "w", "note": "w", "vat": "center"}.get(c, "e"))
        self.tree.tag_configure("new", foreground="gray")
        style_table(self.tree)
        sb = ttk.Scrollbar(tree_frm, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self._on_tree_click, add="+")
        self.tree.bind("<Delete>", lambda _e: self.delete_item())
        # 표 크기가 바뀌거나 표를 스크롤하면 떠 있는 입력칸 자리가 어긋나므로 입력을 마침
        self.tree.bind("<Configure>", lambda _e: self._end_edit(), add="+")  # add: style_table 의 칸선 맞춤도 유지
        self.tree.bind("<MouseWheel>", lambda _e: self._end_edit(), add="+")
        self.items: dict[str, dict] = {}  # tree iid -> item (맨 아래 '새 품목' 줄은 빠짐)
        self.editor = None  # 지금 떠 있는 입력칸
        self.edit_cell = None  # (줄, 열)
        self.tree.insert("", "end", iid=NEW_ROW, values=NEW_ROW_TEXT, tags=("new",))

        sum_row = ttk.Frame(frm)
        sum_row.pack(fill="x", pady=(6, 0))
        ttk.Button(sum_row, text="선택한 줄 삭제", command=self.delete_item).pack(side="left")
        ttk.Checkbutton(sum_row, text="견적금액에 'VAT포함' 표기", variable=self.vat_note_var).pack(side="left", padx=12)
        self.total_lbl = ttk.Label(sum_row, font=("맑은 고딕", 10, "bold"))
        self.total_lbl.pack(side="right")
        self._refresh()

    # ------------------------------------------------ 붙임
    def _build_attach(self):
        parent = ttk.LabelFrame(self.body, text=" 붙임  (마지막 줄에 '끝.' 자동 · 목록의 줄을 더블클릭하면 파일 연결) ",
                                padding=8)
        parent.pack(fill="x", padx=10, pady=(5, 10))
        self.attach_kind = tk.StringVar()  # 처음엔 비워 두고 칸 안에 '선택' 표시
        self.attach_name = tk.StringVar()
        self.attach_count = tk.StringVar(value="1")
        self.attach_src = tk.StringVar()
        self.attach_as_is = tk.BooleanVar(value=False)  # 쓴 이름을 그대로 파일 이름으로 ([종류]·날짜 없이)

        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Label(row, text="종류").pack(side="left")
        # 목록에 없는 종류도 직접 입력 가능
        self.attach_kind_box = ttk.Combobox(row, textvariable=self.attach_kind, values=attach_types(), width=13,
                                            style="Wide.TCombobox")  # 화살표 버튼을 넓게
        self.attach_kind_box.pack(side="left", padx=(4, 10))
        add_placeholder(self.attach_kind_box, "선택")
        ttk.Label(row, text="이름").pack(side="left")
        name = ttk.Entry(row, textvariable=self.attach_name, width=24)
        name.pack(side="left", padx=(4, 4), fill="x", expand=True)
        add_placeholder(name, "비우면 [종류]기업명_날짜")  # 복사될 파일 이름 규칙 (storage.copy_name)
        # 체크하면 복사될 파일 이름이 [종류]이름_날짜 대신 쓴 이름 그대로 (이름을 비우면 체크해도 [종류]기업명_날짜)
        ttk.Checkbutton(row, text="그대로 파일명", variable=self.attach_as_is).pack(side="left", padx=(0, 10))
        ttk.Label(row, text="부수").pack(side="left")
        # 입력칸 + [+][−] 버튼 (키보드 ↑↓도). 숫자 칸(Spinbox)은 화살표가 위아래로 쌓여 다른 칸보다 높아서 안 씀
        count = ttk.Entry(row, textvariable=self.attach_count, width=3, justify="center")
        count.pack(side="left", padx=(4, 2), fill="y")
        for text, step in (("+", 1), ("−", -1)):
            ttk.Button(row, text=text, width=2, style="Step.TButton",
                       command=lambda s=step: self._step_count(s)).pack(side="left", fill="y", padx=(0, 2))
        count.bind("<Up>", lambda _e: self._step_count(1))
        count.bind("<Down>", lambda _e: self._step_count(-1))
        ttk.Frame(row, width=8).pack(side="left")
        ttk.Label(row, text="파일").pack(side="left")
        ttk.Entry(row, textvariable=self.attach_src, state="readonly", width=12).pack(
            side="left", padx=(4, 2), fill="x", expand=True)
        ttk.Button(row, text="파일…", width=5, command=self.choose_attach_file).pack(side="left", padx=(0, 10))
        self.attach_btns = ttk.Frame(row, width=230)
        self.attach_btns.pack(side="left")
        self.attach_add_btn = ttk.Button(self.attach_btns, text="추가", command=self.add_attach)
        self.attach_edit_btns = [ttk.Button(self.attach_btns, text="수정 저장", command=self.update_attach),
                                 ttk.Button(self.attach_btns, text="삭제", command=self.delete_attach),
                                 ttk.Button(self.attach_btns, text="취소", command=self.cancel_attach)]
        set_edit_mode(self.attach_add_btn, self.attach_edit_btns, False)

        self.attach_tree = ttk.Treeview(parent, columns=("line", "src"), show="headings", height=4)
        self.attach_tree.heading("line", text="붙임 표기")
        self.attach_tree.heading("src", text="첨부 파일 (원본 → 복사될 이름)")
        self.attach_tree.column("line", width=260)
        self.attach_tree.column("src", width=600)
        self.attach_tree.pack(fill="both", expand=True, pady=(6, 0))
        style_table(self.attach_tree)
        self.attach_tree.bind("<<TreeviewSelect>>", self._on_attach_select)
        self.attach_tree.bind("<Double-1>", self.choose_attach_file)
        self.attaches: dict[str, dict] = {}  # tree iid -> {kind, name, count, src}. 처음에는 비어 있음
        self.vendor_var.trace_add("write", lambda *_: self._refresh_attach())

    def _attach_name(self, a):
        return a["name"] or self.vendor_var.get().strip()

    @staticmethod
    def _as_is(a):
        """'이름 그대로 파일명'은 이름을 썼을 때만 (비어 있으면 [종류]기업명_날짜)"""
        return bool(a.get("as_is") and a["name"])

    def _copy_name(self, a, date):
        return copy_name(a["kind"], self._attach_name(a), a["src"], date, self._as_is(a))

    def _attach_values(self, a):
        # 같은 종류가 여러 개면 '견적서_AMP 1부.'처럼 이름으로 구별, 하나면 '견적서 1부.'
        same_kind = sum(b["kind"] == a["kind"] for b in self.attaches.values())
        line = attach_line(a["kind"], a["count"], self._attach_name(a) if same_kind > 1 else "")
        if not a["src"]:
            return line, ""
        return line, f"{Path(a['src']).name}  →  {self._copy_name(a, f'{dt.date.today():%y%m%d}')}"

    def _insert_attach(self, a):
        iid = self.attach_tree.insert("", "end")
        self.attaches[iid] = a
        self._refresh_attach()  # 같은 종류가 늘면 다른 줄 표기도 바뀜

    def _refresh_attach(self):
        for iid, a in self.attaches.items():
            self.attach_tree.item(iid, values=self._attach_values(a))
        stripe_rows(self.attach_tree)

    def _read_attach(self):
        kind = self.attach_kind.get().strip()
        if not kind:
            messagebox.showwarning("입력 확인", "붙임 문서 종류를 선택하세요.")
            return None
        try:
            count = max(1, int(self.attach_count.get()))
        except ValueError:
            count = 1
        return {"kind": kind, "name": self.attach_name.get().strip(), "count": count, "src": self.attach_src.get(),
                "as_is": self.attach_as_is.get()}

    def _step_count(self, step):
        try:
            count = int(self.attach_count.get().strip() or 0)
        except ValueError:
            count = 0
        self.attach_count.set(str(max(1, count + step)))
        return "break"  # ↑↓ 키의 기본 동작은 막음

    def _clear_attach_entry(self):
        self.attach_kind.set("")  # 다음 붙임도 종류를 새로 고르게 ('선택' 표시)
        self.attach_name.set("")
        self.attach_count.set("1")
        self.attach_src.set("")
        self.attach_as_is.set(False)

    def choose_attach_file(self, _e=None):
        """목록에서 선택한 붙임이 있으면 바로 연결, 없으면 새로 추가할 항목용으로 입력칸에만 채움"""
        if _e is not None:  # 더블클릭: 클릭한 줄을 대상으로
            iid = self.attach_tree.identify_row(_e.y)
            if not iid:
                return
            self.attach_tree.selection_set(iid)
        sel = self.attach_tree.selection()
        a = self.attaches[sel[0]] if sel else None
        title = f"붙임 파일 선택 - [{a['kind']}]" if a else "붙임 파일 선택"
        path = filedialog.askopenfilename(title=title, initialdir=get_setting("attach_dir"), parent=self)
        if not path:
            return
        self.attach_src.set(path)
        if a:
            a["src"] = path
            self.attach_tree.item(sel[0], values=self._attach_values(a))

    def add_attach(self):
        a = self._read_attach()
        if a:
            self._insert_attach(a)
            self._clear_attach_entry()

    def update_attach(self):
        sel = self.attach_tree.selection()
        if not sel:
            return
        a = self._read_attach()
        if a:
            self.attaches[sel[0]] = a
            self._refresh_attach()
            self.cancel_attach()

    def cancel_attach(self):
        self.attach_tree.selection_remove(self.attach_tree.selection())
        self._clear_attach_entry()
        set_edit_mode(self.attach_add_btn, self.attach_edit_btns, False)

    def _reset_attach(self):
        """붙임 목록을 비우고 입력칸을 처음 상태로"""
        self.attach_tree.delete(*self.attach_tree.get_children())
        self.attaches.clear()
        self.attach_kind.set("")
        self.cancel_attach()

    def delete_attach(self):
        for iid in self.attach_tree.selection():
            self.attach_tree.delete(iid)
            self.attaches.pop(iid, None)
        self._refresh_attach()
        self.cancel_attach()

    def _on_attach_select(self, _e):
        sel = self.attach_tree.selection()
        set_edit_mode(self.attach_add_btn, self.attach_edit_btns, bool(sel))
        if sel:
            a = self.attaches[sel[0]]
            self.attach_kind.set(a["kind"])
            self.attach_name.set(a["name"])
            self.attach_count.set(str(a["count"]))
            self.attach_src.set(a["src"])
            self.attach_as_is.set(a.get("as_is", False))
        else:
            self._clear_attach_entry()

    # ------------------------------------------------ 품목 조작 (표 칸을 누르면 그 자리에 입력칸이 뜸)
    def _row_values(self, d):
        supply, tax = split_amount(d["qty"], d["price"], d["vat"])
        # 세액구분 뒤 ▾ : 눌러서 고르는 칸이라는 표시 (표에만 보이고 값에는 안 들어감)
        return (d["name"], f"{d['qty']:,}", f"{d['price']:,}", f"{d['vat']}  ▾", f"{supply:,}", f"{tax:,}",
                f"{supply + tax:,}", d["note"])

    def _insert_item(self, d):
        iid = self.tree.insert("", "end", values=self._row_values(d))
        self.items[iid] = d
        self.tree.move(NEW_ROW, "", "end")  # '새 품목' 줄은 항상 맨 아래
        stripe_rows(self.tree)
        return iid

    def _on_tree_click(self, e):
        if self.tree.identify_region(e.x, e.y) != "cell":  # 제목 줄·열 경계(너비 끌기)는 그대로
            self._end_edit()
            return
        row = self.tree.identify_row(e.y)
        col = self.TREE_COLS[int(self.tree.identify_column(e.x)[1:]) - 1]
        if row == NEW_ROW:
            col = "name"  # 새 품목은 품목 이름부터
        if col in EDIT_COLS:
            self.after_idle(self._begin_edit, row, col)  # 줄 선택(기본 동작)이 끝난 뒤에 띄움
        else:
            self._end_edit()  # 공급가액·세액·합계는 계산값이라 입력 안 함

    def _begin_edit(self, row, col, keyboard=False):
        self._end_edit()
        if not self.tree.exists(row):
            return
        self.tree.see(row)
        self.update_idletasks()
        box = self.tree.bbox(row, col)
        if not box:
            return
        x, y, w, h = box
        if col == "vat":  # 세 가지 중 고르기: 칸 바로 아래에 메뉴
            menu = tk.Menu(self, tearoff=0)
            for m in VAT_MODES:
                menu.add_command(label=m, command=lambda m=m: self._vat_chosen(row, m, keyboard))
            menu.tk_popup(self.tree.winfo_rootx() + x, self.tree.winfo_rooty() + y + h)
            return
        d = self.items.get(row)
        value = "" if d is None else d[col]
        ed = ttk.Entry(self.tree, justify="right" if col in ("qty", "price") else "left", font=TABLE_FONT)
        ed.insert(0, f"{value:,}" if isinstance(value, int) else value)
        ed.select_range(0, "end")
        ed.place(x=x, y=y, width=w, height=h)
        ed.focus_set()
        ed.bind("<Return>", lambda _e: self._edit_next(1))
        ed.bind("<Tab>", lambda _e: self._edit_next(1))
        ed.bind("<Shift-Tab>", lambda _e: self._edit_next(-1))
        ed.bind("<Escape>", lambda _e: self._end_edit(commit=False))
        ed.bind("<FocusOut>", lambda _e: self._end_edit() if self.editor is ed else None)
        if col == "qty":
            ed.bind("<Up>", lambda _e: self._step_qty(ed, 1))
            ed.bind("<Down>", lambda _e: self._step_qty(ed, -1))
        self.editor, self.edit_cell = ed, (row, col)

    @staticmethod
    def _step_qty(ed, step):
        try:
            qty = int(ed.get().replace(",", "").strip() or 0)
        except ValueError:
            qty = 0
        ed.delete(0, "end")
        ed.insert(0, f"{max(1, qty + step):,}")
        return "break"  # ↑↓ 키의 기본 동작은 막음

    def _end_edit(self, commit=True):
        """떠 있는 입력칸을 닫고 값을 반영. 반영된 줄(새 품목이면 새로 생긴 줄)을 돌려줌"""
        ed = self.editor
        if ed is None:
            return None
        self.editor = None
        row, col = self.edit_cell
        text = ed.get()
        ed.destroy()
        return self._set_cell(row, col, text) if commit else row

    def _set_cell(self, row, col, text):
        text = text.strip()
        if row == NEW_ROW:
            if not text:
                return None
            return self._insert_item({"name": text, "qty": 1, "price": 0, "vat": "별도", "note": ""})
        d = self.items[row]
        if col in ("qty", "price"):
            try:
                n = int(text.replace(",", ""))
                if n < (1 if col == "qty" else 0):
                    raise ValueError
            except ValueError:
                self.bell()  # 숫자가 아니면 원래 값 그대로
                return row
            d[col] = n
        elif col == "name" and not text:
            self.bell()  # 품목 이름은 비울 수 없음 (줄을 없애려면 삭제)
            return row
        else:
            d[col] = text
        self._refresh()
        return row

    def _vat_chosen(self, row, mode, keyboard):
        if row in self.items:
            self.items[row]["vat"] = mode
            self._refresh()
            if keyboard:  # Tab·Enter 로 왔으면 다음 칸(비고)으로 이어서
                self._begin_edit(row, "note", keyboard=True)

    def _edit_next(self, step):
        """Tab·Enter: 다음 칸, Shift+Tab: 이전 칸. 줄 끝에서는 다음 줄 품목으로 (마지막이면 새 품목 줄)"""
        col = self.edit_cell[1]
        row = self._end_edit()
        if row is None:  # 새 품목 줄을 비운 채로 넘어감
            return "break"
        rows = list(self.tree.get_children())
        i = EDIT_COLS.index(col) + step
        if 0 <= i < len(EDIT_COLS):
            self._begin_edit(row, EDIT_COLS[i], keyboard=True)
        else:
            j = rows.index(row) + (1 if i > 0 else -1)
            if 0 <= j < len(rows):
                self._begin_edit(rows[j], EDIT_COLS[0] if i > 0 else EDIT_COLS[-1], keyboard=True)
        return "break"

    def delete_item(self):
        self._end_edit(commit=False)
        for iid in self.tree.selection():
            if iid != NEW_ROW:
                self.tree.delete(iid)
                self.items.pop(iid, None)
        self._refresh()

    def _clear_items(self):
        self._end_edit(commit=False)
        for iid in list(self.items):
            self.tree.delete(iid)
        self.items.clear()
        self._refresh()

    def _item_list(self):
        return [self.items[iid] for iid in self.tree.get_children() if iid != NEW_ROW]

    def _refresh(self):
        for iid, d in self.items.items():
            self.tree.item(iid, values=self._row_values(d))
        stripe_rows(self.tree)
        amounts = [split_amount(i["qty"], i["price"], i["vat"]) for i in self._item_list()]
        supply = sum(s for s, _ in amounts)
        tax = sum(t for _, t in amounts)
        self.total_lbl.config(text=f"공급가액 {supply:,}  +  세액 {tax:,}  =  총계 ₩{supply + tax:,}")

    # ------------------------------------------------ 견적서 읽기
    def load_quote(self):
        # 지워질 견적내역이 있으면 파일을 고르기 전에 미리 알림 (읽은 뒤에는 묻지 않고 바로 채움)
        if self.items and not messagebox.askokcancel(
                "견적서 불러오기", f"견적서를 불러오면 지금 견적내역(품목 {len(self.items)}개)은 지워지고\n"
                "견적서 내용으로 바뀝니다. 계속할까요?", icon="warning", parent=self):
            return
        mode = get_setting("read_mode")
        api_key = get_setting("anthropic_api_key")
        if mode == "claude" and not (api_key or os.environ.get("ANTHROPIC_API_KEY")):
            messagebox.showinfo("API 키 필요", "Claude API 방식은 API 키가 필요합니다.\n"
                                "(이 방식은 화면에서 숨겨져 있고 settings.json 으로만 켤 수 있습니다.)", parent=self)
            if not ask_api_key(self):
                return
            api_key = get_setting("anthropic_api_key")
        self._choose_quote(mode, api_key)

    def _choose_quote(self, mode, api_key, title="견적서 선택"):
        """견적서 파일을 골라 읽기 시작. 유효일이 지나 다시 고를 때도 씀"""
        path = filedialog.askopenfilename(title=title, filetypes=QUOTE_FILETYPES,
                                          initialdir=get_setting("quote_dir"), parent=self)
        if path:
            self._start_quote(path, mode, api_key)

    def _busy(self, text):
        """견적서 읽기·로그인 대기 중 표시. text 가 비면 원래대로"""
        self.quote_btn.state(["disabled"] if text else ["!disabled"])
        self.winfo_toplevel().config(cursor="watch" if text else "")
        if text:
            self.quote_progress.pack(side="left", before=self.quote_note, padx=(0, 8), pady=2)
            self.quote_progress.start(12)
            self._set_note(text, "gray")
        else:
            self.quote_progress.stop()
            self.quote_progress.pack_forget()
            self._set_note("")

    def _start_quote(self, path, mode, api_key):
        # 읽는 동안 창이 멈추지 않도록 따로 실행하고 끝날 때까지 확인
        result = {}

        def work():
            try:
                from .quote_reader import read_quote
                result["data"] = read_quote(path, mode, api_key)
            except Exception as e:  # QuoteReadError 는 안내문, 그 밖은 예상 못 한 오류
                result["error"] = e

        self._busy("견적서 읽는 중…")
        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        self._wait_quote(thread, (path, mode, api_key), result)

    def _wait_quote(self, thread, job, result):
        if thread.is_alive():
            self.after(200, self._wait_quote, thread, job, result)
            return
        self._busy("")
        if "error" in result:
            e = result["error"]
            if type(e).__name__ == "ClaudeCodeNotInstalled":
                self._offer_step(job, "Claude Code 설치", f"{e}\n\n지금 설치할까요? (관리자 권한 필요 없음, 1~2분)\n"
                                 "Claude Pro·Max 같은 유료 구독이 있어야 쓸 수 있습니다. 무료 플랜은 안 됩니다.\n"
                                 "설치 창이 끝나면 Enter 키를 누르세요. 이어서 로그인 단계로 넘어갑니다.",
                                 "start_claude_code_install", "설치 기다리는 중…")
                return
            if type(e).__name__ == "ClaudeCodeLoginRequired":
                self._offer_step(job, "Claude Code 로그인", f"{e}\n\n지금 로그인 창을 열까요?\n"
                                 "브라우저에서 Claude 계정으로 로그인한 뒤, 검은 창에서 아무 키나 누르면\n"
                                 "견적서를 자동으로 다시 읽습니다.",
                                 "start_claude_code_login", "로그인 기다리는 중…")
                return
            if any(c.__name__ == "QuoteReadError" for c in type(e).__mro__):
                msg = str(e)
            elif isinstance(e, ImportError):
                msg = f"견적서 읽기에 필요한 패키지가 없습니다. 실행.bat으로 다시 실행해 주세요.\n{e}"
            else:
                msg = f"견적서를 읽지 못했습니다.\n{type(e).__name__}: {e}"
            messagebox.showerror("견적서 읽기 실패", msg, parent=self)
            return
        valid = result["data"]["valid_until"]
        if valid and dt.date.fromisoformat(valid) < dt.date.today():  # 유효일 당일까지는 유효
            answer = ask_choice(self, "견적서 유효일 지남",
                                f"{Path(job[0]).name}\n견적 유효일({valid})이 지났습니다.\n\n"
                                "다른 견적서를 고르거나, 이 견적서로 그냥 진행할 수 있습니다.",
                                ["다시 선택", "그냥 진행", "취소"])
            if answer == "다시 선택":
                self._choose_quote(job[1], job[2], "견적서 다시 선택")
                return
            if answer != "그냥 진행":  # 취소·창 닫음: 지금 입력은 그대로
                return
        self._apply_quote(job[0], result["data"])

    def _offer_step(self, job, title, question, starter, busy_text):
        """Claude Code 설치·로그인 창을 띄우고, 창이 닫히면 같은 견적서를 다시 읽음.
        다시 읽을 때 아직 준비가 안 됐으면(설치 실패, 로그인 안 함) 다시 물어봄"""
        if not messagebox.askyesno(title, question, parent=self):
            return
        try:
            from . import quote_reader
            proc = getattr(quote_reader, starter)()
        except Exception as e:
            messagebox.showerror(title, f"창을 열지 못했습니다.\n{e}", parent=self)
            return
        self._busy(busy_text)
        self._wait_step(proc, job)

    def _wait_step(self, proc, job):
        if proc.poll() is None:
            self.after(500, self._wait_step, proc, job)
            return
        self._busy("")
        self._start_quote(*job)

    def _apply_quote(self, path, data):
        """읽은 내용을 묻지 않고 바로 채움 (기존 견적내역은 지움 - 버튼 옆에 미리 안내). 확인할 점은 아래 줄에 표시"""
        items = data["items"]
        if not items:  # 채울 것이 없으면 지금 입력은 그대로 둠
            hint = "Claude Code 방식으로 다시 읽거나 " if get_setting("read_mode") == "local" else ""
            self._set_note(" / ".join([f"견적서에서 품목을 찾지 못했습니다. {hint}직접 입력해 주세요. "
                                                    "(지금 견적내역은 그대로입니다)"] + data["warnings"]))
            return

        if data["vendor"]:
            self.vendor_var.set(data["vendor"])
        if data["target"] and not self.target_var.get().strip():
            self.target_var.set(data["target"])
        self._clear_items()
        for it in items:
            self._insert_item(it)
        self._refresh()
        # 읽은 파일을 견적서 붙임으로 연결 (비어 있는 견적서 칸이 없으면 새로 추가)
        if not any(a["src"] == path for a in self.attaches.values()):
            slot = next((iid for iid in self.attach_tree.get_children()
                         if self.attaches[iid]["kind"] == "견적서" and not self.attaches[iid]["src"]), None)
            if slot:
                self.attaches[slot]["src"] = path
                self.attach_tree.item(slot, values=self._attach_values(self.attaches[slot]))
            else:
                self._insert_attach({"kind": "견적서", "name": "", "count": 1, "src": path})

        note = f"{Path(path).name} 불러옴: 견적처 {data['vendor'] or '(찾지 못함 - 직접 입력)'}, 품목 {len(items)}개"
        if data["valid_until"]:
            note += f", 유효일 {data['valid_until']}"
            if dt.date.fromisoformat(data["valid_until"]) < dt.date.today():
                note += " (지남)"
        if data["warnings"]:
            note += "\n확인할 점: " + " / ".join(data["warnings"])
        self._set_note(note)

    # ------------------------------------------------ 생성
    @staticmethod
    def _lines(text_widget):
        return [ln.strip() for ln in text_widget.get("1.0", "end").splitlines() if ln.strip()]

    def _collect(self):
        """입력 확인 후 (doc, items, attaches). 빠진 값이 있으면 None"""
        target = self.target_var.get().strip()
        vendor = self.vendor_var.get().strip()
        items = self._item_list()
        if not target:
            messagebox.showwarning("입력 확인", "구매대상을 입력하세요.")
            return None
        if not vendor:
            messagebox.showwarning("입력 확인", "견적처(기업명)를 입력하세요.")
            return None
        if not items:
            messagebox.showwarning("입력 확인", "견적내역을 1개 이상 추가하세요.")
            return None
        attaches = [self.attaches[iid] for iid in self.attach_tree.get_children()]
        doc = {
            "target": target,
            "title": self.title_var.get().strip() or f"{target} 구매의 건",
            "vendor": vendor,
            "payment": self.payment_var.get().strip(),
            "vat_note": self.vat_note_var.get(),
            "payment_detail": self._lines(self.detail_txt),
            "shop": self.shop_var.get().strip(),
            "attach": [self._attach_values(a)[0] for a in attaches],
        }
        return doc, items, attaches

    def copy_for_web(self):
        """하이웍스 등 웹 편집기에 붙여넣을 수 있게 정렬을 유지한 HTML로 복사"""
        collected = self._collect()
        if not collected:
            return
        doc, items, _ = collected
        try:
            from .html_doc import copy_html
            copy_html(doc, items)
        except Exception as e:  # 다른 프로그램이 클립보드를 쓰는 중 등
            messagebox.showerror("복사 실패", f"클립보드에 복사하지 못했습니다.\n{e}")
            return
        messagebox.showinfo("복사 완료", "품의서 내용을 복사했습니다.\n하이웍스 작성 화면에 Ctrl+V로 붙여넣으세요.\n"
                            "서식이 틀어지면 편집기의 HTML(소스) 모드에 붙여넣으세요.")

    def generate(self):
        collected = self._collect()
        if not collected:
            return
        doc, items, attaches = collected
        vendor = doc["vendor"]
        missing = [a["src"] for a in attaches if a["src"] and not Path(a["src"]).is_file()]
        if missing:
            messagebox.showerror("붙임 파일 없음", "다음 파일을 찾을 수 없습니다.\n" + "\n".join(missing))
            return

        save_dir = Path(self._save_dir())
        date = f"{dt.date.today():%y%m%d}"
        company_dir = output_dir(save_dir) / safe_filename(vendor)  # 저장 경로 안의 hidoc_output\기업명
        folder = company_dir / date
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("저장 실패", f"폴더를 만들 수 없습니다.\n{folder}\n{e}")
            return

        taken = set()
        path = unique_path(folder / f"[품의서]{safe_filename(vendor)}_{date}.hwp", taken)

        self.winfo_toplevel().config(cursor="watch")
        self.update()
        try:
            from .hwp_doc import build_hwp
            if not build_hwp(doc, items, path):
                messagebox.showerror("저장 실패", f"한글 파일을 저장하지 못했습니다.\n{path}")
                return
            copied = copy_attachments([(a["kind"], self._attach_name(a), a["src"], self._as_is(a)) for a in attaches],
                                      company_dir, folder, date, taken)
        except PermissionError as e:
            messagebox.showerror("저장 실패", f"파일이 열려 있어 저장할 수 없습니다.\n{e.filename}")
            return
        except Exception as e:  # 한글 미설치, 자동화 오류 등
            messagebox.showerror("한글 오류", "한글 문서를 만들 수 없습니다.\n"
                                 f"한컴오피스 한글이 설치되어 있는지 확인하세요.\n\n{e}")
            return
        finally:
            self.winfo_toplevel().config(cursor="")

        msg = f"생성되었습니다.\n{path}"
        if copied:
            msg += f"\n\n붙임 파일 ({company_dir.name} 폴더 기준):\n" + "\n".join(copied)
        if messagebox.askyesno("완료", msg + "\n\n폴더를 여시겠습니까?"):
            os.startfile(folder)

    def open_folder(self):
        folder = output_dir(self._save_dir())
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def reset(self):
        if not messagebox.askyesno("새로 작성", "입력한 내용을 모두 지울까요?"):
            return
        for var in (self.target_var, self.title_var, self.vendor_var, self.payment_var, self.shop_var):
            var.set("")
        self.vat_note_var.set(False)
        self._clear_items()
        self.detail_txt.delete("1.0", "end")
        self._reset_attach()
        self._set_note("")

