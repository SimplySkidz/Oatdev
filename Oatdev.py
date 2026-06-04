import ctypes
import json
import os
import re
import time
import threading
import tkinter as tk
import urllib.request
from tkinter import messagebox, ttk




try:
    import pygetwindow as gw
    import pyperclip
except Exception:
    gw = None
    pyperclip = None


def check_deps():
    if gw is None or pyperclip is None:
        messagebox.showerror(
            "Missing dependencies",
            "Required packages not found. Please install:\n\npip install pygetwindow pyperclip",
        )
        return False
    return True


SW_RESTORE = 9
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_PASTE = 0x0302

VK_MAPPING = {
    '`': 0xC0,
    'tilde': 0xC0,
    'backquote': 0xC0,
    '/': 0xBF,
    'slash': 0xBF,
    'space': 0x20,
    ' ': 0x20,
    'enter': 0x0D,
    'return': 0x0D,
    'tab': 0x09,
    'esc': 0x1B,
    'escape': 0x1B,
    'backspace': 0x08,
    'insert': 0x2D,
    'delete': 0x2E,
    'home': 0x24,
    'end': 0x23,
    'pageup': 0x21,
    'pagedown': 0x22,
    'left': 0x25,
    'up': 0x26,
    'right': 0x27,
    'down': 0x28,
    'shift': 0x10,
    'ctrl': 0x11,
    'control': 0x11,
    'alt': 0x12,
    'f1': 0x70,
    'f2': 0x71,
    'f3': 0x72,
    'f4': 0x73,
    'f5': 0x74,
    'f6': 0x75,
    'f7': 0x76,
    'f8': 0x77,
    'f9': 0x78,
    'f10': 0x79,
    'f11': 0x7A,
    'f12': 0x7B,
    'f13': 0x7C,
    'f14': 0x7D,
    'f15': 0x7E,
    'f16': 0x7F,
    'f17': 0x80,
    'f18': 0x81,
    'f19': 0x82,
    'f20': 0x83,
    'f21': 0x84,
    'f22': 0x85,
    'f23': 0x86,
    'f24': 0x87,
}

EXTENDED_KEYS = {
    0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25,
    0x26, 0x27, 0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x2F,
    0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39,
    0x5B, 0x5C, 0x5D, 0x5E, 0x5F,
}


def normalize_title(title):
    return (title or '').strip().lower()


def is_admin_tool_title(title):
    title = (title or '').lower()
    return 'admin tool' in title or 'Oatdev' in title


def find_window(title_substring):
    title_substring = (title_substring or '').strip()
    if not title_substring:
        return None

    search = title_substring.lower()
    all_windows = gw.getAllWindows()
    if not all_windows:
        return None

    candidates = [w for w in all_windows if search in normalize_title(w.title)]
    if not candidates:
        return None

    candidates = [w for w in candidates if not is_admin_tool_title(w.title)] or candidates

    exact = [w for w in candidates if normalize_title(w.title) == search]
    if exact:
        return exact[0]

    starts = [w for w in candidates if normalize_title(w.title).startswith(search)]
    if starts:
        return starts[0]

    return candidates[0]


def get_window_hwnd(win):
    return getattr(win, '_hWnd', None) or getattr(win, 'hwnd', None)


def make_key_lparam(vk, keyup=False):
    scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
    lparam = 1 | (scan << 16)
    if vk in EXTENDED_KEYS:
        lparam |= 0x01000000
    if keyup:
        lparam |= 0xC0000000
    return lparam


def set_foreground_window(hwnd):
    if not hwnd:
        return False
    try:
        fg = ctypes.windll.user32.GetForegroundWindow()
        if fg == hwnd:
            return True
        if ctypes.windll.user32.IsIconic(hwnd):
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)

        current_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        fg_tid = ctypes.windll.user32.GetWindowThreadProcessId(fg, 0)
        target_tid = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, 0)
        ctypes.windll.user32.AttachThreadInput(current_tid, fg_tid, True)
        ctypes.windll.user32.AttachThreadInput(current_tid, target_tid, True)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
        ctypes.windll.user32.BringWindowToTop(hwnd)
        ctypes.windll.user32.SetActiveWindow(hwnd)
        ctypes.windll.user32.AttachThreadInput(current_tid, fg_tid, False)
        ctypes.windll.user32.AttachThreadInput(current_tid, target_tid, False)
        return True
    except Exception:
        return False


def activate_window(win):
    try:
        if hasattr(win, 'isMinimized') and win.isMinimized:
            win.restore()
    except Exception:
        pass
    try:
        win.activate()
    except Exception:
        pass

    hwnd = get_window_hwnd(win)
    if hwnd is not None:
        set_foreground_window(hwnd)

    time.sleep(0.25)


def key_to_vk(key):
    if not key:
        return None
    k = key.lower()             
    if k in VK_MAPPING:
        return VK_MAPPING[k]
    if len(key) == 1:
        vk = ctypes.windll.user32.VkKeyScanW(ord(key)) & 0xFF
        if vk != 0xFF:
            return vk
        return ord(key.upper())
    return None


def parse_key_sequence(key_sequence):
    if not key_sequence:
        return []
    parts = [p.strip().lower() for p in key_sequence.replace(',', '+').split('+') if p.strip()]
    vks = []
    for part in parts:
        vk = VK_MAPPING.get(part)
        if vk is None:
            if len(part) == 1:
                vk = ctypes.windll.user32.VkKeyScanW(ord(part)) & 0xFF
                if vk == 0xFF:
                    vk = None
            elif part.startswith('f') and part[1:].isdigit():
                num = int(part[1:])
                if 1 <= num <= 24:
                    vk = 0x6F + num
            else:
                vk = None
        if vk is None:
            raise ValueError(f'Unknown key token: {part}')
        vks.append(vk)
    return vks


def press_keydown(hwnd, vk):
    if not hwnd or vk is None:
        return False
    return bool(ctypes.windll.user32.PostMessageW(hwnd, WM_KEYDOWN, vk, make_key_lparam(vk, keyup=False)))


def press_keyup(hwnd, vk):
    if not hwnd or vk is None:
        return False
    return bool(ctypes.windll.user32.PostMessageW(hwnd, WM_KEYUP, vk, make_key_lparam(vk, keyup=True)))


def send_key_sequence(hwnd, key_sequence):
    try:
        vks = parse_key_sequence(key_sequence)
    except ValueError:
        return False
    if not vks:
        return False
    for vk in vks:
        if not press_keydown(hwnd, vk):
            return False
        time.sleep(0.02)
    for vk in reversed(vks):
        if not press_keyup(hwnd, vk):
            return False
        time.sleep(0.02)
    return True


def post_key(hwnd, vk):
    if not hwnd or vk is None:
        return False
    res_down = press_keydown(hwnd, vk)
    time.sleep(0.01)
    res_up = press_keyup(hwnd, vk)
    time.sleep(0.01)
    return res_down and res_up


def post_text(hwnd, text):
    if not hwnd or not text:
        return False
    for ch in text:
        vk = key_to_vk(ch)
        if vk is None or vk == 0xFF:
            return False
        if not post_key(hwnd, vk):
            return False
    return True


KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ('wVk', ctypes.c_ushort),
        ('wScan', ctypes.c_ushort),
        ('dwFlags', ctypes.c_ulong),
        ('time', ctypes.c_ulong),
        ('dwExtraInfo', ctypes.c_void_p),
    ]


class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [('ki', KEYBDINPUT)]
    _anonymous_ = ('_input',)
    _fields_ = [('type', ctypes.c_ulong), ('_input', _INPUT)]


def send_system_key(vk, keyup=False):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki.wVk = vk
    inp.ki.wScan = 0
    inp.ki.dwFlags = KEYEVENTF_KEYUP if keyup else 0
    inp.ki.time = 0
    inp.ki.dwExtraInfo = ctypes.cast(ctypes.pointer(ctypes.c_ulong(0)), ctypes.c_void_p)
    return ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)) == 1


def send_system_text(text):
    for ch in text:
        vk = key_to_vk(ch)
        if vk is None or vk == 0xFF:
            return False
        if not send_system_key(vk, keyup=False):
            return False
        time.sleep(0.01)
        if not send_system_key(vk, keyup=True):
            return False
        time.sleep(0.01)
    return True


def paste_text_via_clipboard(hwnd, text):
    if not text or not hwnd:
        return False
    try:
        old_clip = pyperclip.paste()
    except Exception:
        old_clip = None

    try:
        pyperclip.copy(text)
    except Exception:
        return False

    try:
        ctypes.windll.user32.SendMessageW(hwnd, WM_PASTE, 0, 0)
    except Exception:
        pass

    success = send_system_key_sequence('ctrl+v')
    time.sleep(0.05)
    if old_clip is not None:
        try:
            pyperclip.copy(old_clip)
        except Exception:
            pass
    return success


def send_system_key_sequence(key_sequence):
    try:
        vks = parse_key_sequence(key_sequence)
    except ValueError:
        return False
    if not vks:
        return False
    for vk in vks:
        if not send_system_key(vk, keyup=False):
            return False
        time.sleep(0.02)
    for vk in reversed(vks):
        if not send_system_key(vk, keyup=True):
            return False
        time.sleep(0.02)
    return True


def send_console_command_via_window(win, command_text, console_key='`'):
    hwnd = get_window_hwnd(win)
    if hwnd is None:
        raise RuntimeError('Window handle not available for target window')

    try:
        if console_key:
            if not send_key_sequence(hwnd, console_key):
                raise RuntimeError(f'Failed to send console key sequence: {console_key!r}')
    except ValueError as e:
        raise RuntimeError(str(e)) from e

    time.sleep(0.10)
    if paste_text_via_clipboard(hwnd, command_text):
        return post_key(hwnd, key_to_vk('enter'))

    if post_text(hwnd, command_text) and post_key(hwnd, key_to_vk('enter')):
        return True

    # Fallback to foreground + system input if window messages don't work.
    activate_window(win)
    if console_key and not send_system_key_sequence(console_key):
        raise RuntimeError(f'Failed to send console key via system input: {console_key!r}')
    if not send_system_text(command_text + '\r'):
        raise RuntimeError('Both window-post and system input methods failed')

    return True


def send_command_to_game(window_title, command_text, console_key='`'):
    """Focus the game window and send a single console command (no clipboard wait)."""
    if not check_deps():
        return False
    win = find_window(window_title)
    if not win:
        messagebox.showerror("Window not found", f"Could not find a window with title containing '{window_title}'")
        return False

    activate_window(win)

    try:
        return send_console_command_via_window(win, command_text, console_key)
    except Exception as e:
        messagebox.showerror("Input error", f"Failed to send keys: {e}")
        return False


def send_listplayers_to_game(window_title, console_key='`', status_callback=None):
    if not check_deps():
        return None
    win = find_window(window_title)
    if not win:
        messagebox.showerror("Window not found", f"Could not find a window with title containing '{window_title}'")
        return None

    if status_callback:
        status_callback('Focusing game window...')

    activate_window(win)

    try:
        original_clip = pyperclip.paste()
    except Exception:
        original_clip = None

    # Clear clipboard so we know the first non-empty content is from THIS call
    try:
        pyperclip.copy('')
    except Exception:
        pass

    if status_callback:
        status_callback('Opening console...')

    hwnd = get_window_hwnd(win)
    if hwnd is None:
        return None

    try:
        vks = parse_key_sequence(console_key)
    except ValueError:
        return None

    for vk in vks:
        press_keydown(hwnd, vk)
        time.sleep(0.02)
    for vk in reversed(vks):
        press_keyup(hwnd, vk)
        time.sleep(0.02)

    time.sleep(0.25)

    if status_callback:
        status_callback('Typing command...')

    post_text(hwnd, 'listplayers')
    post_key(hwnd, key_to_vk('enter'))

    if status_callback:
        status_callback('Waiting for game response...')

    try:
        timeout = 6.0
        poll = 0.1
        waited = 0.0
        while waited < timeout:
            time.sleep(poll)
            waited += poll
            try:
                clip = pyperclip.paste()
            except Exception:
                clip = None
            if clip:
                return clip
            if status_callback and int(waited * 10) % 5 == 0:
                status_callback(f'Waiting... ({waited:.0f}s)')

        try:
            clip = pyperclip.paste()
        except Exception:
            clip = None
        return clip
    finally:
        if original_clip is not None:
            try:
                pyperclip.copy(original_clip)
            except Exception:
                pass


def fetch_aliases(playfab_id):
    try:
        url = f'https://chivalry2stats.com/player?id={playfab_id}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='replace')
    except Exception:
        return None
    m = re.search(r'\\"aliasHistory\\":\\"([^\\]*)\\"', html)
    if not m:
        return None
    raw = m.group(1)
    aliases = [a.strip() for a in raw.split(',') if a.strip()]
    return aliases if aliases else None


def parse_players(text):
    if not text:
        return []
    players = []
    lines = text.splitlines()
    hex_re = re.compile(r'^[A-Fa-f0-9]{15,}$')

    playfab_col = 1
    for raw in lines[:5]:
        low = raw.strip().lower()
        if 'playfab' in low:
            parts = [p.strip() for p in raw.strip().split(' - ')]
            for i, p in enumerate(parts):
                if 'playfab' in p.lower():
                    playfab_col = i
                    break
            break

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith('servername') or low.startswith('name -') or 'playfabplayerid' in low:
            continue

        if ' - ' not in line:
            continue

        parts = [p.strip() for p in line.split(' - ')]
        if len(parts) > playfab_col:
            pid = parts[playfab_col]
            if hex_re.fullmatch(pid):
                p = {'name': parts[0], 'playfab_id': pid}
                if len(parts) >= 3: p['eos_id'] = parts[2]
                if len(parts) >= 4: p['score'] = parts[3]
                if len(parts) >= 5: p['kills'] = parts[4]
                if len(parts) >= 6: p['deaths'] = parts[5].removesuffix(' ms')
                if len(parts) >= 7: p['ping'] = parts[6]
                players.append(p)
                continue
        if len(parts) >= 2:
            for candidate in parts[1:]:
                if hex_re.fullmatch(candidate):
                    players.append({'name': parts[0], 'playfab_id': candidate})
                    break

    return players


class App:
    def __init__(self, root):
        self.root = root
        root.title('Oatdev')

        root.configure(bg='#f5e6c8')
        try:
            root.iconbitmap('allergen_wheat_icon-icons.com_56427.ico')
        except Exception:
            pass
        root.protocol('WM_DELETE_WINDOW', self._on_close)

        style = ttk.Style()
        style.theme_use('clam')

        BG = '#f5e6c8'
        BG_ENTRY = '#faf0dc'
        FG = '#2b1a0e'
        CRIMSON = '#8b0000'
        GOLD = '#b8860b'
        BTN_BG = '#ede0c8'
        BTN_ACTIVE = '#d4b896'
        SEL_BG = '#c8a050'

        FONT = ('Palatino Linotype', 10)
        FONT_BOLD = ('Palatino Linotype', 10, 'bold')
        FONT_BANNER = ('Constantia', 20, 'bold')

        style.configure('.', background=BG, font=FONT)
        style.configure('TLabel', background=BG, foreground=FG, font=FONT)
        style.configure('Banner.TLabel', background=BG, foreground=CRIMSON, font=FONT_BANNER)
        style.configure('TFrame', background=BG)
        style.configure('TButton', background=BTN_BG, foreground=FG, font=FONT, borderwidth=1)
        style.map('TButton', background=[('active', BTN_ACTIVE), ('pressed', GOLD)])
        style.configure('TEntry', fieldbackground=BG_ENTRY, foreground=FG, font=FONT, insertcolor=FG)
        style.configure('TLabelframe', background=BG, foreground=FG, font=FONT_BOLD)
        style.configure('TLabelframe.Label', background=BG, foreground=CRIMSON, font=FONT_BOLD)
        style.configure('Treeview', background=BG_ENTRY, foreground=FG, fieldbackground=BG_ENTRY, font=FONT, rowheight=22)
        style.configure('Treeview.Heading', background=BTN_BG, foreground=FG, font=FONT_BOLD)
        style.map('Treeview', background=[('selected', SEL_BG)], foreground=[('selected', FG)])

        body = ttk.Frame(root)
        body.pack(fill='both', expand=True)

        left = ttk.Frame(body)
        left.pack(side='left', fill='both', expand=True)

        banner = ttk.Label(left, text='~ O A T D E V ~', style='Banner.TLabel')
        banner.pack(fill='x', padx=8, pady=(8, 0))

        topfrm = ttk.Frame(left)
        topfrm.pack(fill='x', padx=8, pady=4)
        ttk.Label(topfrm, text='Window:').pack(side='left')
        self.win_entry = ttk.Entry(topfrm, width=25)
        self.win_entry.pack(side='left', padx=(4, 10))
        self.win_entry.insert(0, 'Chivalry 2')
        ttk.Label(topfrm, text='Key:').pack(side='left')
        self.key_entry = ttk.Entry(topfrm, width=8)
        self.key_entry.pack(side='left', padx=(4, 10))
        self.key_entry.insert(0, '`')
        btn = ttk.Button(topfrm, text='Debug', command=self.toggle_debug)
        btn.pack(side='left')
        self._bind_status_tip(btn, 'Open debug monitor')
        btn = ttk.Button(topfrm, text='Clear', command=self.clear_players)
        btn.pack(side='left', padx=(6, 10))
        self._bind_status_tip(btn, 'Clear player list and details')
        btn = ttk.Button(topfrm, text='Log', command=self.toggle_log)
        btn.pack(side='right')
        self._bind_status_tip(btn, 'View action log history')

        mainfrm = ttk.Frame(left)
        mainfrm.pack(fill='both', expand=True, padx=8, pady=(0, 6))
        self.tree = ttk.Treeview(mainfrm, columns=('name',), show='headings', height=15)
        self.tree.heading('name', text='Name')
        self.tree.column('name', width=240)
        self.tree.pack(side='left', fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', self.on_select)
        self.tree.bind('<Double-1>', self.on_double_click)
        self.tree.tag_configure('match', background='#d4b896')

        detfrm = ttk.LabelFrame(mainfrm, text='Player Details', width=260)
        self.detfrm = detfrm
        detfrm.pack(side='left', fill='y', padx=(8, 0))
        detfrm.pack_propagate(False)
        self.detail_name = ttk.Label(detfrm, text='', anchor='w')
        self.detail_name.pack(fill='x', padx=6, pady=(8, 2))
        self.detail_playfab = ttk.Label(detfrm, text='', anchor='w')
        self.detail_playfab.pack(fill='x', padx=6, pady=2)
        self.detail_score = ttk.Label(detfrm, text='', anchor='w')
        self.detail_score.pack(fill='x', padx=6, pady=2)
        self.detail_kills = ttk.Label(detfrm, text='', anchor='w')
        self.detail_kills.pack(fill='x', padx=6, pady=2)
        self.detail_deaths = ttk.Label(detfrm, text='', anchor='w')
        self.detail_deaths.pack(fill='x', padx=6, pady=2)
        btn = ttk.Button(detfrm, text='Past Names', command=self.show_past_names)
        btn.pack(fill='x', padx=6, pady=(8, 2))
        self._bind_status_tip(btn, 'Fetch previous names for the selected player')
        self.alias_listbox = tk.Listbox(
            detfrm, font=('Consolas', 10), height=6,
            bg='#faf0dc', fg='#2b1a0e',
            selectbackground='#c8a050', selectforeground='#2b1a0e',
        )
        self.alias_listbox.pack(fill='both', expand=True, padx=6, pady=(0, 6))

        # search + actions bar
        barbtnfrm = ttk.Frame(left)
        barbtnfrm.pack(fill='x', padx=8, pady=(0, 6))
        ttk.Label(barbtnfrm, text='Search:').pack(side='left')
        self.search_entry = ttk.Entry(barbtnfrm, width=20)
        self.search_entry.pack(side='left', padx=(4, 4))
        self.search_entry.bind('<KeyRelease>', self._on_search_key)
        self.search_entry.bind('<Return>', self.on_search)
        self.search_entry.bind('<Escape>', lambda e: self.clear_search())
        btn = ttk.Button(barbtnfrm, text='Copy PFId', command=self.copy_selected)
        btn.pack(side='left', padx=(10, 0))
        self._bind_status_tip(btn, 'Copy selected player PlayFabId to clipboard')
        btn = ttk.Button(barbtnfrm, text="List Players", command=self.on_run)
        btn.pack(side='left', padx=(6, 0))
        self._bind_status_tip(btn, 'Send listplayers command to game')

        self.all_players = []
        self._item_players = {}
        self._last_parsed = None
        self.debug_window = None
        self.debug_text = None
        self.action_log = []
        self._log_window = None
        self._settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings.json')
        self._load_settings()

        # commands frame
        cmdfrm = ttk.LabelFrame(left, text='Commands')
        cmdfrm.pack(fill='x', padx=8, pady=(0, 8))

        # row 1: PlayFabId, Duration, Reason, action buttons
        row1 = ttk.Frame(cmdfrm)
        row1.pack(fill='x', padx=6, pady=(6, 4))
        ttk.Label(row1, text='PFId:').pack(side='left')
        self.id_entry = ttk.Entry(row1, width=22)
        self.id_entry.pack(side='left', padx=(4, 8))
        ttk.Label(row1, text='Hrs:').pack(side='left')
        self.duration_entry = ttk.Entry(row1, width=5)
        self.duration_entry.pack(side='left', padx=(4, 8))
        ttk.Label(row1, text='Reason:').pack(side='left')
        self.reason_entry = ttk.Entry(row1, width=30)
        self.reason_entry.pack(side='left', padx=(4, 8))
        btn = ttk.Button(row1, text='Kick', command=self.kick_by_id)
        btn.pack(side='left')
        self._bind_status_tip(btn, 'Kick player by PlayFabId')
        btn = ttk.Button(row1, text='Ban', command=self.ban_by_id)
        btn.pack(side='left', padx=(4, 0))
        self._bind_status_tip(btn, 'Ban player by PlayFabId with duration and reason')
        btn = ttk.Button(row1, text='Unban', command=self.unban_by_id)
        btn.pack(side='left', padx=(4, 0))
        self._bind_status_tip(btn, 'Unban player by PlayFabId')

        # row 2: message + send buttons, extras at far right
        row2 = ttk.Frame(cmdfrm)
        row2.pack(fill='x', padx=6, pady=(4, 6))
        ttk.Label(row2, text='Message:').pack(side='left')
        self.msg_entry = ttk.Entry(row2, width=50)
        self.msg_entry.pack(side='left', padx=(4, 4))
        btn = ttk.Button(row2, text='Server', command=self.serversay)
        btn.pack(side='left')
        self._bind_status_tip(btn, 'Send message to all players on server')
        btn = ttk.Button(row2, text='Admin', command=self.adminsay)
        btn.pack(side='left', padx=(4, 0))
        self._bind_status_tip(btn, 'Send message with admin tag')
        btn = ttk.Button(row2, text='Extras →', command=self.toggle_right_panel)
        btn.pack(side='right')
        self._bind_status_tip(btn, 'Toggle extra game controls panel')

        # right-side panel (hidden by default)
        self._right_panel = ttk.LabelFrame(body, text='Game Controls', width=200)
        self._right_panel.pack_propagate(False)
        pfrm = ttk.Frame(self._right_panel)
        pfrm.pack(fill='both', expand=True, padx=6, pady=6)

        ttk.Label(pfrm, text='MATCH', font=FONT_BOLD, foreground=CRIMSON).pack(anchor='w', pady=(0, 4))
        btn = ttk.Button(pfrm, text='Start Game', command=self.start_game)
        btn.pack(fill='x', pady=(0, 6))
        self._bind_status_tip(btn, 'Manually start the match')

        stfrm = ttk.Frame(pfrm)
        stfrm.pack(fill='x', pady=(0, 4))
        ttk.Label(stfrm, text='Stage Time (mins):').pack(side='left')
        self._panel_stage_entry = ttk.Entry(stfrm, width=8)
        self._panel_stage_entry.pack(side='right')
        btn = ttk.Button(pfrm, text='Add Time', command=self._panel_add_stage)
        btn.pack(fill='x', pady=(0, 8))
        self._bind_status_tip(btn, 'Add or subtract stage time (negative value to subtract)')

        btn = ttk.Button(pfrm, text='End Game', command=self._panel_end_game)
        btn.pack(fill='x', pady=(0, 6))
        self._bind_status_tip(btn, 'End the current match')

        ttk.Separator(pfrm, orient='horizontal').pack(fill='x', pady=(4, 6))

        ttk.Label(pfrm, text='UTILITY', font=FONT_BOLD, foreground=CRIMSON).pack(anchor='w', pady=(0, 4))

        bfrm = ttk.Frame(pfrm)
        bfrm.pack(fill='x', pady=(0, 6))
        ttk.Label(bfrm, text='Bots:').pack(side='left')
        self._extra_bots_entry = ttk.Entry(bfrm, width=6)
        self._extra_bots_entry.pack(side='left', padx=(4, 0))
        btn = ttk.Button(bfrm, text='Add', command=self.add_bots)
        btn.pack(side='right')
        self._bind_status_tip(btn, 'Add bots to the game')

        btn = ttk.Button(pfrm, text='Remove Bots', command=self.remove_bots)
        btn.pack(fill='x', pady=(0, 2))
        self._bind_status_tip(btn, 'Remove bots from the game')
        btn = ttk.Button(pfrm, text='Toggle FPS', command=self.stat_fps)
        btn.pack(fill='x', pady=(0, 2))
        self._bind_status_tip(btn, 'Toggle FPS counter display')
        btn = ttk.Button(pfrm, text='Toggle HUD', command=self.toggle_hud)
        btn.pack(fill='x', pady=(0, 2))
        self._bind_status_tip(btn, 'Toggle heads-up display visibility')

        ttk.Separator(pfrm, orient='horizontal').pack(fill='x', pady=(6, 6))

        btn = ttk.Button(pfrm, text='Disconnect', command=self.disconnect)
        btn.pack(fill='x', pady=(0, 4))
        self._bind_status_tip(btn, 'Disconnect from the game server')
        btn = ttk.Button(pfrm, text='Exit', command=self.exit_game)
        btn.pack(fill='x')
        self._bind_status_tip(btn, 'Exit the game')

        self.status = ttk.Label(left, text='Ready', anchor='center', wraplength=600)
        self.status.pack(fill='x', padx=8, pady=(0, 4))

    def _bind_status_tip(self, widget, text):
        def show_tip(e):
            self._prev_status = self.status.cget('text')
            self.status.config(text=text)
        def clear_tip(e):
            self.status.config(text=getattr(self, '_prev_status', 'Ready'))
        widget.bind('<Enter>', show_tip)
        widget.bind('<Leave>', clear_tip)

    def set_status(self, text):
        self._prev_status = text
        self.status.config(text=text)

    def _load_settings(self):
        try:
            with open(self._settings_file) as f:
                s = json.load(f)
        except Exception:
            return
        if 'console_key' in s:
            self.key_entry.delete(0, tk.END)
            self.key_entry.insert(0, s['console_key'])

    def _save_settings(self):
        s = {'console_key': self.key_entry.get().strip() or '`'}
        try:
            with open(self._settings_file, 'w') as f:
                json.dump(s, f)
        except Exception:
            pass

    def _on_close(self):
        self._save_settings()
        self.root.destroy()

    def _log_action(self, action, details=''):
        if action not in ('Ban', 'Kick', 'Unban'):
            return
        t = time.strftime('%H:%M:%S')
        self.action_log.append({'time': t, 'action': action, 'details': details})
        if self._log_window and self._log_window.winfo_exists():
            self._log_tree.insert('', tk.END, values=(t, action, details))
            self._log_tree.see(tk.END)

    def toggle_log(self):
        if self._log_window and self._log_window.winfo_exists():
            self._log_window.lift()
            return
        self._log_window = tk.Toplevel(self.root, bg='#f5e6c8')
        self._log_window.title('Action Log')
        self._log_window.geometry('650x350')
        self._log_window.transient(self.root)
        frm = ttk.Frame(self._log_window)
        frm.pack(fill='both', expand=True, padx=8, pady=8)
        ttk.Label(frm, text='Admin actions are logged below:', anchor='w').pack(fill='x')
        tree = ttk.Treeview(frm, columns=('time', 'action', 'details'), show='headings', height=16)
        tree.heading('time', text='Time')
        tree.heading('action', text='Action')
        tree.heading('details', text='Details')
        tree.column('time', width=70)
        tree.column('action', width=120)
        tree.column('details', width=430)
        tree.pack(fill='both', expand=True, pady=(6, 0))
        self._log_tree = tree
        for entry in self.action_log:
            tree.insert('', tk.END, values=(entry['time'], entry['action'], entry['details']))
        self._log_window.protocol('WM_DELETE_WINDOW', self._close_log)

    def _close_log(self):
        self._log_window.destroy()
        self._log_window = None

    def toggle_debug(self):
        if self.debug_window and self.debug_window.winfo_exists():
            self.debug_window.destroy()
            self.debug_window = None
            self.debug_text = None
            self.set_status('Debug closed')
        else:
            self.debug_window = tk.Toplevel(self.root, bg='#f5e6c8')
            self.debug_window.title('Debug - Command Monitor')
            self.debug_window.geometry('600x400')
            self.debug_window.transient(self.root)
            frm = ttk.Frame(self.debug_window)
            frm.pack(fill='both', expand=True, padx=8, pady=8)
            ttk.Label(
                frm,
                text='Sent commands will appear here instead of being transmitted:',
                anchor='w',
            ).pack(fill='x')
            bf = ttk.Frame(frm)
            bf.pack(fill='x', pady=(0, 6))
            btn = ttk.Button(bf, text='Clear', command=lambda: self.debug_text.delete('1.0', tk.END))
            btn.pack(side='left')
            self._bind_status_tip(btn, 'Clear debug output')
            btn = ttk.Button(bf, text='False Populate', command=self._debug_listplayers)
            btn.pack(side='left', padx=(6, 0))
            self._bind_status_tip(btn, 'Populate with sample player data for testing')
            btn = ttk.Button(bf, text='Close', command=self.toggle_debug)
            btn.pack(side='right')
            self._bind_status_tip(btn, 'Close debug monitor')
            self.debug_text = tk.Text(frm, wrap='word', bg='#faf0dc', fg='#2b1a0e', font=('Consolas', 10), insertbackground='#2b1a0e')
            self.debug_text.pack(fill='both', expand=True)
            self.debug_window.protocol('WM_DELETE_WINDOW', self.toggle_debug)
            self.set_status('Debug open - commands will be intercepted')

    def _debug_insert(self, text):
        if self.debug_window and self.debug_window.winfo_exists():
            self.debug_text.insert(tk.END, f'> {text}\n')
            self.debug_text.see(tk.END)

    def _debug_listplayers(self):
        data = (
            'ServerName - OATS Duel Orleans [Duels Pit FFA Discord oatsduelyard] 134.255.251.182:10180\n'
            'Name -  PlayFabPlayerId - EOSPlayerId - Score - Kills - Deaths - Ping\n'
            'ʳ̶ᵖ̶ᵈ̶Falcon - DC7BA1E2ACB1A167 - 1096334384 - 0 - 0 - 0 ms\n'
            'ƬIƬΛП - AE17F81ACE3EF8F6 - -293570384 - 1080 - 8 - 4 ms\n'
            'ᶱᵗᴷŞimpɭeʂtŞɲarҽ - AD6D2AC59E4CB914 - -1261571360 - 125 - 1 - 1 ms\n'
            'Want My Oats - CD9B5A73422D169B - -182484784 - 2287 - 19 - 23 ms\n'
            'Eagle - 93F92DBF9A4B012 - 1475890736 - 0 - 0 - 0 ms\n'
            'ᵒᵃᵗˢCryptic - 600DB838AC62BDE9 - 1571692528 - 0 - 0 - 2 ms\n'
            'Ø₳T̷S̷ artisanal miner - 285FE56F575A3DB0 - -820817664 - 235 - 4 - 3 ms'
        )
        players = parse_players(data)
        self.populate(players)

    def _run_command_thread(self, command_text):
        key = self.key_entry.get().strip() or '`'
        if self.debug_window is not None:
            line = f'{key} {command_text}'
            self.root.after(0, lambda t=line: self._debug_insert(t))
            self.root.after(0, lambda t=line: self.set_status(f'[DEBUG] Intercepted: {t}'))
            return
        title = self.win_entry.get().strip()
        self.set_status(f"Sending: {command_text}")
        ok = send_command_to_game(title, command_text, key)
        if ok:
            self.set_status('Command sent')
        else:
            self.set_status('Command failed')

    def clear_players(self):
        self.all_players = []
        self._item_players.clear()
        self._last_parsed = None
        for i in self.tree.get_children():
            self.tree.delete(i)
        self._clear_details()
        self.detfrm.config(text='Player Details')
        self.set_status('Cleared.')

    def on_run(self):
        if not check_deps():
            return
        key = self.key_entry.get().strip() or '`'
        if self.debug_window is not None:
            line = f'{key} listplayers'
            self._debug_insert(line)
            self.set_status(f"[DEBUG] Intercepted: {line}")
            return
        self.set_status("Running 'listplayers'...")
        self._log_action('ListPlayers')
        t = threading.Thread(target=self._run_thread, daemon=True)
        t.start()

    def _run_thread(self):
        title = self.win_entry.get().strip()
        key = self.key_entry.get().strip() or '`'

        def status(msg):
            self.root.after(0, lambda m=msg: self.set_status(m))

        clip = send_listplayers_to_game(title, key, status_callback=status)
        if not clip:
            self.root.after(0, lambda: self.set_status('No clipboard output received.'))
            self.root.after(0, self._return_focus)
            return
        players = parse_players(clip)
        self.root.after(0, lambda: self.populate(players))
        self.root.after(100, self._return_focus)

    def kick_by_id(self):
        pid = (self.id_entry.get() or '').strip()
        reason = (self.reason_entry.get() or '').strip()
        if not pid:
            messagebox.showerror('Missing id', 'Please enter a PlayFabId to kick')
            return
        if reason:
            reason = reason.replace('"', "'")
            cmd = f'kickbyid {pid} "{reason}"'
        else:
            cmd = f'kickbyid {pid}'
        self._log_action('Kick', f'{pid} - {reason or "no reason"}')
        threading.Thread(target=self._run_command_thread, args=(cmd,), daemon=True).start()

    def ban_by_id(self):
        pid = (self.id_entry.get() or '').strip()
        dur = (self.duration_entry.get() or '').strip()
        reason = (self.reason_entry.get() or '').strip()
        if not pid or not dur:
            messagebox.showerror('Missing fields', 'Please enter PlayFabId and duration (hours)')
            return
        # ensure numeric hours
        try:
            hours = int(dur)
        except ValueError:
            messagebox.showerror('Invalid duration', 'Duration must be an integer number of hours')
            return
        if reason:
            reason = reason.replace('"', "'")
            cmd = f'banbyid {pid} {hours} "{reason}"'
        else:
            cmd = f'banbyid {pid} {hours}'
        self._log_action('Ban', f'{pid} {hours}h - {reason or "no reason"}')
        threading.Thread(target=self._run_command_thread, args=(cmd,), daemon=True).start()

    def unban_by_id(self):
        pid = (self.id_entry.get() or '').strip()
        if not pid:
            messagebox.showerror('Missing id', 'Please enter a PlayFabId to unban')
            return
        cmd = f'unbanbyid {pid}'
        self._log_action('Unban', pid)
        threading.Thread(target=self._run_command_thread, args=(cmd,), daemon=True).start()

    def serversay(self):
        msg = (self.msg_entry.get() or '').strip()
        if not msg:
            messagebox.showerror('Missing message', 'Please enter a message to send')
            return
        if ' ' in msg:
            msg = msg.replace('"', "'")
            msg = f'"{msg}"'
        cmd = f'serversay {msg}'
        self._log_action('ServerSay', msg)
        threading.Thread(target=self._run_command_thread, args=(cmd,), daemon=True).start()

    def _panel_end_game(self):
        if messagebox.askyesno('End Game', 'End the current match?'):
            self._log_action('EndGame')
            threading.Thread(target=self._run_command_thread, args=('TBSendgame',), daemon=True).start()

    def _panel_add_stage(self):
        try:
            mins = float((self._panel_stage_entry.get() or '').strip())
        except ValueError:
            messagebox.showerror('Invalid time', 'Enter minutes (e.g. 0.5 for 30s, -0.5 for -30s)')
            return
        cmd = f'TBSaddstagetime {mins}'
        self._log_action('AddStageTime', f'{mins}m')
        threading.Thread(target=self._run_command_thread, args=(cmd,), daemon=True).start()

    def toggle_right_panel(self):
        if self._right_panel.winfo_viewable():
            self._right_panel.pack_forget()
        else:
            self._right_panel.pack(side='right', fill='y', padx=(0, 8), pady=(0, 8))

    def adminsay(self):
        msg = (self.msg_entry.get() or '').strip()
        if not msg:
            messagebox.showerror('Missing message', 'Please enter a message to send')
            return
        if ' ' in msg:
            msg = msg.replace('"', "'")
            msg = f'"{msg}"'
        cmd = f'adminsay {msg}'
        self._log_action('AdminSay', msg)
        threading.Thread(target=self._run_command_thread, args=(cmd,), daemon=True).start()

    def add_bots(self):
        amount = (self._extra_bots_entry.get() or '').strip()
        if not amount:
            messagebox.showerror('Missing amount', 'Enter the number of bots to add')
            return
        cmd = f'addbots {amount}'
        self._log_action('AddBots', amount)
        threading.Thread(target=self._run_command_thread, args=(cmd,), daemon=True).start()

    def remove_bots(self):
        cmd = 'removebots 1 1'
        self._log_action('RemoveBots')
        threading.Thread(target=self._run_command_thread, args=(cmd,), daemon=True).start()

    def start_game(self):
        cmd = 'TBSmanuallystartgame'
        self._log_action('StartGame')
        threading.Thread(target=self._run_command_thread, args=(cmd,), daemon=True).start()

    def stat_fps(self):
        cmd = 'stat fps'
        self._log_action('StatFPS')
        threading.Thread(target=self._run_command_thread, args=(cmd,), daemon=True).start()

    def disconnect(self):
        cmd = 'disconnect'
        self._log_action('Disconnect')
        threading.Thread(target=self._run_command_thread, args=(cmd,), daemon=True).start()

    def exit_game(self):
        cmd = 'exit'
        self._log_action('Exit')
        threading.Thread(target=self._run_command_thread, args=(cmd,), daemon=True).start()

    def toggle_hud(self):
        cmd = 'togglehud'
        self._log_action('ToggleHUD')
        threading.Thread(target=self._run_command_thread, args=(cmd,), daemon=True).start()

    def populate(self, players, set_all=True):
        if set_all:
            self.all_players = players
        for i in self.tree.get_children():
            self.tree.delete(i)
        self._clear_details()
        self._item_players.clear()
        if not players:
            self.detfrm.config(text='Player Details')
            self.set_status('No players parsed from clipboard.')
            return
        seen = set()
        count = 0
        for p in players:
            pid = p.get('playfab_id', '')
            if pid in seen:
                continue
            seen.add(pid)
            try:
                iid = self.tree.insert('', tk.END, values=(p.get('name', ''),))
            except Exception:
                continue
            self._item_players[iid] = p
            count += 1
        self.detfrm.config(text=f'Player Details ({count} players)')
        self.set_status(f'Parsed {count} players.')

    def _on_search_key(self, event=None):
        if hasattr(self, '_search_debounce') and self._search_debounce:
            self.root.after_cancel(self._search_debounce)
        self._search_debounce = self.root.after(200, self.on_search)

    def on_search(self, event=None):
        q = (self.search_entry.get() or '').strip()
        for item in self.tree.get_children():
            self.tree.item(item, tags=())
        if not q:
            self.set_status(f'{len(self.all_players)} players')
            return
        qf = q.casefold()
        matching = []
        for item in self.tree.get_children():
            p = self._item_players.get(item)
            if p and qf in (p.get('name', '') or '').casefold():
                matching.append(item)
                self.tree.item(item, tags=('match',))
        if len(matching) == 1:
            self.tree.selection_set(matching[0])
            self.tree.see(matching[0])
            self.on_select()
            p = self._item_players.get(matching[0])
            self.set_status(f'{p["name"]} matched' if p else '1 matched')
        else:
            self.set_status(f'{len(matching)} players matched')

    def clear_search(self):
        self.search_entry.delete(0, tk.END)
        for item in self.tree.get_children():
            self.tree.item(item, tags=())
        self.set_status(f'{len(self.all_players)} players')

    def _player_from_sel(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return self._item_players.get(sel[0])

    def copy_selected(self):
        p = self._player_from_sel()
        if not p:
            return
        if not check_deps():
            return
        try:
            pyperclip.copy(p['playfab_id'])
            self.set_status('PlayFabId copied to clipboard.')
        except Exception as e:
            messagebox.showerror('Clipboard error', str(e))

    def on_select(self, event=None):
        p = self._player_from_sel()
        if not p:
            return
        self.id_entry.delete(0, tk.END)
        self.id_entry.insert(0, p['playfab_id'])
        self._show_details(p)
        self.set_status(p['name'])

    def on_double_click(self, event=None):
        p = self._player_from_sel()
        if not p:
            return
        if not check_deps():
            return
        try:
            pyperclip.copy(p['playfab_id'])
            self.set_status('PlayFabId copied to clipboard.')
        except Exception as e:
            messagebox.showerror('Clipboard error', str(e))

    def _clear_details(self):
        for attr in ('detail_name', 'detail_playfab', 'detail_score', 'detail_kills', 'detail_deaths'):
            getattr(self, attr).config(text='')
        self.alias_listbox.delete(0, tk.END)

    def _show_details(self, p):
        self.detail_name.config(text=f"Name: {p.get('name', '')}")
        self.detail_playfab.config(text=f"PlayFabId: {p.get('playfab_id', '')}")
        self.detail_score.config(text=f"Score: {p.get('score', 'N/A')}")
        self.detail_kills.config(text=f"Kills: {p.get('kills', 'N/A')}")
        self.detail_deaths.config(text=f"Deaths: {p.get('deaths', '')}")

    def show_past_names(self):
        p = self._player_from_sel()
        if not p:
            messagebox.showinfo('Past Names', 'Select a player first.')
            return
        pid = p['playfab_id']
        self.set_status(f'Fetching past names for {p["name"]}...')
        threading.Thread(target=self._fetch_and_show_aliases, args=(pid,), daemon=True).start()

    def _fetch_and_show_aliases(self, playfab_id):
        aliases = fetch_aliases(playfab_id)
        self.root.after(0, self._display_aliases, aliases)

    def _display_aliases(self, aliases):
        self.alias_listbox.delete(0, tk.END)
        if not aliases:
            self.set_status('No alias history found.')
            return
        for name in aliases:
            self.alias_listbox.insert(tk.END, name)
        self.set_status(f'Found {len(aliases)} past names.')

    def _return_focus(self):
        try:
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def paste_clipboard(self):
        if not check_deps():
            return
        try:
            raw = pyperclip.paste()
        except Exception as e:
            messagebox.showerror('Clipboard error', str(e))
            return
        players = parse_players(raw)
        self.populate(players)


def main():
    try:
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == '__main__':
    main()