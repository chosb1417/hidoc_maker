"""구매 품의서 작성 화면 (메인 창 app.py 안에 들어가는 화면 조각)

구매 내용을 입력받아 한글(.hwp) 품의서 생성, 하이웍스용 복사, 견적서 불러오기를 함.
저장 폴더 구조는 storage.py 참고.
"""

import os
import datetime as dt
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

from .money import VAT_MODES, split_amount
from .quote_reader import READ_MODES, SHOWN_READ_MODES
from .settings import DEFAULT_SAVE_DIR, get_setting, output_dir, update_settings
from .storage import (attach_line, attach_types, company_folders, copy_attachments, copy_name, safe_filename,
                      unique_path)
from .widgets import add_placeholder, add_suggestions, ask_api_key, ask_choice

NOTICE_COLOR = "#b45309"  # 주황: 안내·확인할 점
QUOTE_FILETYPES = [("견적서", "*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff"), ("모든 파일", "*.*")]


# ---------------------------------------------------------------- GUI
class PurchaseRequestForm(ttk.Frame):
    ITEM_FIELDS = [("name", "품목", 34), ("qty", "수량", 6), ("price", "단가", 14), ("vat", "세액", 6), ("note", "비고", 12)]

    def __init__(self, master):
        super().__init__(master)
        self.target_var = tk.StringVar()
        self.title_var = tk.StringVar()
        self.vendor_var = tk.StringVar()
        self.payment_var = tk.StringVar()  # 비워 두면 품의서에서 4번 지급방식 항목을 뺌
        self.shop_var = tk.StringVar()  # 온라인 구매(쿠팡 등) 주소. 비워 두면 구매처 항목을 뺌
        self.vat_note_var = tk.BooleanVar(value=False)  # 견적금액 뒤 'VAT포함' 표기
        self.save_dir_var = tk.StringVar()
        self.read_mode_var = tk.StringVar()
        self.item_vars = {k: tk.StringVar() for k, _, _ in self.ITEM_FIELDS}
        self.item_vars["qty"].set("1")
        self.item_vars["vat"].set("별도")

        self._build_info()
        self._build_items()
        self._build_bottom()
        self.refresh_from_settings()

    def refresh_from_settings(self):
        """설정 탭에서 바꾼 값(저장 경로, 읽기 방식, 붙임 종류)을 반영. 메인 창이 이 화면을 보여 줄 때마다 부름"""
        self.save_dir_var.set(get_setting("save_dir"))
        mode_label = {v: k for k, v in READ_MODES.items()}.get(get_setting("read_mode"), "로컬 (무료)")
        self.read_mode_var.set(mode_label)
        self.attach_kind_box.config(values=attach_types())
        self._refresh_vendors()

    def _refresh_vendors(self):
        """견적처 드롭다운 목록 = 저장 경로\\hidoc_output 안의 기업 폴더"""
        self.vendor_box.config(values=company_folders(self.save_dir_var.get().strip() or DEFAULT_SAVE_DIR))

    def _build_info(self):
        frm = ttk.LabelFrame(self, text=" 기본 정보 ", padding=8)
        frm.pack(fill="x", padx=10, pady=(10, 5))
        rows = [
            ("구매대상", self.target_var, "예) G.Eye-Parking H100 Multi 설계 및 3대 제작 선금"),
            ("제목", self.title_var, "비워두면 '구매대상 + 구매의 건'으로 자동 작성"),
            ("견적처", self.vendor_var, "기업명 - ▼ 목록에서 기존 기업을 고르거나 새로 입력 (저장 폴더·붙임 파일 이름에 사용)"),
            ("지급방식", self.payment_var, f"예) {get_setting('payment_example')}  - 비워 두면 품의서에서 지급방식 항목을 뺌"),
            ("구매처", self.shop_var, "온라인 구매 주소(URL) 예) 쿠팡 장바구니 주소  - 비워 두면 품의서에서 구매처 항목을 뺌"),
        ]
        for i, (label, var, hint) in enumerate(rows):
            ttk.Label(frm, text=label, width=9).grid(row=i, column=0, sticky="w", pady=2)
            if var is self.vendor_var:
                # 직접 입력도 되는 드롭다운. 목록은 hidoc_output 안의 기업 폴더 (열 때마다 새로 읽음)
                entry = self.vendor_box = ttk.Combobox(frm, textvariable=var, postcommand=self._refresh_vendors)
                # 입력하는 동안에도 같은 글자가 들어간 기존 기업을 칸 아래에 보여 줌
                add_suggestions(entry, var, lambda: company_folders(self.save_dir_var.get().strip() or DEFAULT_SAVE_DIR))
            else:
                entry = ttk.Entry(frm, textvariable=var)
            entry.grid(row=i, column=1, columnspan=2, sticky="ew", pady=2)
            if hint:
                add_placeholder(entry, hint, var)
        frm.columnconfigure(1, weight=1)

        row = len(rows)
        ttk.Label(frm, text="견적서", width=9).grid(row=row, column=0, sticky="w", pady=(6, 2))
        quote = ttk.Frame(frm)
        quote.grid(row=row, column=1, sticky="w", pady=(6, 2))
        self.quote_btn = ttk.Button(quote, text="견적서 불러오기…", command=self.load_quote)
        self.quote_btn.pack(side="left")
        ttk.Label(quote, text="읽기 방식").pack(side="left", padx=(12, 4))
        mode = ttk.Combobox(quote, textvariable=self.read_mode_var, values=SHOWN_READ_MODES,
                            width=17, state="readonly")
        mode.pack(side="left")
        mode.bind("<<ComboboxSelected>>",
                  lambda _e: update_settings(read_mode=READ_MODES[self.read_mode_var.get()]))
        ttk.Label(frm, text="PDF·이미지에서 견적처와 품목을 읽어 채움", foreground="gray").grid(
            row=row, column=2, sticky="w", padx=8)
        # 아래 줄: 읽는 동안은 진행 막대 + 상태(_busy), 끝나면 불러온 결과·확인할 점 (확인 창 대신)
        note_row = ttk.Frame(frm)
        note_row.grid(row=row + 1, column=1, columnspan=2, sticky="w")
        self.quote_progress = ttk.Progressbar(note_row, mode="indeterminate", length=120)
        self.quote_note = ttk.Label(note_row, foreground=NOTICE_COLOR, justify="left", wraplength=860)
        self.quote_note.pack(side="left")

    def _build_items(self):
        frm = ttk.LabelFrame(self, text=" 견적내역 ", padding=8)
        frm.pack(fill="both", expand=True, padx=10, pady=5)

        entry_row = ttk.Frame(frm)
        entry_row.pack(fill="x")
        for i, (key, label, width) in enumerate(self.ITEM_FIELDS):
            ttk.Label(entry_row, text=label).grid(row=0, column=i, sticky="w")
            if key == "vat":
                e = ttk.Combobox(entry_row, textvariable=self.item_vars[key], values=VAT_MODES,
                                 width=width, state="readonly")
            else:
                e = ttk.Entry(entry_row, textvariable=self.item_vars[key], width=width)
                e.bind("<Return>", lambda _e: self.add_item())
            e.grid(row=1, column=i, padx=(0, 4), sticky="ew")
            if key == "name":
                self.name_entry = e
        entry_row.columnconfigure(0, weight=1)
        btns = ttk.Frame(entry_row)
        btns.grid(row=1, column=len(self.ITEM_FIELDS), padx=(6, 0))
        ttk.Button(btns, text="추가", width=6, command=self.add_item).pack(side="left")
        ttk.Button(btns, text="수정", width=6, command=self.update_item).pack(side="left", padx=2)
        ttk.Button(btns, text="삭제", width=6, command=self.delete_item).pack(side="left")

        cols = ["name", "qty", "price", "vat", "supply", "tax", "total", "note"]
        heads = ["품목", "수량", "단가", "세액구분", "공급가액", "세액", "합계", "비고"]
        widths = [230, 50, 100, 70, 100, 90, 110, 100]
        tree_frm = ttk.Frame(frm)
        tree_frm.pack(fill="both", expand=True, pady=(8, 0))
        self.tree = ttk.Treeview(tree_frm, columns=cols, show="headings", height=6)
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor={"name": "w", "note": "w", "vat": "center"}.get(c, "e"))
        sb = ttk.Scrollbar(tree_frm, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.items: dict[str, dict] = {}  # tree iid -> item

        sum_row = ttk.Frame(frm)
        sum_row.pack(fill="x", pady=(6, 0))
        ttk.Label(sum_row, text="세액: 별도 = 단가+10% / 포함 = 단가에 부가세 포함 / 없음 = 면세",
                  foreground="gray").pack(side="left")
        self.total_lbl = ttk.Label(sum_row, font=("맑은 고딕", 10, "bold"))
        self.total_lbl.pack(side="right")
        ttk.Checkbutton(sum_row, text="견적금액에 'VAT포함' 표기", variable=self.vat_note_var).pack(side="right", padx=12)
        self._refresh()

    def _build_bottom(self):
        frm = ttk.Frame(self)
        frm.pack(fill="x", padx=10, pady=5)
        left = ttk.LabelFrame(frm, text=" 지급방식 상세 (한 줄에 하나) ", padding=6)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.detail_txt = tk.Text(left, height=5, width=20, font=("맑은 고딕", 10))
        self.detail_txt.pack(fill="both", expand=True)
        add_placeholder(self.detail_txt, "예) 발주 시 선금 50% 지급\n     출고 시 잔금 50% 지급\n     지급방식 내용은 견적서에 기재")

        right = ttk.LabelFrame(frm, text=" 붙임 (마지막 줄에 '끝.' 자동) ", padding=6)
        right.grid(row=0, column=1, sticky="nsew")
        frm.columnconfigure(0, weight=1, uniform="bottom")
        frm.columnconfigure(1, weight=2, uniform="bottom")
        self._build_attach(right)

        path_row = ttk.Frame(self, padding=(10, 5, 10, 0))
        path_row.pack(fill="x")
        ttk.Label(path_row, text="저장 경로").pack(side="left")
        ttk.Entry(path_row, textvariable=self.save_dir_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(path_row, text="찾아보기", command=self.choose_save_dir).pack(side="left")
        ttk.Label(path_row, text="→ 저장경로\\hidoc_output\\기업명\\ 폴더에 저장", foreground="gray").pack(side="left", padx=(8, 0))

        bar = ttk.Frame(self, padding=(10, 5, 10, 10))
        bar.pack(fill="x")
        ttk.Button(bar, text="저장 폴더 열기", command=self.open_folder).pack(side="left")
        ttk.Button(bar, text="새로 작성", command=self.reset).pack(side="left", padx=6)
        ttk.Button(bar, text="한글 생성", command=self.generate).pack(side="right", ipadx=20, ipady=4)
        ttk.Button(bar, text="하이웍스용 복사", command=self.copy_for_web).pack(side="right", padx=6, ipady=4)

    def _build_attach(self, parent):
        self.attach_kind = tk.StringVar(value=attach_types()[0])
        self.attach_name = tk.StringVar()
        self.attach_count = tk.StringVar(value="1")
        self.attach_src = tk.StringVar()

        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Label(row, text="종류").grid(row=0, column=0, sticky="w")
        ttk.Label(row, text="이름 (비우면 기업명)").grid(row=0, column=1, sticky="w")
        ttk.Label(row, text="부수").grid(row=0, column=2, sticky="w")
        # 목록에 없는 종류도 직접 입력 가능
        self.attach_kind_box = ttk.Combobox(row, textvariable=self.attach_kind, values=attach_types(), width=13)
        self.attach_kind_box.grid(row=1, column=0, padx=(0, 4))
        ttk.Entry(row, textvariable=self.attach_name, width=30).grid(row=1, column=1, padx=(0, 4), sticky="ew")
        ttk.Spinbox(row, textvariable=self.attach_count, from_=1, to=99, width=3).grid(row=1, column=2, sticky="w")
        ttk.Label(row, text="파일 - 목록에서 항목을 고르고 [파일…] 또는 항목 더블클릭").grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Entry(row, textvariable=self.attach_src, state="readonly").grid(row=3, column=0, columnspan=2, sticky="ew", padx=(0, 4))
        btns = ttk.Frame(row)
        btns.grid(row=3, column=2, sticky="w")
        ttk.Button(btns, text="파일…", width=5, command=self.choose_attach_file).pack(side="left")
        ttk.Button(btns, text="추가", width=5, command=self.add_attach).pack(side="left", padx=(6, 0))
        ttk.Button(btns, text="수정", width=5, command=self.update_attach).pack(side="left", padx=2)
        ttk.Button(btns, text="삭제", width=5, command=self.delete_attach).pack(side="left")
        ttk.Button(btns, text="비우기", width=6, command=self.clear_attach).pack(side="left", padx=(6, 0))
        row.columnconfigure(1, weight=1)

        self.attach_tree = ttk.Treeview(parent, columns=("line", "src"), show="headings", height=5)
        self.attach_tree.heading("line", text="붙임 표기")
        self.attach_tree.heading("src", text="첨부 파일 (원본 → 복사될 이름)")
        self.attach_tree.column("line", width=190)
        self.attach_tree.column("src", width=330)
        self.attach_tree.pack(fill="both", expand=True, pady=(6, 0))
        self.attach_tree.bind("<<TreeviewSelect>>", self._on_attach_select)
        self.attach_tree.bind("<Double-1>", self.choose_attach_file)
        self.attaches: dict[str, dict] = {}  # tree iid -> {kind, name, count, src}. 처음에는 비어 있음
        self.vendor_var.trace_add("write", lambda *_: self._refresh_attach())

    def _attach_name(self, a):
        return a["name"] or self.vendor_var.get().strip()

    def _copy_name(self, a, date):
        return copy_name(a["kind"], self._attach_name(a), a["src"], date)

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

    def _read_attach(self):
        kind = self.attach_kind.get().strip()
        if not kind:
            messagebox.showwarning("입력 확인", "붙임 문서 종류를 선택하세요.")
            return None
        try:
            count = max(1, int(self.attach_count.get()))
        except ValueError:
            count = 1
        return {"kind": kind, "name": self.attach_name.get().strip(), "count": count, "src": self.attach_src.get()}

    def _clear_attach_entry(self):
        self.attach_name.set("")
        self.attach_count.set("1")
        self.attach_src.set("")

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
            messagebox.showinfo("수정", "수정할 붙임을 목록에서 선택하세요.")
            return
        a = self._read_attach()
        if a:
            self.attaches[sel[0]] = a
            self._refresh_attach()
            self.attach_tree.selection_remove(sel)
            self._clear_attach_entry()

    def _reset_attach(self):
        """붙임 목록을 비우고 입력칸을 처음 상태로"""
        self.attach_tree.delete(*self.attach_tree.get_children())
        self.attaches.clear()
        self.attach_kind.set(attach_types()[0])
        self._clear_attach_entry()

    def clear_attach(self):
        if self.attaches and messagebox.askyesno("붙임 비우기", "붙임 목록을 모두 지울까요?"):
            self.attach_tree.delete(*self.attach_tree.get_children())
            self.attaches.clear()
            self._clear_attach_entry()

    def delete_attach(self):
        for iid in self.attach_tree.selection():
            self.attach_tree.delete(iid)
            self.attaches.pop(iid, None)
        self._refresh_attach()
        self._clear_attach_entry()

    def _on_attach_select(self, _e):
        sel = self.attach_tree.selection()
        if sel:
            a = self.attaches[sel[0]]
            self.attach_kind.set(a["kind"])
            self.attach_name.set(a["name"])
            self.attach_count.set(str(a["count"]))
            self.attach_src.set(a["src"])

    # ------------------------------------------------ 품목 조작
    def _read_item(self):
        d = {k: v.get().strip() for k, v in self.item_vars.items()}
        if not d["name"]:
            messagebox.showwarning("입력 확인", "품목을 입력하세요.")
            return None
        try:
            d["qty"] = int(d["qty"].replace(",", ""))
            d["price"] = int(d["price"].replace(",", ""))
            if d["qty"] <= 0 or d["price"] < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("입력 확인", "수량과 단가는 숫자로 입력하세요.")
            return None
        return d

    def _row_values(self, d):
        supply, tax = split_amount(d["qty"], d["price"], d["vat"])
        return (d["name"], f"{d['qty']:,}", f"{d['price']:,}", d["vat"], f"{supply:,}", f"{tax:,}",
                f"{supply + tax:,}", d["note"])

    def _clear_item_entry(self):
        for k, v in self.item_vars.items():
            v.set({"qty": "1", "vat": "별도"}.get(k, ""))
        self.name_entry.focus_set()

    def add_item(self):
        d = self._read_item()
        if d:
            iid = self.tree.insert("", "end", values=self._row_values(d))
            self.items[iid] = d
            self._clear_item_entry()
            self._refresh()

    def update_item(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("수정", "수정할 품목을 목록에서 선택하세요.")
            return
        d = self._read_item()
        if d:
            self.items[sel[0]] = d
            self.tree.selection_remove(sel)
            self._clear_item_entry()
            self._refresh()

    def delete_item(self):
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self.items.pop(iid, None)
        self._clear_item_entry()
        self._refresh()

    def _on_select(self, _e):
        sel = self.tree.selection()
        if sel:
            for k, v in self.items[sel[0]].items():
                self.item_vars[k].set(str(v))

    def _item_list(self):
        return [self.items[iid] for iid in self.tree.get_children()]

    def _refresh(self):
        for iid in self.tree.get_children():
            self.tree.item(iid, values=self._row_values(self.items[iid]))
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
        mode = READ_MODES[self.read_mode_var.get()]
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
            self.quote_note.config(text=text, foreground="gray")
        else:
            self.quote_progress.stop()
            self.quote_progress.pack_forget()
            self.quote_note.config(text="", foreground=NOTICE_COLOR)

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
            hint = "Claude Code 방식으로 다시 읽거나 " if READ_MODES[self.read_mode_var.get()] == "local" else ""
            self.quote_note.config(text=" / ".join([f"견적서에서 품목을 찾지 못했습니다. {hint}직접 입력해 주세요. "
                                                    "(지금 견적내역은 그대로입니다)"] + data["warnings"]))
            return

        if data["vendor"]:
            self.vendor_var.set(data["vendor"])
        if data["target"] and not self.target_var.get().strip():
            self.target_var.set(data["target"])
        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        for it in items:
            iid = self.tree.insert("", "end", values=self._row_values(it))
            self.items[iid] = it
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
        self.quote_note.config(text=note)

    # ------------------------------------------------ 생성
    @staticmethod
    def _lines(text_widget):
        return [ln.strip() for ln in text_widget.get("1.0", "end").splitlines() if ln.strip()]

    def choose_save_dir(self):
        path = filedialog.askdirectory(title="저장 경로 선택", initialdir=self.save_dir_var.get())
        if path:
            self.save_dir_var.set(path)

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

        save_dir = Path(self.save_dir_var.get().strip() or DEFAULT_SAVE_DIR)
        date = f"{dt.date.today():%y%m%d}"
        company_dir = output_dir(save_dir) / safe_filename(vendor)  # 저장 경로 안의 hidoc_output\기업명
        folder = company_dir / date
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("저장 실패", f"폴더를 만들 수 없습니다.\n{folder}\n{e}")
            return
        update_settings(save_dir=str(save_dir))

        taken = set()
        path = unique_path(folder / f"[품의서]{safe_filename(vendor)}_{date}.hwp", taken)

        self.winfo_toplevel().config(cursor="watch")
        self.update()
        try:
            from .hwp_doc import build_hwp
            if not build_hwp(doc, items, path):
                messagebox.showerror("저장 실패", f"한글 파일을 저장하지 못했습니다.\n{path}")
                return
            copied = copy_attachments([(a["kind"], self._attach_name(a), a["src"]) for a in attaches],
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
        folder = output_dir(self.save_dir_var.get().strip() or DEFAULT_SAVE_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def reset(self):
        if not messagebox.askyesno("새로 작성", "입력한 내용을 모두 지울까요?"):
            return
        for var in (self.target_var, self.title_var, self.vendor_var, self.payment_var, self.shop_var):
            var.set("")
        self.vat_note_var.set(False)
        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        self._clear_item_entry()
        self._refresh()
        self.detail_txt.delete("1.0", "end")
        self._reset_attach()
        self.quote_note.config(text="")

