"""여러 화면에서 함께 쓰는 입력창 도우미"""

import ctypes
import tkinter as tk
from ctypes import wintypes
from tkinter import simpledialog, ttk

from .settings import update_settings

# Windows 입력기(IME) - 한글을 조합하는 동안의 글자는 입력칸 값에 아직 안 들어가므로 직접 읽음
_user32 = ctypes.windll.user32
_imm32 = ctypes.windll.imm32
_user32.GetFocus.restype = wintypes.HWND
_imm32.ImmGetContext.argtypes = [wintypes.HWND]
_imm32.ImmGetContext.restype = ctypes.c_void_p
_imm32.ImmReleaseContext.argtypes = [wintypes.HWND, ctypes.c_void_p]
_imm32.ImmGetCompositionStringW.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
_imm32.ImmGetCompositionStringW.restype = ctypes.c_long
_imm32.ImmNotifyIME.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
GCS_COMPSTR = 0x0008  # 조합 중인 글자
NI_COMPOSITIONSTR, CPS_CANCEL = 0x0015, 0x0004


def ime_composition() -> str:
    """지금 포커스가 있는 칸에서 조합 중인 글자 (예: '한빛'을 칠 때 값은 '한', 조합 중은 '빛'). 없으면 ''"""
    hwnd = _user32.GetFocus()
    himc = _imm32.ImmGetContext(hwnd)
    if not himc:
        return ""
    try:
        size = _imm32.ImmGetCompositionStringW(himc, GCS_COMPSTR, None, 0)  # 바이트 수
        if size <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(size // 2 + 1)
        _imm32.ImmGetCompositionStringW(himc, GCS_COMPSTR, buf, size)
        return buf.value
    finally:
        _imm32.ImmReleaseContext(hwnd, himc)


# ---------------------------------------------------------------- 한글 조합 글자를 입력칸 안에 직접 그리기
# tkinter 는 조합 중인 글자를 Windows 입력기가 띄우는 작은 상자로 보여 줘서 글자가 떠 있는 것처럼 보임.
# 입력기에 상자를 띄우지 말라고 알리고(WM_IME_SETCONTEXT 의 ISC_SHOWUICOMPOSITIONWINDOW 끄기 - 직접 그리는
# 프로그램을 위한 Windows 의 공식 방법), 조합 중인 글자는 커서 위치에 본문과 같은 글꼴로 직접 그림.
WM_IME_SETCONTEXT = 0x0281
WM_IME_STARTCOMPOSITION, WM_IME_ENDCOMPOSITION, WM_IME_COMPOSITION = 0x010D, 0x010E, 0x010F
ISC_SHOWUICOMPOSITIONWINDOW = 0x80000000
GWLP_WNDPROC = -4
_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
_user32.SetWindowLongPtrW.restype = ctypes.c_void_p
_user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.CallWindowProcW.restype = ctypes.c_ssize_t


def enable_inline_ime(window):
    """window(Tk 또는 Toplevel) 안의 모든 입력칸에서 조합 중인 한글을 채팅창처럼 본문 자리에 바로 보여 줌.
    tkinter 는 모든 입력칸이 최상위 창 하나로 입력기 메시지를 받으므로 그 창 하나만 처리하면 됨"""
    from tkinter import font as tkfont

    overlay = tk.Label(window, borderwidth=0, padx=0, pady=0, anchor="nw", justify="left")  # 조합 중인 글자
    caret = tk.Frame(window, width=1, bg="black")  # 조합 글자 뒤에 그리는 커서

    def hide():
        overlay.place_forget()
        caret.place_forget()

    def field_font(w):
        if isinstance(w, tk.Text):
            return w.cget("font")
        return ttk.Style(w).lookup(w.winfo_class(), "font") or "TkDefaultFont"

    def caret_box(w, is_text):
        """커서 자리 (x, y, 높이). Entry 는 커서가 맨 끝이면 bbox 가 마지막 글자를 돌려주므로 그 오른쪽으로"""
        if not is_text:
            idx, text = w.index("insert"), w.get()
            if text and idx >= len(text):
                bx, by, bw, bh = w.bbox(idx - 1)
                return bx + bw, by, bh
        box = w.bbox("insert")
        return (box[0], box[1], box[3]) if box else None

    def refresh():
        w = window.focus_get()
        comp = ime_composition()
        if not comp or not isinstance(w, (tk.Entry, ttk.Entry, tk.Text)):  # ttk.Combobox 도 ttk.Entry
            hide()
            return
        is_text = isinstance(w, tk.Text)
        pos = caret_box(w, is_text)
        if not pos:
            hide()
            return
        x, y, h = pos
        empty = not (w.get("1.0", "end-1c") if is_text else w.get())
        fnt = field_font(w)
        width = tkfont.Font(root=window, font=fnt).measure(comp)
        overlay.config(text=comp, font=fnt, fg="black", bg=w.cget("background") if is_text else "SystemWindow")
        x -= 1  # tkinter 원래 커서(조합 글자 앞)까지 덮음
        width += 1
        if empty:  # 빈 칸이면 예시 글자(placeholder)를 가려서 채팅창처럼 조합 글자만 보이게
            overlay.place(in_=w, x=x, y=y, width=max(w.winfo_width() - x - 3, width),
                          height=max(w.winfo_height() - y - 3, h))
        else:
            overlay.place(in_=w, x=x, y=y, width=width + 1, height=h)
        caret.place(in_=w, x=x + width, y=y, width=1, height=h)
        overlay.lift()
        caret.lift()
        _hide_ime_box()  # 입력기가 띄운 조합 상자가 남아 있으면 숨김

    def wndproc(hwnd, msg, wparam, lparam):
        # 여기서는 tkinter 를 부르면 안 됨 (tkinter 가 이벤트를 처리하는 도중이라 프로그램이 강제 종료됨).
        # Windows 함수만 쓰고, 다시 그리기는 아래 tkinter 키·포커스 이벤트에서 함
        if msg == WM_IME_SETCONTEXT:
            lparam &= ~ISC_SHOWUICOMPOSITIONWINDOW  # 입력기의 조합 상자를 띄우지 않음 (새 한글 입력기는 무시함)
        result = _user32.CallWindowProcW(old_proc, hwnd, msg, wparam, lparam)
        if msg in (WM_IME_STARTCOMPOSITION, WM_IME_COMPOSITION, WM_IME_NOTIFY):
            _hide_ime_box()  # 입력기가 조합 상자를 띄우거나 옮긴 직후 숨김
        return result

    window.update_idletasks()
    proc = _WNDPROC(wndproc)
    old_proc = _user32.SetWindowLongPtrW(window.winfo_id(), GWLP_WNDPROC, ctypes.cast(proc, ctypes.c_void_p))
    window._inline_ime_proc = proc  # 콜백이 사라지지 않게 창이 살아 있는 동안 붙잡아 둠
    # 키를 누르고 뗄 때(입력기가 조합 글자를 바꾼 뒤), 포커스가 옮겨질 때(조합이 확정됨) 다시 그림.
    # tkinter 가 커서를 다시 그리며 입력기 글자 위치를 커서로 되돌려 놓을 수 있어 조금 뒤에 그림
    for event in ("<KeyPress>", "<KeyRelease>", "<FocusOut>", "<FocusIn>"):
        window.bind_all(event, lambda _e: window.after(15, refresh), add="+")


WM_IME_NOTIFY = 0x0282
# Windows 한글 입력기가 조합 글자를 보여 주는 창들. 커서 자리에 붙는 창(MSCTFIME Composition)과,
# 위치를 못 정하면 화면 모서리에 뜨는 상자 창(CiceroUIWndFrame)
IME_BOX_CLASSES = {"MSCTFIME Composition", "CiceroUIWndFrame"}
IME_BOX_MAX_HEIGHT = 60  # 한 줄짜리 조합 상자만 숨김 (한자 후보 목록처럼 큰 창은 그대로 둠)
_kernel32 = ctypes.windll.kernel32
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32.EnumThreadWindows.argtypes = [wintypes.DWORD, _WNDENUMPROC, wintypes.LPARAM]
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]


@_WNDENUMPROC
def _hide_if_ime_box(hwnd, _lparam):
    if _user32.IsWindowVisible(hwnd):
        cls = ctypes.create_unicode_buffer(64)
        _user32.GetClassNameW(hwnd, cls, 64)
        rect = wintypes.RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(rect))
        if cls.value in IME_BOX_CLASSES and rect.bottom - rect.top <= IME_BOX_MAX_HEIGHT:
            _user32.ShowWindow(hwnd, 0)  # SW_HIDE
    return True


def _hide_ime_box():
    """이 프로그램 안에 입력기가 띄운 조합 상자 창을 숨김 (조합 글자는 우리가 입력칸 안에 직접 그림)"""
    _user32.EnumThreadWindows(_kernel32.GetCurrentThreadId(), _hide_if_ime_box, 0)


def ime_cancel():
    """조합 중인 글자를 버림 (추천 목록에서 고른 뒤 조합 중이던 글자가 뒤에 붙지 않게)"""
    hwnd = _user32.GetFocus()
    himc = _imm32.ImmGetContext(hwnd)
    if himc:
        _imm32.ImmNotifyIME(himc, NI_COMPOSITIONSTR, CPS_CANCEL, 0)
        _imm32.ImmReleaseContext(hwnd, himc)


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
        typed = key(var.get() + ime_composition())  # 조합 중인 마지막 한글 글자까지 포함
        matches = [it for it in state["items"] if typed and typed in key(it) and key(it) != typed][:limit]
        show(matches) if matches else hide()

    def choose(*_):
        sel = box.curselection()
        if not sel:
            return
        state["choosing"] = True
        if entry.focus_get() is entry:
            ime_cancel()
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

    def on_key(e):
        if e.keysym not in ("Up", "Down", "Return", "Escape"):
            on_change()  # 조합 중에는 값이 안 바뀌어 trace 가 안 불리므로 키를 뗄 때마다 다시 찾음

    var.trace_add("write", on_change)
    entry.bind("<KeyRelease>", on_key, add="+")
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


def ask_choice(parent, title, message, buttons, icon="warning"):
    """버튼 이름을 직접 정하는 확인 창. 누른 버튼 글자를 돌려줌. 창을 닫거나 Esc 면 None
    (messagebox 는 예/아니오 같은 정해진 버튼만 됨)"""
    win = tk.Toplevel(parent)
    win.title(title)
    win.resizable(False, False)
    win.transient(parent.winfo_toplevel())
    choice = {}

    body = ttk.Frame(win, padding=(16, 14, 16, 8))
    body.pack(fill="both")
    ttk.Label(body, image=f"::tk::icons::{icon}").pack(side="left", anchor="n", padx=(0, 12))
    ttk.Label(body, text=message, justify="left").pack(side="left")
    row = ttk.Frame(win, padding=(16, 4, 16, 14))
    row.pack(fill="x")
    for i, text in enumerate(reversed(buttons)):  # 오른쪽부터 채워 buttons 순서대로 보이게
        btn = ttk.Button(row, text=text, command=lambda t=text: (choice.update(value=t), win.destroy()))
        btn.pack(side="right", padx=(6, 0))
        if i == len(buttons) - 1:
            default = btn
            btn.focus_set()  # 첫 버튼이 기본 (Enter)
    # Enter: Tab 으로 옮긴 버튼이 있으면 그 버튼, 아니면 첫 버튼
    win.bind("<Return>", lambda _e: (win.focus_get() if isinstance(win.focus_get(), ttk.Button) else default).invoke())
    win.bind("<Escape>", lambda _e: win.destroy())

    # 부모 창 가운데에 띄우고, 닫힐 때까지 다른 곳을 누르지 못하게
    win.update_idletasks()
    top = parent.winfo_toplevel()
    x = top.winfo_rootx() + (top.winfo_width() - win.winfo_width()) // 2
    y = top.winfo_rooty() + (top.winfo_height() - win.winfo_height()) // 3
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()
    win.wait_window()
    return choice.get("value")
