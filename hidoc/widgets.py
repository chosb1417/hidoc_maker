"""여러 화면에서 함께 쓰는 입력창 도우미"""

import tkinter as tk
from tkinter import simpledialog

from .settings import update_settings


def add_placeholder(widget, text, var=None):
    """입력칸이 비어 있을 때만 안쪽에 회색 예시 글자를 보여 줌. 입력값에는 들어가지 않음.
    한 줄 입력칸은 Tk 9 의 placeholder 옵션을 쓰고, 그 옵션이 없는 경우(Tk 8.6, 여러 줄 Text)는
    입력칸 위에 회색 글자를 겹쳐 놓음. Entry 는 var, Text 는 내용으로 비었는지 판단"""
    is_text = isinstance(widget, tk.Text)
    if not is_text:
        try:
            widget.configure(placeholder=text)
            return
        except tk.TclError:  # Tk 8.6
            pass
    hint = tk.Label(widget, text=text, fg="gray", bg=widget.cget("background") if is_text else "SystemWindow",
                    font=("맑은 고딕", 10), justify="left", padx=0, pady=0, cursor="xterm")
    hint.bind("<Button-1>", lambda _e: widget.focus_set())  # 예시 글자를 눌러도 입력칸으로

    def refresh(*_):
        if widget.get("1.0", "end-1c") if is_text else var.get():
            hint.place_forget()
        elif is_text:
            hint.place(x=3, y=3)
        else:
            hint.place(x=4, rely=0.5, anchor="w")

    if is_text:
        def on_modified(_e):
            refresh()
            widget.edit_modified(False)  # 다음 변경도 알림을 받도록
        widget.bind("<<Modified>>", on_modified, add="+")
    else:
        var.trace_add("write", refresh)
    refresh()


def ask_api_key(parent) -> bool:
    """Claude API 키를 물어 settings.json 에 저장. 키를 저장했으면 True, 지웠거나 취소했으면 False"""
    key = simpledialog.askstring(
        "Claude API 키", "Claude API 키를 붙여 넣으세요. (sk-ant-…)\n"
        "키는 이 PC의 settings.json 에만 저장되고 git에는 올라가지 않습니다.\n"
        "비워 두고 확인을 누르면 저장된 키를 지웁니다.", show="*", parent=parent)
    if key is None:
        return False
    update_settings(anthropic_api_key=key.strip())
    return bool(key.strip())
