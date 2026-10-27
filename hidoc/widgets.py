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


def add_suggestions(entry, var, get_items, limit=8):
    """입력하는 동안 칸 바로 아래에 get_items() 중 입력한 글자가 들어간 항목을 보여 줌 (공백·대소문자 무시).
    마우스 클릭 또는 ↓↑ + Enter 로 고르고, Esc·다른 칸으로 이동하면 닫힘.
    칸에 포커스가 있을 때만 뜨므로 프로그램이 값을 채울 때는 나타나지 않음"""
    popup = tk.Toplevel(entry)
    popup.withdraw()
    popup.overrideredirect(True)  # 제목 표시줄 없는 작은 창
    popup.transient(entry.winfo_toplevel())  # 메인 창에 딸린 창으로 묶어 항상 그 위에 뜨게
    box = tk.Listbox(popup, height=limit, activestyle="none", font=("맑은 고딕", 10), exportselection=False,
                     relief="solid", borderwidth=1, highlightthickness=0)
    box.pack(fill="both", expand=True)
    state = {"items": [], "choosing": False}

    def key(text):
        return text.replace(" ", "").lower()

    def hide(*_):
        popup.withdraw()

    def show(matches):
        box.delete(0, "end")
        for m in matches:
            box.insert("end", m)
        box.config(height=len(matches))
        box.update_idletasks()  # 줄 수를 바꾼 뒤 높이를 다시 계산
        x, y = entry.winfo_rootx(), entry.winfo_rooty() + entry.winfo_height()
        popup.geometry(f"{entry.winfo_width()}x{box.winfo_reqheight()}+{x}+{y}")
        popup.deiconify()
        popup.lift()

    def on_change(*_):
        if state["choosing"] or entry.focus_get() is not entry:
            return
        typed = key(var.get())
        matches = [it for it in state["items"] if typed and typed in key(it) and key(it) != typed][:limit]
        show(matches) if matches else hide()

    def choose(*_):
        sel = box.curselection()
        if not sel:
            return
        state["choosing"] = True
        var.set(box.get(sel[0]))
        state["choosing"] = False
        hide()
        entry.focus_set()
        entry.icursor("end")

    def move(step):
        if not popup.winfo_viewable():
            return None  # 목록이 닫혀 있으면 원래 동작(드롭다운 열기 등)
        n = box.size()
        cur = box.curselection()
        i = (cur[0] + step) % n if cur else (0 if step > 0 else n - 1)
        box.selection_clear(0, "end")
        box.selection_set(i)
        box.see(i)
        return "break"

    def on_return(_e):
        if popup.winfo_viewable() and box.curselection():
            choose()
            return "break"
        return None

    def on_focus_in(_e):
        state["items"] = list(get_items())  # 칸에 들어올 때 한 번 읽음

    def on_focus_out(_e):
        # 목록을 누르면 포커스가 목록으로 가므로, 그때는 닫지 않음 (고르면 choose 가 닫음)
        entry.after(150, lambda: None if entry.focus_get() is box else hide())

    def on_window_change(e):
        if e.widget is entry.winfo_toplevel():  # 안쪽 요소가 아니라 창 자체가 움직이거나 크기가 바뀔 때만
            hide()

    var.trace_add("write", on_change)
    entry.bind("<FocusIn>", on_focus_in, add="+")
    entry.bind("<FocusOut>", on_focus_out, add="+")
    entry.bind("<Down>", lambda _e: move(1))
    entry.bind("<Up>", lambda _e: move(-1))
    entry.bind("<Return>", on_return, add="+")
    entry.bind("<Escape>", hide, add="+")
    box.bind("<ButtonRelease-1>", choose)
    entry.winfo_toplevel().bind("<Configure>", on_window_change, add="+")


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
