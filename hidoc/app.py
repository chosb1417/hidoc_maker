"""hidoc maker 메인 창. python -m hidoc 또는 실행.bat 으로 실행

첫 화면: '문서 만들기'(documents.py 의 문서 목록)와 '설정' 탭.
문서를 고르면 같은 창이 작성 화면으로 바뀌고, 위쪽 '← 처음으로'로 돌아옴.
작성 화면은 한 번 만든 뒤 계속 두므로 처음으로 갔다 와도 입력 내용이 남음.
"""

import tkinter as tk
from tkinter import ttk

from .documents import DOCUMENTS
from .settings_view import SettingsView
from .widgets import enable_inline_ime

APP_TITLE = "hidoc maker"


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1000x880")  # 품의서 화면 위 "처음으로" 줄만큼 높임
        self.minsize(920, 680)
        style = ttk.Style(self)
        style.configure(".", font=("맑은 고딕", 10))
        style.configure("Treeview.Heading", font=("맑은 고딕", 10, "bold"))
        style.configure("Doc.TButton", font=("맑은 고딕", 12, "bold"), padding=(16, 12), anchor="w")
        style.configure("Title.TLabel", font=("맑은 고딕", 14, "bold"))

        self.forms = {}  # 문서 key -> 작성 화면 (한 번 만들고 유지)
        self.current = None
        self._build_home()
        self._build_doc_page()
        self.home.pack(fill="both", expand=True, padx=10, pady=10)
        enable_inline_ime(self)  # 한글 조합 중인 글자를 떠 있는 상자 대신 입력칸 본문 자리에 바로 표시

    # ------------------------------------------------ 첫 화면
    def _build_home(self):
        self.home = ttk.Notebook(self)
        docs = ttk.Frame(self.home, padding=24)
        ttk.Label(docs, text="만들 문서를 고르세요", style="Title.TLabel").pack(anchor="w", pady=(0, 16))
        for doc in DOCUMENTS:
            ttk.Button(docs, text=f"{doc.name}\n{doc.description}", style="Doc.TButton",
                       command=lambda d=doc: self.open_document(d)).pack(fill="x", pady=4)
        self.settings_view = SettingsView(self.home)
        self.home.add(docs, text="  문서 만들기  ")
        self.home.add(self.settings_view, text="  설정  ")
        self.home.bind("<<NotebookTabChanged>>", self._on_tab)

    def _on_tab(self, _e):
        if self.home.select() == str(self.settings_view):
            self.settings_view.on_show()

    # ------------------------------------------------ 작성 화면
    def _build_doc_page(self):
        self.doc_page = ttk.Frame(self)
        bar = ttk.Frame(self.doc_page, padding=(10, 8, 10, 0))
        bar.pack(fill="x")
        ttk.Button(bar, text="← 처음으로", command=self.go_home).pack(side="left")
        self.doc_title = ttk.Label(bar, style="Title.TLabel")
        self.doc_title.pack(side="left", padx=12)
        self.doc_body = ttk.Frame(self.doc_page)
        self.doc_body.pack(fill="both", expand=True)

    def open_document(self, doc):
        form = self.forms.get(doc.key)
        if form is None:
            form = self.forms[doc.key] = doc.form_class(self.doc_body)
        form.refresh_from_settings()  # 설정 탭에서 바꾼 경로·읽기 방식 반영
        form.pack(fill="both", expand=True)
        self.current = form
        self.doc_title.config(text=doc.name)
        self.title(f"{doc.name} - {APP_TITLE}")
        self.home.pack_forget()
        self.doc_page.pack(fill="both", expand=True)

    def go_home(self):
        if self.current is not None:
            self.current.pack_forget()
            self.current = None
        self.doc_page.pack_forget()
        self.title(APP_TITLE)
        self.home.pack(fill="both", expand=True, padx=10, pady=10)
