import win32api
import win32con
import win32gui
import win32process


KEYBOARD_FOCUS_CLASSES = (
    "Chrome_RenderWidgetHostHWND",
    "Chrome_WidgetWin_0",
)


def embed_window(child_hwnd: int, parent_hwnd: int) -> None:
    win32gui.ShowWindow(child_hwnd, win32con.SW_RESTORE)

    style = win32gui.GetWindowLong(child_hwnd, win32con.GWL_STYLE)
    style = style & ~win32con.WS_CAPTION
    style = style & ~win32con.WS_THICKFRAME
    style = style & ~win32con.WS_BORDER
    style = style & ~win32con.WS_POPUP
    style = style | win32con.WS_CHILD | win32con.WS_VISIBLE | win32con.WS_TABSTOP

    win32gui.SetWindowLong(child_hwnd, win32con.GWL_STYLE, style)
    win32gui.SetParent(child_hwnd, parent_hwnd)
    win32gui.ShowWindow(child_hwnd, win32con.SW_SHOW)
    force_redraw(parent_hwnd)
    force_redraw(child_hwnd)
    focus_embedded_window(child_hwnd)


def resize_embedded_window(hwnd: int, width: int, height: int) -> None:
    win32gui.SetWindowPos(
        hwnd,
        None,
        0,
        0,
        width,
        height,
        win32con.SWP_NOZORDER
        | win32con.SWP_FRAMECHANGED
        | win32con.SWP_NOACTIVATE,
    )
    force_redraw(hwnd)


def release_embedded_window(hwnd: int) -> None:
    win32gui.SetParent(hwnd, 0)


def focus_embedded_window(hwnd: int) -> None:
    focus_hwnd = find_keyboard_focus_window(hwnd) or hwnd
    root_hwnd = win32gui.GetAncestor(hwnd, win32con.GA_ROOT)
    foreground_hwnd = win32gui.GetForegroundWindow()
    current_thread_id = win32api.GetCurrentThreadId()
    target_thread_id, _ = win32process.GetWindowThreadProcessId(focus_hwnd)
    foreground_thread_id = None
    if foreground_hwnd:
        foreground_thread_id, _ = win32process.GetWindowThreadProcessId(foreground_hwnd)
    attached_pairs = []

    try:
        attach_thread_input(current_thread_id, target_thread_id, attached_pairs)
        if foreground_thread_id:
            attach_thread_input(current_thread_id, foreground_thread_id, attached_pairs)
            attach_thread_input(target_thread_id, foreground_thread_id, attached_pairs)

        for action in (
            lambda: win32gui.ShowWindow(hwnd, win32con.SW_SHOW),
            lambda: win32gui.BringWindowToTop(root_hwnd),
            lambda: win32gui.SetForegroundWindow(root_hwnd),
            lambda: win32gui.SetActiveWindow(root_hwnd),
            lambda: win32gui.SetFocus(focus_hwnd),
        ):
            try:
                action()
            except Exception:
                pass
    finally:
        for source_thread_id, target_thread_id in reversed(attached_pairs):
            try:
                win32process.AttachThreadInput(source_thread_id, target_thread_id, False)
            except Exception:
                pass


def attach_thread_input(
    source_thread_id: int,
    target_thread_id: int,
    attached_pairs: list[tuple[int, int]],
) -> None:
    if source_thread_id == target_thread_id:
        return

    try:
        win32process.AttachThreadInput(source_thread_id, target_thread_id, True)
        attached_pairs.append((source_thread_id, target_thread_id))
    except Exception:
        pass


def find_keyboard_focus_window(root_hwnd: int) -> int | None:
    descendants = []

    def enum_child(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            descendants.append(hwnd)

    try:
        win32gui.EnumChildWindows(root_hwnd, enum_child, None)
    except Exception:
        return None

    for class_name in KEYBOARD_FOCUS_CLASSES:
        for hwnd in reversed(descendants):
            try:
                if win32gui.GetClassName(hwnd) == class_name:
                    return hwnd
            except Exception:
                pass

    return descendants[-1] if descendants else None


def force_redraw(hwnd: int) -> None:
    win32gui.RedrawWindow(
        hwnd,
        None,
        None,
        win32con.RDW_INVALIDATE
        | win32con.RDW_UPDATENOW
        | win32con.RDW_ALLCHILDREN,
    )
