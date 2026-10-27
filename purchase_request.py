"""hidoc maker - 품의서 한글(HWP) 생성기 (tkinter GUI, 한컴오피스 필요)

실행: python purchase_request.py  (또는 실행.bat 더블클릭)
결과: 저장경로/기업명/
        [사업자등록증]기업명.확장자, [통장사본]기업명.확장자   (기업 공통 서류)
        YYMMDD/[품의서]기업명_YYMMDD.hwp, [견적서]기업명_YYMMDD.확장자 ...
"""

import json
import os
import re
import shutil
import datetime as dt
import filecmp
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DEFAULT_SAVE_DIR = APP_DIR / "output"
SETTINGS_PATH = APP_DIR / "settings.json"
VAT_RATE = 0.1
# 품목별 세액 처리: 별도 = 단가에 10% 추가 / 포함 = 단가에 부가세 포함 / 없음 = 면세
VAT_MODES = ["별도", "포함", "없음"]
# 견적서 읽기 방식: 화면 표시 -> quote_reader 의 mode
READ_MODES = {"로컬 (무료)": "local", "Claude API": "claude"}
QUOTE_FILETYPES = [("견적서", "*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff"), ("모든 파일", "*.*")]


def split_amount(qty: int, price: int, mode: str) -> tuple[int, int]:
    """한 품목의 (공급가액, 세액)"""
    amount = qty * price
    if mode == "별도":
        return amount, round(amount * VAT_RATE)
    if mode == "포함":
        supply = round(amount / (1 + VAT_RATE))
        return supply, amount - supply
    return amount, 0
ATTACH_TYPES = ["사업자등록증", "통장사본", "견적서", "거래명세서", "전자세금계산서", "계약서", "발주서", "검수확인서"]
DEFAULT_ATTACH = ["사업자등록증", "통장사본", "견적서", "거래명세서", "전자세금계산서"]
# 기업 폴더 바로 아래에 날짜 없이 저장하는 기업 공통 서류
COMPANY_DOCS = {"사업자등록증", "통장사본"}


def attach_line(kind: str, name: str, count: int) -> str:
    """('견적서', '엠에스산업', 1) -> '[견적서]엠에스산업 1부.'"""
    return f"[{kind}]{name} {count}부."


# ---------------------------------------------------------------- 문자열 도우미
def won_to_korean(amount: int) -> str:
    """4125000 -> '사백일십이만오천'"""
    if amount == 0:
        return "영"
    digits = "영일이삼사오육칠팔구"
    small = ["", "십", "백", "천"]
    big = ["", "만", "억", "조", "경"]
    result = []
    group = 0
    while amount > 0:
        chunk = amount % 10000
        amount //= 10000
        if chunk:
            text = ""
            for i in range(3, -1, -1):
                d = (chunk // 10 ** i) % 10
                if d:
                    text += digits[d] + small[i]
            result.insert(0, text + big[group])
        group += 1
    return "".join(result)


def eul_reul(word: str) -> str:
    """마지막 글자 받침에 맞는 목적격 조사"""
    last = word.rstrip()[-1:] or " "
    if "가" <= last <= "힣":
        return "을" if (ord(last) - 0xAC00) % 28 else "를"
    if last.isdigit():
        return "을" if last in "013678" else "를"
    return "을(를)"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(data: dict):
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def unique_path(path: Path, taken: set) -> Path:
    """이미 있는 파일이거나 이번에 쓴 이름이면 (2), (3)... 을 붙임"""
    n, cand = 2, path
    while cand in taken or cand.exists():
        cand = path.with_name(f"{path.stem}({n}){path.suffix}")
        n += 1
    taken.add(cand)
    return cand


def safe_filename(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", text).strip("_")[:40] or "제목없음"


# ---------------------------------------------------------------- GUI
class App(tk.Tk):
    ITEM_FIELDS = [("name", "품목", 34), ("qty", "수량", 6), ("price", "단가", 14), ("vat", "세액", 6), ("note", "비고", 12)]

    def __init__(self):
        super().__init__()
        self.title("hidoc maker")
        self.geometry("1000x840")
        self.minsize(920, 680)
        style = ttk.Style(self)
        style.configure(".", font=("맑은 고딕", 10))
        style.configure("Treeview.Heading", font=("맑은 고딕", 10, "bold"))

        self.target_var = tk.StringVar()
        self.title_var = tk.StringVar()
        self.vendor_var = tk.StringVar()
        self.payment_var = tk.StringVar(value="선금 50% , 잔금 50%")
        self.vat_note_var = tk.BooleanVar(value=False)  # 견적금액 뒤 'VAT포함' 표기
        settings = load_settings()
        self.save_dir_var = tk.StringVar(value=settings.get("save_dir", str(DEFAULT_SAVE_DIR)))
        mode_label = {v: k for k, v in READ_MODES.items()}.get(settings.get("read_mode"), "로컬 (무료)")
        self.read_mode_var = tk.StringVar(value=mode_label)
        self.item_vars = {k: tk.StringVar() for k, _, _ in self.ITEM_FIELDS}
        self.item_vars["qty"].set("1")
        self.item_vars["vat"].set("별도")

        self._build_info()
        self._build_items()
        self._build_bottom()

    def _build_info(self):
        frm = ttk.LabelFrame(self, text=" 기본 정보 ", padding=8)
        frm.pack(fill="x", padx=10, pady=(10, 5))
        rows = [
            ("구매대상", self.target_var, "예) G.Eye-Parking H100 Multi 설계 및 3대 제작 선금"),
            ("제목", self.title_var, "비워두면 '구매대상 + 구매의 건'으로 자동 작성"),
            ("견적처", self.vendor_var, "기업명 - 저장 폴더와 붙임 파일 이름에 사용"),
            ("지급방식", self.payment_var, ""),
        ]
        for i, (label, var, hint) in enumerate(rows):
            ttk.Label(frm, text=label, width=9).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Entry(frm, textvariable=var).grid(row=i, column=1, sticky="ew", pady=2)
            ttk.Label(frm, text=hint, foreground="gray").grid(row=i, column=2, sticky="w", padx=8)
        frm.columnconfigure(1, weight=1)

        row = len(rows)
        ttk.Label(frm, text="견적서", width=9).grid(row=row, column=0, sticky="w", pady=(6, 2))
        quote = ttk.Frame(frm)
        quote.grid(row=row, column=1, sticky="w", pady=(6, 2))
        self.quote_btn = ttk.Button(quote, text="견적서 불러오기…", command=self.load_quote)
        self.quote_btn.pack(side="left")
        ttk.Label(quote, text="읽기 방식").pack(side="left", padx=(12, 4))
        mode = ttk.Combobox(quote, textvariable=self.read_mode_var, values=list(READ_MODES),
                            width=12, state="readonly")
        mode.pack(side="left")
        mode.bind("<<ComboboxSelected>>",
                  lambda _e: save_settings({**load_settings(), "read_mode": READ_MODES[self.read_mode_var.get()]}))
        ttk.Button(quote, text="API 키…", command=self.set_api_key).pack(side="left", padx=(6, 0))
        self.quote_status = ttk.Label(quote, foreground="gray")
        self.quote_status.pack(side="left", padx=8)
        ttk.Label(frm, text="PDF·이미지에서 견적처와 품목을 읽어 채움", foreground="gray").grid(
            row=row, column=2, sticky="w", padx=8)

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
        self.detail_txt.insert("1.0", "발주 시 선금 50% 지급\n출고 시 잔금 50% 지급\n지급방식 내용은 견적서에 기재")

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
        ttk.Label(path_row, text="→ 저장경로\\기업명\\ 폴더에 저장", foreground="gray").pack(side="left", padx=(8, 0))

        bar = ttk.Frame(self, padding=(10, 5, 10, 10))
        bar.pack(fill="x")
        ttk.Button(bar, text="저장 폴더 열기", command=self.open_folder).pack(side="left")
        ttk.Button(bar, text="새로 작성", command=self.reset).pack(side="left", padx=6)
        ttk.Button(bar, text="한글 생성", command=self.generate).pack(side="right", ipadx=20, ipady=4)
        ttk.Button(bar, text="하이웍스용 복사", command=self.copy_for_web).pack(side="right", padx=6, ipady=4)

    def _build_attach(self, parent):
        self.attach_kind = tk.StringVar(value=ATTACH_TYPES[0])
        self.attach_name = tk.StringVar()
        self.attach_count = tk.StringVar(value="1")
        self.attach_src = tk.StringVar()

        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Label(row, text="종류").grid(row=0, column=0, sticky="w")
        ttk.Label(row, text="이름 (비우면 기업명)").grid(row=0, column=1, sticky="w")
        ttk.Label(row, text="부수").grid(row=0, column=2, sticky="w")
        # 목록에 없는 종류도 직접 입력 가능
        ttk.Combobox(row, textvariable=self.attach_kind, values=ATTACH_TYPES, width=13).grid(row=1, column=0, padx=(0, 4))
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
        self.attaches: dict[str, dict] = {}  # tree iid -> {kind, name, count, src}
        self._load_default_attach()
        self.vendor_var.trace_add("write", lambda *_: self._refresh_attach())

    def _attach_name(self, a):
        return a["name"] or self.vendor_var.get().strip()

    def _copy_name(self, a, date):
        """복사될 파일 이름: 기업 공통 서류는 [종류]기업명.확장자, 나머지는 [종류]기업명_YYMMDD.확장자"""
        name = f"[{a['kind']}]{safe_filename(self._attach_name(a))}"
        if a["kind"] not in COMPANY_DOCS:
            name += f"_{date}"
        return name + Path(a["src"]).suffix

    def _attach_values(self, a):
        line = attach_line(a["kind"], self._attach_name(a), a["count"])
        if not a["src"]:
            return line, ""
        return line, f"{Path(a['src']).name}  →  {self._copy_name(a, f'{dt.date.today():%y%m%d}')}"

    def _insert_attach(self, a):
        iid = self.attach_tree.insert("", "end", values=self._attach_values(a))
        self.attaches[iid] = a

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
        path = filedialog.askopenfilename(title=title, parent=self)
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
            self.attach_tree.item(sel[0], values=self._attach_values(a))
            self.attach_tree.selection_remove(sel)
            self._clear_attach_entry()

    def _load_default_attach(self):
        self.attach_tree.delete(*self.attach_tree.get_children())
        self.attaches.clear()
        for kind in DEFAULT_ATTACH:
            self._insert_attach({"kind": kind, "name": "", "count": 1, "src": ""})
        self.attach_kind.set(ATTACH_TYPES[0])
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
    def set_api_key(self):
        """Claude API 키를 settings.json 에 저장. 저장했으면 True"""
        key = simpledialog.askstring(
            "Claude API 키", "Claude API 키를 붙여 넣으세요. (sk-ant-…)\n"
            "키는 이 PC의 settings.json 에만 저장되고 git에는 올라가지 않습니다.\n"
            "비워 두고 확인을 누르면 저장된 키를 지웁니다.", show="*", parent=self)
        if key is None:
            return False
        save_settings({**load_settings(), "anthropic_api_key": key.strip()})
        return bool(key.strip())

    def load_quote(self):
        mode = READ_MODES[self.read_mode_var.get()]
        api_key = load_settings().get("anthropic_api_key", "")
        if mode == "claude" and not (api_key or os.environ.get("ANTHROPIC_API_KEY")):
            messagebox.showinfo("API 키 필요", "Claude API 방식은 API 키가 필요합니다.", parent=self)
            if not self.set_api_key():
                return
            api_key = load_settings().get("anthropic_api_key", "")
        path = filedialog.askopenfilename(title="견적서 선택", filetypes=QUOTE_FILETYPES, parent=self)
        if not path:
            return

        # 읽는 동안 창이 멈추지 않도록 따로 실행하고 끝날 때까지 확인
        result = {}

        def work():
            try:
                from quote_reader import read_quote
                result["data"] = read_quote(path, mode, api_key)
            except Exception as e:  # QuoteReadError 는 안내문, 그 밖은 예상 못 한 오류
                result["error"] = e

        self.quote_btn.state(["disabled"])
        self.quote_status.config(text="읽는 중…")
        self.config(cursor="watch")
        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        self._wait_quote(thread, path, result)

    def _wait_quote(self, thread, path, result):
        if thread.is_alive():
            self.after(200, self._wait_quote, thread, path, result)
            return
        self.quote_btn.state(["!disabled"])
        self.quote_status.config(text="")
        self.config(cursor="")
        if "error" in result:
            e = result["error"]
            if type(e).__name__ == "QuoteReadError":
                msg = str(e)
            elif isinstance(e, ImportError):
                msg = f"견적서 읽기에 필요한 패키지가 없습니다. 실행.bat으로 다시 실행해 주세요.\n{e}"
            else:
                msg = f"견적서를 읽지 못했습니다.\n{type(e).__name__}: {e}"
            messagebox.showerror("견적서 읽기 실패", msg, parent=self)
            return
        self._apply_quote(path, result["data"])

    def _apply_quote(self, path, data):
        items = data["items"]
        if not items:
            hint = "Claude API 방식으로 다시 읽거나 " if READ_MODES[self.read_mode_var.get()] == "local" else ""
            messagebox.showwarning("견적서 읽기", f"견적서에서 품목을 찾지 못했습니다.\n{hint}직접 입력해 주세요.\n\n"
                                   + "\n".join(data["warnings"]), parent=self)
            return
        lines = [f"견적처 : {data['vendor'] or '(찾지 못함)'}"]
        if data["target"]:
            lines.append(f"구매대상 : {data['target']}")
        lines.append(f"품목 {len(items)}개")
        lines += [f"  {it['name']}  {it['qty']:,} x {it['price']:,}원 ({it['vat']})" for it in items[:10]]
        if len(items) > 10:
            lines.append(f"  … 외 {len(items) - 10}개")
        if data["warnings"]:
            lines += ["", "확인할 점"] + [f"  - {w}" for w in data["warnings"]]
        if self.items:
            lines += ["", "지금 입력된 견적내역은 지우고 새로 채웁니다."]
        if not messagebox.askyesno("견적서 읽기 결과", "\n".join(lines) + "\n\n입력창에 채울까요?", parent=self):
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
            from html_doc import copy_html
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
        company_dir = save_dir / safe_filename(vendor)
        folder = company_dir / date
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("저장 실패", f"폴더를 만들 수 없습니다.\n{folder}\n{e}")
            return
        save_settings({**load_settings(), "save_dir": str(save_dir)})

        taken = set()
        path = unique_path(folder / f"[품의서]{safe_filename(vendor)}_{date}.hwp", taken)

        self.config(cursor="watch")
        self.update()
        try:
            from hwp_doc import build_hwp
            if not build_hwp(doc, items, path):
                messagebox.showerror("저장 실패", f"한글 파일을 저장하지 못했습니다.\n{path}")
                return
            # 기업 공통 서류는 기업 폴더에 [종류]기업명.확장자, 나머지는 날짜 폴더에 [종류]기업명_날짜.확장자
            copied = []
            for a in attaches:
                if not a["src"]:
                    continue
                src = Path(a["src"])
                if a["kind"] in COMPANY_DOCS:
                    dest = company_dir / self._copy_name(a, date)
                    if dest.exists() and filecmp.cmp(src, dest, shallow=False):
                        copied.append(f"{dest.relative_to(company_dir)} (같은 파일이 있어 유지)")
                        continue
                    dest = unique_path(dest, taken)
                else:
                    dest = unique_path(folder / self._copy_name(a, date), taken)
                shutil.copy2(src, dest)
                copied.append(str(dest.relative_to(company_dir)))
        except PermissionError as e:
            messagebox.showerror("저장 실패", f"파일이 열려 있어 저장할 수 없습니다.\n{e.filename}")
            return
        except Exception as e:  # 한글 미설치, 자동화 오류 등
            messagebox.showerror("한글 오류", "한글 문서를 만들 수 없습니다.\n"
                                 f"한컴오피스 한글이 설치되어 있는지 확인하세요.\n\n{e}")
            return
        finally:
            self.config(cursor="")

        msg = f"생성되었습니다.\n{path}"
        if copied:
            msg += f"\n\n붙임 파일 ({company_dir.name} 폴더 기준):\n" + "\n".join(copied)
        if messagebox.askyesno("완료", msg + "\n\n폴더를 여시겠습니까?"):
            os.startfile(folder)

    def open_folder(self):
        save_dir = Path(self.save_dir_var.get().strip() or DEFAULT_SAVE_DIR)
        save_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(save_dir)

    def reset(self):
        if not messagebox.askyesno("새로 작성", "입력한 내용을 모두 지울까요?"):
            return
        for var in (self.target_var, self.title_var, self.vendor_var):
            var.set("")
        self.vat_note_var.set(False)
        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        self._clear_item_entry()
        self._refresh()
        self._load_default_attach()


if __name__ == "__main__":
    App().mainloop()
