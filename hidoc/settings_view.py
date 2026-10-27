"""첫 화면의 '설정' 탭: 파일 경로(입출력), 견적서 읽기·Claude, 환경 점검

여기서 바꾼 값은 바로 settings.json 에 저장되고, 문서 작성 화면을 열 때 반영됨.
회사 이름·지급방식 기본값·붙임 종류 같은 값은 화면에 두지 않고 기본값을 씀(settings.py 의 DEFAULTS).
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from .environment import run_checks
from .quote_reader import READ_MODES
from .settings import get_setting, update_settings
from .widgets import ask_api_key

LABEL_WIDTH = 22
OK_COLOR = "#15803d"  # 초록
WARN_COLOR = "#b45309"  # 주황

# (설정 키, 이름, 설명)
PATH_SETTINGS = [
    ("save_dir", "저장 경로 (출력)", "이 폴더 안에 hidoc_output\\기업명\\날짜 폴더를 만들어 품의서와 붙임 파일을 저장"),
    ("quote_dir", "견적서 폴더 (입력)", "견적서 불러오기 창이 처음 열릴 폴더"),
    ("attach_dir", "붙임 파일 폴더 (입력)", "붙임 파일 선택 창이 처음 열릴 폴더"),
]


class SettingsView(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=12)
        self.path_vars = {}
        self.env_rows = {}
        self.checking = False
        self._build_paths()
        self._build_quote()
        self._build_env()

    # ------------------------------------------------ 파일 경로
    def _build_paths(self):
        frm = ttk.LabelFrame(self, text=" 파일 경로 ", padding=10)
        frm.pack(fill="x", pady=(0, 8))
        for i, (key, label, desc) in enumerate(PATH_SETTINGS):
            var = tk.StringVar()
            self.path_vars[key] = var
            ttk.Label(frm, text=label, width=LABEL_WIDTH).grid(row=i * 2, column=0, sticky="w", pady=(4, 0))
            entry = ttk.Entry(frm, textvariable=var)
            entry.grid(row=i * 2, column=1, sticky="ew", pady=(4, 0))
            entry.bind("<FocusOut>", lambda _e, k=key: self._save_path(k))
            entry.bind("<Return>", lambda _e, k=key: self._save_path(k))
            ttk.Button(frm, text="찾아보기…", command=lambda k=key: self._browse(k)).grid(
                row=i * 2, column=2, padx=(6, 0), pady=(4, 0))
            ttk.Label(frm, text=desc, foreground="gray").grid(row=i * 2 + 1, column=1, sticky="w")
        frm.columnconfigure(1, weight=1)

    def _browse(self, key):
        path = filedialog.askdirectory(title="폴더 선택", initialdir=self.path_vars[key].get(), parent=self)
        if path:
            self.path_vars[key].set(path)
            self._save_path(key)

    def _save_path(self, key):
        update_settings(**{key: self.path_vars[key].get().strip()})
        self.path_vars[key].set(get_setting(key))  # 비우면 기본 폴더로 돌아감

    # ------------------------------------------------ 견적서 읽기·Claude
    def _build_quote(self):
        frm = ttk.LabelFrame(self, text=" 견적서 읽기·Claude ", padding=10)
        frm.pack(fill="x", pady=(0, 8))

        ttk.Label(frm, text="기본 읽기 방식", width=LABEL_WIDTH).grid(row=0, column=0, sticky="w", pady=3)
        self.mode_var = tk.StringVar()
        mode = ttk.Combobox(frm, textvariable=self.mode_var, values=list(READ_MODES), width=20, state="readonly")
        mode.grid(row=0, column=1, sticky="w", pady=3)
        mode.bind("<<ComboboxSelected>>", lambda _e: update_settings(read_mode=READ_MODES[self.mode_var.get()]))
        ttk.Label(frm, text="로컬: 무료, 외부 전송 없음 / Claude Code: 각자 Claude 구독(Team) 사용 / "
                            "Claude API: API 키 필요, 장당 100원 안팎", foreground="gray").grid(
            row=1, column=1, columnspan=3, sticky="w")

        ttk.Label(frm, text="Claude API 키", width=LABEL_WIDTH).grid(row=2, column=0, sticky="w", pady=(8, 3))
        self.key_lbl = ttk.Label(frm)
        self.key_lbl.grid(row=2, column=1, sticky="w", pady=(8, 3))
        keys = ttk.Frame(frm)
        keys.grid(row=2, column=2, sticky="w", pady=(8, 3))
        ttk.Button(keys, text="입력…", command=self._set_key).pack(side="left")
        ttk.Button(keys, text="삭제", command=self._delete_key).pack(side="left", padx=(4, 0))

        ttk.Label(frm, text="Claude Code", width=LABEL_WIDTH).grid(row=3, column=0, sticky="w", pady=3)
        self.cc_lbl = ttk.Label(frm, text="확인 중…")
        self.cc_lbl.grid(row=3, column=1, sticky="w", pady=3)
        cc = ttk.Frame(frm)
        cc.grid(row=3, column=2, sticky="w", pady=3)
        ttk.Button(cc, text="설치", command=lambda: self._run_step("start_claude_code_install")).pack(side="left")
        ttk.Button(cc, text="로그인", command=lambda: self._run_step("start_claude_code_login")).pack(
            side="left", padx=(4, 0))
        frm.columnconfigure(1, weight=1)

    def _refresh_key(self):
        key = get_setting("anthropic_api_key")
        self.key_lbl.config(text=f"저장됨 (…{key[-4:]})" if key else "없음 (Claude API 방식을 쓸 때만 필요)")

    def _set_key(self):
        ask_api_key(self)
        self._refresh_key()

    def _delete_key(self):
        if get_setting("anthropic_api_key") and messagebox.askyesno("Claude API 키", "저장된 키를 지울까요?", parent=self):
            update_settings(anthropic_api_key="")
            self._refresh_key()

    def _run_step(self, starter):
        """Claude Code 설치·로그인 창을 띄우고, 창이 닫히면 환경을 다시 점검"""
        from . import quote_reader
        try:
            proc = getattr(quote_reader, starter)()
        except Exception as e:
            messagebox.showerror("Claude Code", f"창을 열지 못했습니다.\n{e}", parent=self)
            return
        self.cc_lbl.config(text="창이 닫히기를 기다리는 중…")

        def wait():
            if proc.poll() is None:
                self.after(500, wait)
            else:
                self.check_env()
        wait()

    # ------------------------------------------------ 환경 점검
    def _build_env(self):
        frm = ttk.LabelFrame(self, text=" 환경 점검 ", padding=10)
        frm.pack(fill="x")
        from .environment import CHECKS
        for i, (name, _) in enumerate(CHECKS):
            ttk.Label(frm, text=name, width=LABEL_WIDTH).grid(row=i, column=0, sticky="w", pady=2)
            mark = ttk.Label(frm, text="…", width=8)
            mark.grid(row=i, column=1, sticky="w", pady=2)
            detail = ttk.Label(frm, text="", wraplength=640, justify="left")
            detail.grid(row=i, column=2, sticky="w", pady=2)
            self.env_rows[name] = (mark, detail)
        self.env_btn = ttk.Button(frm, text="다시 점검", command=self.check_env)
        self.env_btn.grid(row=len(CHECKS), column=0, sticky="w", pady=(8, 0))
        frm.columnconfigure(2, weight=1)

    def check_env(self):
        """점검은 스레드에서 하고 결과만 화면에 표시 (Claude Code 확인이 1초 안팎 걸림)"""
        if self.checking:
            return
        self.checking = True
        self.env_btn.state(["disabled"])
        for mark, detail in self.env_rows.values():
            mark.config(text="…", foreground="gray")
            detail.config(text="점검 중", foreground="gray")
        result = {}
        thread = threading.Thread(target=lambda: result.update(rows=run_checks()), daemon=True)
        thread.start()

        def wait():
            if thread.is_alive():
                self.after(200, wait)
                return
            self.checking = False
            self.env_btn.state(["!disabled"])
            for name, ok, detail in result["rows"]:
                mark, text = self.env_rows[name]
                mark.config(text="정상" if ok else "확인 필요", foreground=OK_COLOR if ok else WARN_COLOR)
                text.config(text=detail, foreground="" if ok else WARN_COLOR)
                if name == "Claude Code":
                    self.cc_lbl.config(text=detail)
        wait()

    # ------------------------------------------------ 탭을 열 때
    def on_show(self):
        """설정 탭이 보일 때마다 저장된 값을 다시 읽고 환경을 점검"""
        for key, var in self.path_vars.items():
            var.set(get_setting(key))
        self.mode_var.set({v: k for k, v in READ_MODES.items()}.get(get_setting("read_mode"), "로컬 (무료)"))
        self._refresh_key()
        self.check_env()
