import ctypes
import http.cookiejar
import json
import os
import re
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
import urllib.request
import urllib.parse

try:
    import pygetwindow as gw
    import pyperclip
except Exception:
    gw = None
    pyperclip = None

_UA = 'Mozilla/5.0'
_TIMEOUT = 10
_CAP_TIMEOUT = 15

_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'name_cache.json')
_player_name_cache: dict[str, str] = {}


def _load_name_cache():
    try:
        with open(_CACHE_FILE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            _player_name_cache.update(data)
    except Exception:
        pass


def _save_name_cache():
    try:
        with open(_CACHE_FILE, 'w') as f:
            json.dump(_player_name_cache, f, indent=2)
    except Exception:
        pass


_load_name_cache()


def search_chiv2stats(query):
    try:
        if query and re.match(r'^[A-Fa-f0-9]{16}$', query):
            cached = _player_name_cache.get(query)
            if cached:
                return [{'name': cached, 'playfab_id': query}], None
            url = f'https://chivalry2stats.com/player?id={query}'
            req = urllib.request.Request(url, headers={'User-Agent': _UA})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                html = resp.read().decode('utf-8', errors='replace')
            m = re.search(r'\\"aliasHistory\\":\\"([^\\]*)\\"', html)
            if m:
                raw = m.group(1)
                aliases = [a.strip() for a in raw.split(',') if a.strip()]
                if aliases:
                    _player_name_cache[query] = aliases[-1]
                    return [{'name': aliases[-1], 'playfab_id': query}], None
            return [], None

        all_players = []
        seen = set()
        pattern = re.compile(
            r'href=["\']/player\?id=([A-Fa-f0-9]{16})["\'][^>]*>.*?'
            r'<span[^>]*class=["\'][^"\']*text-xs[^"\']*["\'][^>]*>([^<]+)</span>',
            re.DOTALL,
        )
        for p in range(1, 4):
            url = f'https://chivalry2stats.com/player?username={urllib.parse.quote(query)}&page={p}'
            req = urllib.request.Request(url, headers={'User-Agent': _UA})
            try:
                with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                    html = resp.read().decode('utf-8', errors='replace')
            except Exception:
                break
            found = 0
            for m in pattern.finditer(html):
                pid = m.group(1)
                if pid not in seen:
                    seen.add(pid)
                    all_players.append({'name': m.group(2), 'playfab_id': pid})
                    found += 1
            if found == 0:
                break
        return (all_players if all_players else []), None

    except Exception as e:
        return None, str(e)


def fetch_aliases(playfab_id):
    try:
        url = f'https://chivalry2stats.com/player?id={playfab_id}'
        req = urllib.request.Request(url, headers={'User-Agent': _UA})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            html = resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        return None, str(e)

    m = re.search(r'\\"aliasHistory\\":\\"([^\\]*)\\"', html)
    if not m:
        return [], None
    raw = m.group(1)
    aliases = [a.strip() for a in raw.split(',') if a.strip()]

    if playfab_id not in _player_name_cache and aliases:
        _player_name_cache[playfab_id] = aliases[-1]

    aliases.reverse()
    return (aliases if aliases else []), None


def fetch_capdev_events(playfab_id, server_id=17):
    try:
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        opener.addheaders = [('User-Agent', _UA)]

        login_data = urllib.parse.urlencode({'username': 'SimplySkidz', 'password': 'hidden'}).encode()
        opener.open('https://cap-dev.notmyrealname.fyi/auth/login', data=login_data)

        events = []
        pattern = re.compile(
            r'data-event-id="(\d+)".*?'
            r'<div class="col border">\s*(.*?)\s*</div>.*?'
            r'<div class="col border">\s*(.*?)\s*</div>.*?'
            r'<div class="col border col-1">\s*(.*?)\s*</div>.*?'
            r'<div class="col border col-1">\s*(.*?)\s*</div>.*?'
            r'<div class="col border text-truncate">.*?<a[^>]*>(.*?)</a>.*?'
            r'<div class="col border">\s*(.*?)\s*</div>.*?'
            r'<div class="col border col-1">\s*(.*?)\s*</div>',
            re.DOTALL
        )
        page = 1
        while True:
            params = urllib.parse.urlencode({
                'serverID': server_id,
                'eventType': ['ban', 'kick', 'unban'],
                'page': page,
                'playerID': playfab_id
            }, doseq=True)
            req = urllib.request.Request(
                f'https://cap-dev.notmyrealname.fyi/api/v1/player/event/query?{params}'
            )
            req.add_header('HX-Request', 'true')
            req.add_header('HX-Target', 'player-events-table')
            resp = opener.open(req, timeout=_CAP_TIMEOUT)
            html = resp.read().decode('utf-8', errors='replace')
            found = 0
            for m in pattern.finditer(html):
                found += 1
                events.append({
                    'id': m.group(1),
                    'date': m.group(2).strip(),
                    'server': m.group(3).strip(),
                    'duration': m.group(4).strip(),
                    'type': m.group(5).strip(),
                    'reason': m.group(6).strip(),
                    'admin': m.group(7).strip(),
                    'player_id': m.group(8).strip(),
                })
            if found == 0:
                break
            page += 1
    except Exception as e:
        return None, str(e)

    return (events if events else []), None


class PlayerInfoDisplay:
    TAB_ACTIVE = '#c8a050'
    TAB_INACTIVE = '#ede0c8'

    def __init__(self, detail_name, detail_playfab, detail_stats,
                 names_listbox, history_listbox, cap_summary,
                 tab_aliases, tab_history, root):
        self.detail_name = detail_name
        self.detail_playfab = detail_playfab
        self.detail_stats = detail_stats
        self.names_listbox = names_listbox
        self.history_listbox = history_listbox
        self.cap_summary = cap_summary
        self._tab_aliases = tab_aliases
        self._tab_history = tab_history
        self.root = root
        self._active_view = 'aliases'
        self._current_pid = None
        self._current_tip = None
        self._player_cache = {}
        self.history_listbox.bind('<Button-1>', self._show_event_details)
        self.root.bind('<Button-1>', self._dismiss_tip, '+')

    def switch_view(self, view):
        if view == self._active_view:
            return
        self._active_view = view
        self._tab_aliases.config(
            bg=self.TAB_ACTIVE if view == 'aliases' else self.TAB_INACTIVE,
        )
        self._tab_history.config(
            bg=self.TAB_ACTIVE if view == 'history' else self.TAB_INACTIVE,
        )
        if view == 'aliases':
            self.history_listbox.pack_forget()
            self.names_listbox.pack(fill='both', expand=True)
            if self._current_pid and self.names_listbox.size() == 0:
                cached = self._player_cache.get(self._current_pid)
                if cached:
                    if cached.get('aliases_error'):
                        self.names_listbox.delete(0, tk.END)
                        self.names_listbox.insert(tk.END, f'Error: {cached["aliases_error"]}')
                    elif cached['aliases'] is not None:
                        self._populate_listbox(self.names_listbox, cached['aliases'], 'No aliases found')
                    elif cached['aliases'] is None:
                        self.names_listbox.delete(0, tk.END)
                        self.names_listbox.insert(tk.END, 'Loading...')
        else:
            self.names_listbox.pack_forget()
            self.history_listbox.pack(fill='both', expand=True)
            if self._current_pid and self.history_listbox.size() == 0:
                cached = self._player_cache.get(self._current_pid)
                if cached:
                    if cached.get('cap_error'):
                        self.history_listbox.delete(0, tk.END)
                        self.history_listbox.insert(tk.END, f'Error: {cached["cap_error"]}')
                    elif cached['cap_events'] is not None:
                        self._populate_cap_listbox(cached['cap_events'])
                    elif cached['cap_events'] is None:
                        self.history_listbox.delete(0, tk.END)
                        self.history_listbox.insert(tk.END, 'Loading...')

    def clear_cache(self):
        self._player_cache.clear()

    def clear_details(self):
        self.detail_name.config(text='')
        self.detail_playfab.config(text='')
        self.detail_stats.config(text='')
        self.cap_summary.config(text='')
        self.names_listbox.delete(0, tk.END)
        self.history_listbox.delete(0, tk.END)
        self._current_pid = None
        if self._active_view != 'aliases':
            self.switch_view('aliases')

    def show_details(self, p):
        self.detail_name.config(text=p.get('name', ''))
        pid = p.get('playfab_id', '')
        self.detail_playfab.config(text=pid)
        s = p.get('score', '?')
        k = p.get('kills', '?')
        d = p.get('deaths', '?')
        self.detail_stats.config(text=f'Score: {s}  Kills: {k}  Deaths: {d}')
        if pid == self._current_pid:
            return
        self._current_pid = pid
        cached = self._player_cache.get(pid)
        if cached:
            self._display_aliases(cached['aliases'], cached.get('aliases_error'))
            self._display_cap_history(cached['cap_events'], cached.get('cap_error'))
            self.cap_summary.config(text=cached['cap_text'], foreground=cached['cap_fg'])
            return
        _CACHE_LIMIT = 500
        if len(self._player_cache) >= _CACHE_LIMIT:
            try:
                self._player_cache.pop(next(iter(self._player_cache)))
            except (StopIteration, KeyError):
                pass
        self._player_cache[pid] = {'aliases': None, 'cap_events': None, 'aliases_error': None, 'cap_error': None, 'cap_text': '', 'cap_fg': '#2b1a0e'}
        self.names_listbox.delete(0, tk.END)
        self.history_listbox.delete(0, tk.END)
        self.cap_summary.config(text='')
        if self._active_view == 'aliases':
            self.names_listbox.insert(tk.END, 'Loading...')
        else:
            self.history_listbox.insert(tk.END, 'Loading...')
        threading.Thread(target=self._fetch_aliases, args=(pid,), daemon=True).start()
        threading.Thread(target=self._fetch_cap, args=(pid,), daemon=True).start()

    def _fetch_aliases(self, playfab_id):
        aliases, error = fetch_aliases(playfab_id)
        entry = self._player_cache.setdefault(playfab_id, {})
        entry['aliases'] = aliases or []
        entry['aliases_error'] = error
        self.root.after(0, self._display_aliases, entry['aliases'], error)

    def _fetch_cap(self, playfab_id):
        events, error = fetch_capdev_events(playfab_id)
        entry = self._player_cache.setdefault(playfab_id, {})
        entry['cap_events'] = events or []
        entry['cap_error'] = error
        self.root.after(0, self._update_cap_summary, entry['cap_events'], entry, error)
        self.root.after(50, self._display_cap_history, entry['cap_events'], error)

    def _update_cap_summary(self, events, entry=None, error=None):
        if error:
            text = f'ERR: {error}'
            fg = '#8b0000'
        elif not events:
            text = 'No history'
            fg = '#2b1a0e'
        else:
            bans = sum(1 for e in events if e['type'] == 'Ban')
            kicks = sum(1 for e in events if e['type'] == 'Kick')
            text = f'B:{bans} K:{kicks}'
            fg = '#8b0000' if bans >= 3 else '#b8860b' if bans > 0 else '#2b1a0e'
        self.cap_summary.config(text=text, foreground=fg)
        if entry:
            entry['cap_text'] = text
            entry['cap_fg'] = fg

    def _display_aliases(self, aliases, error=None):
        if self._current_pid and self._current_pid not in self._player_cache:
            return
        if error:
            self.names_listbox.delete(0, tk.END)
            self.names_listbox.insert(tk.END, f'Error: {error}')
            return
        self._populate_listbox(self.names_listbox, aliases, 'No aliases found')

    def _display_cap_history(self, events, error=None):
        if self._current_pid and self._current_pid not in self._player_cache:
            return
        if error:
            self.history_listbox.delete(0, tk.END)
            self.history_listbox.insert(tk.END, f'Error: {error}')
            return
        self._populate_cap_listbox(events)

    def _dismiss_tip(self, event):
        if not self._current_tip:
            return
        if event.widget == self.history_listbox:
            return
        try:
            self._current_tip.destroy()
        except tk.TclError:
            pass
        self._current_tip = None

    def _show_event_details(self, event):
        if self._current_tip:
            self._current_tip.destroy()
            self._current_tip = None
        sel = self.history_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < 2:
            return
        events = self._player_cache.get(self._current_pid, {}).get('cap_events', [])
        ev_idx = idx - 2
        if ev_idx >= len(events):
            return
        ev = events[ev_idx]
        reason = ev['reason'].strip()
        if not reason:
            return

        tip = tk.Toplevel(self.root)
        tip.overrideredirect(True)
        tip.attributes('-topmost', True)

        shadow = tk.Frame(tip, bg='#1a0f08')
        shadow.pack(padx=2, pady=2)
        inner = tk.Frame(shadow, bg='#faf0dc', highlightbackground='#2b1a0e',
                         highlightthickness=1)
        inner.pack(padx=0, pady=0)

        lbl = tk.Label(inner, text=reason, font=('Consolas', 9),
                       bg='#faf0dc', fg='#2b1a0e',
                       anchor='w', justify='left',
                       wraplength=400, padx=10, pady=6)
        lbl.pack()

        tip.update_idletasks()
        sw = tip.winfo_screenwidth()
        sh = tip.winfo_screenheight()
        tw = tip.winfo_reqwidth()
        th = tip.winfo_reqheight()
        x = min(event.x_root + 15, sw - tw - 10)
        y = min(event.y_root + 10, sh - th - 10)
        tip.geometry(f'+{x}+{y}')

        def dismiss(*_):
            tip.destroy()
            self._current_tip = None
        tip.bind('<Button>', dismiss)
        tip.bind('<Key>', dismiss)
        self._current_tip = tip

    def _populate_listbox(self, listbox, items, empty_text):
        listbox.delete(0, tk.END)
        if not items:
            listbox.insert(tk.END, empty_text)
            return
        for item in items:
            listbox.insert(tk.END, item)

    def _populate_cap_listbox(self, events):
        self.history_listbox.delete(0, tk.END)
        if not events:
            self.history_listbox.insert(tk.END, 'No history found')
            return

        header = f"{'Type':<6} {'Date':<10} {'Dur':>4}  {'Admin':<22} Reason"
        sep = '─' * 60
        self.history_listbox.insert(tk.END, header)
        self.history_listbox.insert(tk.END, sep)

        for ev in events:
            date = ev['date'].split('+')[0].strip()[:10]
            dur = ev['duration'].strip()
            admin = ev['admin'].strip()[:22]
            reason = ev['reason'].strip()
            line = f"{ev['type']:<6} {date:<10} {dur:>3}h  {admin:<22} {reason}"
            self.history_listbox.insert(tk.END, line)

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
VK_SHIFT = 0x10
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
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,
    0x2D, 0x2E,
    0x5B, 0x5C, 0x5D,
}

_HEX_RE = re.compile(r'^[A-Fa-f0-9]{15,}$')


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
        attached = False
        try:
            ctypes.windll.user32.AttachThreadInput(current_tid, fg_tid, True)
            ctypes.windll.user32.AttachThreadInput(current_tid, target_tid, True)
            attached = True
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
            ctypes.windll.user32.BringWindowToTop(hwnd)
            ctypes.windll.user32.SetActiveWindow(hwnd)
        finally:
            if attached:
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


_CHAR_VK_CACHE: dict[str, tuple[int, int]] = {}
def _char_vk_and_mods(ch):
    cached = _CHAR_VK_CACHE.get(ch)
    if cached is not None:
        return cached
    vk_mods = ctypes.windll.user32.VkKeyScanW(ord(ch))
    vk = vk_mods & 0xFF
    mods = (vk_mods >> 8) & 0xFF
    _CHAR_VK_CACHE[ch] = (vk, mods)
    return (vk, mods)


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


def _post_message(hwnd, vk, keyup):
    if not hwnd or vk is None:
        return False
    msg = WM_KEYUP if keyup else WM_KEYDOWN
    return bool(ctypes.windll.user32.PostMessageW(hwnd, msg, vk, make_key_lparam(vk, keyup=keyup)))


def press_keydown(hwnd, vk):
    return _post_message(hwnd, vk, keyup=False)


def press_keyup(hwnd, vk):
    return _post_message(hwnd, vk, keyup=True)


def _execute_vk_sequence(vks, press_fn, release_fn):
    if not vks:
        return False
    for vk in vks:
        if not press_fn(vk):
            return False
        time.sleep(0.02)
    for vk in reversed(vks):
        if not release_fn(vk):
            return False
        time.sleep(0.02)
    return True


def send_key_sequence(hwnd, key_sequence):
    try:
        vks = parse_key_sequence(key_sequence)
    except ValueError:
        return False
    return _execute_vk_sequence(
        vks,
        lambda vk: press_keydown(hwnd, vk),
        lambda vk: press_keyup(hwnd, vk),
    )


def post_key(hwnd, vk):
    if not hwnd or vk is None:
        return False
    res_down = press_keydown(hwnd, vk)
    time.sleep(0.01)
    res_up = press_keyup(hwnd, vk)
    time.sleep(0.01)
    return res_down and res_up


def _post_char(hwnd, ch):
    vk, mods = _char_vk_and_mods(ch)
    if vk == 0xFF:
        return False
    need_shift = bool(mods & 0x01)
    if need_shift and not _post_message(hwnd, VK_SHIFT, False):
        return False
    if not _post_message(hwnd, vk, False):
        if need_shift:
            _post_message(hwnd, VK_SHIFT, True)
        return False
    time.sleep(0.01)
    if not _post_message(hwnd, vk, True):
        if need_shift:
            _post_message(hwnd, VK_SHIFT, True)
        return False
    time.sleep(0.01)
    if need_shift and not _post_message(hwnd, VK_SHIFT, True):
        return False
    return True


def post_text(hwnd, text):
    if not hwnd or not text:
        return False
    for ch in text:
        if not _post_char(hwnd, ch):
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


def _send_system_char(ch):
    vk, mods = _char_vk_and_mods(ch)
    if vk == 0xFF:
        return False
    need_shift = bool(mods & 0x01)
    if need_shift and not send_system_key(VK_SHIFT, keyup=False):
        return False
    if not send_system_key(vk, keyup=False):
        if need_shift:
            send_system_key(VK_SHIFT, keyup=True)
        return False
    time.sleep(0.01)
    if not send_system_key(vk, keyup=True):
        if need_shift:
            send_system_key(VK_SHIFT, keyup=True)
        return False
    time.sleep(0.01)
    if need_shift and not send_system_key(VK_SHIFT, keyup=True):
        return False
    return True


def send_system_text(text):
    for ch in text:
        if not _send_system_char(ch):
            return False
    return True


def paste_text_via_clipboard(hwnd, text):
    if not text or not hwnd:
        return False
    try:
        old_clip = pyperclip.paste()
    except Exception:
        old_clip = None

    success = False
    try:
        pyperclip.copy(text)
        ctypes.windll.user32.SendMessageW(hwnd, WM_PASTE, 0, 0)
        time.sleep(0.05)
        success = True
    except Exception:
        pass
    finally:
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
    return _execute_vk_sequence(
        vks,
        lambda vk: send_system_key(vk, keyup=False),
        lambda vk: send_system_key(vk, keyup=True),
    )


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

    _execute_vk_sequence(vks, lambda vk: press_keydown(hwnd, vk), lambda vk: press_keyup(hwnd, vk))

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


def parse_players(text):
    if not text:
        return []
    players = []
    lines = text.splitlines()

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
            if _HEX_RE.fullmatch(pid):
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
                if _HEX_RE.fullmatch(candidate):
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
        ttk.Label(topfrm, text='Source:').pack(side='left')

        SRC_INACTIVE = '#ede0c8'
        SRC_ACTIVE = '#c8a050'
        SRC_FG = '#2b1a0e'
        srcfrm = tk.Frame(topfrm, bg='#f5e6c8')
        srcfrm.pack(side='left', padx=(4, 10))
        self._src_game = tk.Label(
            srcfrm, text='Chivalry 2', anchor='center',
            bg=SRC_ACTIVE, fg=SRC_FG,
            font=('Palatino Linotype', 9, 'bold'),
            padx=8, pady=2, cursor='hand2',
        )
        self._src_game.pack(side='left', padx=(0, 1))
        self._src_game.bind('<Button-1>', lambda _: self._set_source('game'))
        self._bind_status_tip(self._src_game, 'Use game as player source')
        self._src_stats = tk.Label(
            srcfrm, text='Chiv2Stats', anchor='center',
            bg=SRC_INACTIVE, fg=SRC_FG,
            font=('Palatino Linotype', 9, 'bold'),
            padx=8, pady=2, cursor='hand2',
        )
        self._src_stats.pack(side='left', padx=(1, 0))
        self._src_stats.bind('<Button-1>', lambda _: self._set_source('stats'))
        self._bind_status_tip(self._src_stats, 'Use Chiv2Statsc as player source')

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

        detfrm = ttk.LabelFrame(mainfrm, text='Player Details', width=300)
        self.detfrm = detfrm
        detfrm.pack(side='left', fill='y', padx=(8, 0))
        detfrm.pack_propagate(False)

        # Player identity / details
        self.detail_name = ttk.Label(
            detfrm, text='', anchor='w', font=('Palatino Linotype', 11, 'bold'),
        )
        self.detail_name.pack(fill='x', padx=8, pady=(8, 0))
        self.detail_playfab = ttk.Label(
            detfrm, text='', anchor='w', font=('Consolas', 9),
        )
        self.detail_playfab.pack(fill='x', padx=8, pady=(0, 1))
        self.detail_stats = ttk.Label(detfrm, text='', anchor='w')
        self.detail_stats.pack(fill='x', padx=8, pady=(0, 0))
        self.cap_summary = ttk.Label(detfrm, text='', anchor='e',
                                     font=('Consolas', 9))
        self.cap_summary.pack(fill='x', padx=8, pady=(0, 4))

        # Styled toggle tabs
        TAB_INACTIVE = '#ede0c8'
        TAB_ACTIVE = '#c8a050'
        TAB_FG = '#2b1a0e'
        tabfrm = tk.Frame(detfrm, bg='#f5e6c8')
        tabfrm.pack(fill='x', padx=8, pady=(4, 0))
        self._tab_aliases = tk.Label(
            tabfrm, text='Alias History', anchor='center',
            bg=TAB_ACTIVE, fg=TAB_FG,
            font=('Palatino Linotype', 9, 'bold'),
            padx=8, pady=3, cursor='hand2',
        )
        self._tab_aliases.pack(side='left', fill='x', expand=True, padx=(0, 1))
        self._tab_aliases.bind('<Button-1>', lambda _: self.player_info.switch_view('aliases'))
        self._bind_status_tip(self._tab_aliases, 'View player alias history')
        self._tab_history = tk.Label(
            tabfrm, text='Ban History', anchor='center',
            bg=TAB_INACTIVE, fg=TAB_FG,
            font=('Palatino Linotype', 9, 'bold'),
            padx=8, pady=3, cursor='hand2',
        )
        self._tab_history.pack(side='left', fill='x', expand=True, padx=(1, 0))
        self._tab_history.bind('<Button-1>', lambda _: self.player_info.switch_view('history'))
        self._bind_status_tip(self._tab_history, 'View player ban/kick history')

        # Shared content area
        info_content = ttk.Frame(detfrm)
        info_content.pack(fill='both', expand=True, padx=8, pady=(4, 6))

        self.names_listbox = tk.Listbox(
            info_content, font=('Consolas', 10),
            bg='#faf0dc', fg='#2b1a0e',
            selectbackground='#c8a050', selectforeground='#2b1a0e',
        )
        self.names_listbox.pack(fill='both', expand=True)
        self.history_listbox = tk.Listbox(
            info_content, font=('Consolas', 10),
            bg='#faf0dc', fg='#2b1a0e',
            selectbackground='#c8a050', selectforeground='#2b1a0e',
        )

        # search + actions bar
        barbtnfrm = ttk.Frame(left)
        barbtnfrm.pack(fill='x', padx=8, pady=(0, 6))
        ttk.Label(barbtnfrm, text='Search:').pack(side='left')
        self.search_entry = ttk.Entry(barbtnfrm, width=20)
        self.search_entry.pack(side='left', padx=(4, 4))
        self.search_entry.bind('<KeyRelease>', self._on_search_key)
        self.search_entry.bind('<Return>', self.on_search)
        self.search_entry.bind('<Escape>', lambda _: self.clear_search())
        btn = ttk.Button(barbtnfrm, text='Copy PFId', command=self.copy_selected)
        btn.pack(side='left', padx=(10, 0))
        self._bind_status_tip(btn, 'Copy selected player PlayFabId to clipboard')
        btn = ttk.Button(barbtnfrm, text="List Players", command=self.on_run)
        btn.pack(side='left', padx=(6, 0))
        self._bind_status_tip(btn, 'Fetch players from current source')

        self._source_mode = 'game'
        self._window_title = 'Chivalry 2'
        self.all_players = []
        self._item_players = {}
        self._last_parsed = None
        self._search_request_id = 0
        self.reason_presets = [
            'Ping - Removed from server for harmful ping',
            'RDM - This is not FFA. Please flourish to duel (M3, L3+Square, L3+X)',
        ]
        self.debug_window = None
        self.debug_text = None
        self.action_log = []
        self._log_window = None
        self._settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings.json')
        self._load_settings()

        self.player_info = PlayerInfoDisplay(
            self.detail_name, self.detail_playfab, self.detail_stats,
            self.names_listbox, self.history_listbox, self.cap_summary,
            self._tab_aliases, self._tab_history, root,
        )

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
        reason_lbl = tk.Label(row1, text='Reason:', anchor='center',
                               bg=BTN_BG, fg=FG,
                               font=('Palatino Linotype', 9, 'bold'),
                               padx=6, pady=2, cursor='hand2')
        reason_lbl.pack(side='left', padx=(0, 4))
        reason_lbl.bind('<Button-1>', lambda _: self._manage_presets())
        reason_lbl.bind('<Enter>', lambda _: reason_lbl.config(bg=BTN_ACTIVE))
        reason_lbl.bind('<Leave>', lambda _: reason_lbl.config(bg=BTN_BG))
        self._bind_status_tip(reason_lbl, 'Manage reason presets')
        self.reason_entry = ttk.Combobox(row1, values=self.reason_presets, width=28)
        self.reason_entry.pack(side='left', padx=(4, 8))
        self._kick_btn = ttk.Button(row1, text='Kick', command=self.kick_by_id)
        self._kick_btn.pack(side='left')
        self._bind_status_tip(self._kick_btn, 'Kick player by PlayFabId')
        self._ban_btn = ttk.Button(row1, text='Ban', command=self.ban_by_id)
        self._ban_btn.pack(side='left', padx=(4, 0))
        self._bind_status_tip(self._ban_btn, 'Ban player by PlayFabId with duration and reason')
        self._unban_btn = ttk.Button(row1, text='Unban', command=self.unban_by_id)
        self._unban_btn.pack(side='left', padx=(4, 0))
        self._bind_status_tip(self._unban_btn, 'Unban player by PlayFabId')

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
        btn = ttk.Button(row2, text='Extras \u25b6', command=self.toggle_right_panel)
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
            widget._saved_status = self.status.cget('text')
            self.status.config(text=text)
        def clear_tip(e):
            saved = getattr(widget, '_saved_status', None)
            self.status.config(text=saved if saved is not None else 'Ready')
            widget._saved_status = None
        widget.bind('<Enter>', show_tip)
        widget.bind('<Leave>', clear_tip)

    def set_status(self, text):
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
        if 'reason_presets' in s and s['reason_presets']:
            seen = set(self.reason_presets)
            for p in s['reason_presets']:
                if p not in seen:
                    self.reason_presets.append(p)
                    seen.add(p)
            if hasattr(self, 'reason_entry'):
                self.reason_entry['values'] = self.reason_presets

    def _save_settings(self):
        s = {
            'console_key': self.key_entry.get().strip() or '`',
            'reason_presets': self.reason_presets,
        }
        try:
            with open(self._settings_file, 'w') as f:
                json.dump(s, f, indent=2)
        except Exception:
            pass

    def _manage_presets(self):
        win = tk.Toplevel(self.root)
        win.title('Reason Presets')
        win.geometry('360x320')
        win.transient(self.root)
        win.configure(bg='#f5e6c8')
        win.grab_set()

        frm = ttk.Frame(win)
        frm.pack(fill='both', expand=True, padx=8, pady=8)
        ttk.Label(frm, text='Manage preset reasons:').pack(anchor='w')

        listbox = tk.Listbox(frm, height=10)
        listbox.pack(fill='both', expand=True, pady=(4, 4))
        for r in self.reason_presets:
            listbox.insert(tk.END, r)

        btnfrm = ttk.Frame(frm)
        btnfrm.pack(fill='x', pady=(0, 4))
        entry = ttk.Entry(btnfrm, width=30)
        entry.pack(side='left')

        def add():
            val = entry.get().strip()
            if val and val not in self.reason_presets:
                self.reason_presets.append(val)
                listbox.insert(tk.END, val)
                entry.delete(0, tk.END)
                self.reason_entry['values'] = self.reason_presets
                self._save_settings()

        def remove():
            sel = listbox.curselection()
            if sel:
                idx = sel[0]
                val = listbox.get(idx)
                self.reason_presets.remove(val)
                listbox.delete(idx)
                self.reason_entry['values'] = self.reason_presets
                self._save_settings()

        ttk.Button(btnfrm, text='Add', command=add).pack(side='left', padx=(4, 0))
        rmfrm = ttk.Frame(frm)
        rmfrm.pack(fill='x', pady=(0, 4))
        ttk.Button(rmfrm, text='Remove Selected', command=remove).pack(side='left')
        ttk.Button(rmfrm, text='Close', command=win.destroy).pack(side='right')

    def _on_close(self):
        self._save_settings()
        self.player_info.clear_cache()
        _save_name_cache()
        self.root.destroy()

    def _log_action(self, action, details=''):
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
        
        btnfrm = ttk.Frame(frm)
        btnfrm.pack(fill='x', pady=(4, 4))
        btn = ttk.Button(btnfrm, text='Copy Selected', command=self._copy_selected_log)
        btn.pack(side='left')
        self._bind_status_tip(btn, 'Copy selected log entry to clipboard')
        btn = ttk.Button(btnfrm, text='Copy All Logs', command=self._copy_all_logs)
        btn.pack(side='left', padx=(4, 0))
        self._bind_status_tip(btn, 'Copy all log entries to clipboard')
        btn = ttk.Button(btnfrm, text='Close', command=self._close_log)
        btn.pack(side='right')
        self._bind_status_tip(btn, 'Close log window')
        
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

    def _copy_selected_log(self):
        if not hasattr(self, '_log_tree') or self._log_tree is None:
            return
        sel = self._log_tree.selection()
        if not sel:
            messagebox.showwarning('No selection', 'Please select a log entry to copy')
            return
        item = self._log_tree.item(sel[0])
        values = item['values']
        text = f'[{values[0]}] {values[1]}: {values[2]}'
        if not check_deps():
            return
        try:
            pyperclip.copy(text)
            self.set_status('Log entry copied to clipboard')
        except Exception as e:
            messagebox.showerror('Clipboard error', str(e))

    def _copy_all_logs(self):
        if not self.action_log:
            messagebox.showinfo('No logs', 'No log entries to copy')
            return
        lines = []
        for entry in self.action_log:
            lines.append(f"[{entry['time']}] {entry['action']}: {entry['details']}")
        text = '\n'.join(lines)
        if not check_deps():
            return
        try:
            pyperclip.copy(text)
            self.set_status(f'{len(lines)} log entries copied to clipboard')
        except Exception as e:
            messagebox.showerror('Clipboard error', str(e))

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
            'Falcon - DC7BA1E2ACB1A167 - 1096334384 - 0 - 0 - 0 ms\n'
            'Titan - AE17F81ACE3EF8F6 - -293570384 - 1080 - 8 - 4 ms\n'
            'SimplySkidz - AD6D2AC59E4CB914 - -1261571360 - 125 - 1 - 1 ms\n'
            'Want My Oats - CD9B5A73422D169B - -182484784 - 2287 - 19 - 23 ms\n'
            'Eagle - 93F92DBF9A4B012A - 1475890736 - 0 - 0 - 0 ms\n'
            'Cryptic - 600DB838AC62BDE9 - 1571692528 - 0 - 0 - 2 ms\n'
            'ArtisanalMiner - 285FE56F575A3DB0 - -820817664 - 235 - 4 - 3 ms\n'
            'Bingo Bango B0ngo - ECE901670E64811D - -820817664 - 235 - 8 - 3 ms\n'
        )
        players = parse_players(data)
        self.populate(players)

    def _set_source(self, mode):
        if mode == self._source_mode:
            return
        self._source_mode = mode
        SRC_ACTIVE = '#c8a050'
        SRC_INACTIVE = '#ede0c8'
        self._src_game.config(bg=SRC_ACTIVE if mode == 'game' else SRC_INACTIVE)
        self._src_stats.config(bg=SRC_ACTIVE if mode == 'stats' else SRC_INACTIVE)
        self.key_entry.config(state='normal' if mode == 'game' else 'disabled')
        state = 'normal' if mode == 'game' else 'disabled'
        self._kick_btn.config(state=state)
        self._ban_btn.config(state=state)
        self.set_status(f'Source: {"Chivalry 2" if mode == "game" else "Chiv2Stats"}')

    def _run_command_thread(self, command_text, key, debug):
        if debug:
            line = f'{key} {command_text}'
            self.root.after(0, lambda t=line: self._debug_insert(t))
            self.root.after(0, lambda t=line: self.set_status(f'[DEBUG] Intercepted: {t}'))
            return
        self.set_status(f"Sending: {command_text}")
        ok = send_command_to_game(self._window_title, command_text, key)
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
        self.player_info.clear_details()
        self.detfrm.config(text='Player Details')
        self.set_status('Cleared.')

    def on_run(self):
        if self._source_mode == 'stats':
            q = (self.search_entry.get() or '').strip()
            self._search_request_id += 1
            req_id = self._search_request_id
            self.set_status('Searching Chiv2Stats...' if q else 'Fetching from Chiv2Stats...')
            t = threading.Thread(target=self._run_chiv2stats_thread, args=(q, req_id), daemon=True)
            t.start()
            return
        if not check_deps():
            return
        key = self.key_entry.get().strip() or '`'
        debug = self.debug_window is not None
        if debug:
            line = f'{key} listplayers'
            self._debug_insert(line)
            self.set_status(f"[DEBUG] Intercepted: {line}")
            return
        self.set_status("Running 'listplayers'...")
        self._log_action('ListPlayers')
        t = threading.Thread(target=self._run_thread, args=(key,), daemon=True)
        t.start()

    def _run_chiv2stats_thread(self, query, req_id):
        if req_id != self._search_request_id:
            return
        players, error = search_chiv2stats(query) if query else search_chiv2stats('')
        self.root.after(0, lambda r=req_id: self._handle_stats_response(players, error, r))

    def _handle_stats_response(self, players, error, req_id):
        if req_id != self._search_request_id:
            return
        if error:
            self.populate([])
            self.set_status(f'Chiv2Stats error: {error}')
            return
        self.populate(players or [])
        if not players:
            self.set_status('No results from Chiv2Stats')

    def _run_thread(self, key):
        def status(msg):
            self.root.after(0, lambda m=msg: self.set_status(m))

        clip = send_listplayers_to_game(self._window_title, key, status_callback=status)
        if not clip:
            self.root.after(0, lambda: self.set_status('No clipboard output received.'))
            self.root.after(0, self._return_focus)
            return
        players = parse_players(clip)
        self.root.after(0, lambda: self.populate(players))
        self.root.after(100, self._return_focus)

    def _run_cmd(self, cmd_key):
        cmd = self._COMMANDS[cmd_key]
        vals = {}
        for f in cmd.get('fields', []):
            w = getattr(self, f)
            vals[f] = w.get().strip() if isinstance(w, (ttk.Entry, ttk.Combobox)) else str(w)
        for f, msg in cmd.get('required', {}).items():
            if not vals.get(f):
                messagebox.showerror('Missing field', msg)
                return
        if 'validate' in cmd:
            try:
                cmd['validate'](vals)
            except ValueError:
                messagebox.showerror('Invalid input', cmd.get('validate_error', 'Invalid value'))
                return
        if 'confirm' in cmd:
            if not messagebox.askyesno(*cmd['confirm']):
                return
        cmd_text = cmd['format'](**vals)
        if 'log' in cmd:
            action, detail_fn = cmd['log']
            p = self._player_from_sel()
            player_name = p.get('name', '') if p else ''
            player_id = vals.get('id_entry', '')
            self._log_action(action, detail_fn(player_name=player_name, player_id=player_id, **vals) if detail_fn else '')
        key = self.key_entry.get().strip() or '`'
        debug = self.debug_window is not None
        threading.Thread(target=self._run_command_thread, args=(cmd_text, key, debug), daemon=True).start()

    _COMMANDS = {
        'kick_by_id': {
            'fields': ['id_entry', 'reason_entry'],
            'required': {'id_entry': 'Please enter a PlayFabId to kick'},
            'format': lambda id_entry, reason_entry: (
                f'kickbyid {id_entry} "{reason_entry.replace(chr(34), chr(39))}"' if reason_entry
                else f'kickbyid {id_entry}'
            ),
            'log': ('Kick', lambda player_name, player_id, id_entry, reason_entry: f'{player_name} ({player_id or id_entry}) - {reason_entry or "no reason"}'),
        },
        'ban_by_id': {
            'fields': ['id_entry', 'reason_entry', 'duration_entry'],
            'required': {'id_entry': 'Please enter a PlayFabId', 'duration_entry': 'Please enter duration hours'},
            'validate': lambda vals: int(vals['duration_entry']),
            'validate_error': 'Duration must be an integer number of hours',
            'format': lambda id_entry, reason_entry, duration_entry: (
                f'banbyid {id_entry} {int(duration_entry)} "{reason_entry.replace(chr(34), chr(39))}"' if reason_entry
                else f'banbyid {id_entry} {int(duration_entry)}'
            ),
            'log': ('Ban', lambda player_name, player_id, id_entry, reason_entry, duration_entry: f'{player_name} ({player_id or id_entry}) {int(duration_entry)}h - {reason_entry or "no reason"}'),
        },
        'unban_by_id': {
            'fields': ['id_entry'],
            'required': {'id_entry': 'Please enter a PlayFabId to unban'},
            'format': lambda id_entry: f'unbanbyid {id_entry}',
            'log': ('Unban', lambda player_name, player_id, id_entry: f'{player_name} ({player_id or id_entry})'),
        },
        'serversay': {
            'fields': ['msg_entry'],
            'required': {'msg_entry': 'Please enter a message to send'},
            'format': lambda msg_entry: (
                f'serversay "{msg_entry.replace(chr(34), chr(39))}"' if ' ' in msg_entry
                else f'serversay {msg_entry}'
            ),
            'log': ('ServerSay', lambda msg_entry: msg_entry),
        },
        'adminsay': {
            'fields': ['msg_entry'],
            'required': {'msg_entry': 'Please enter a message to send'},
            'format': lambda msg_entry: (
                f'adminsay "{msg_entry.replace(chr(34), chr(39))}"' if ' ' in msg_entry
                else f'adminsay {msg_entry}'
            ),
            'log': ('AdminSay', lambda msg_entry: msg_entry),
        },
        'add_bots': {
            'fields': ['_extra_bots_entry'],
            'required': {'_extra_bots_entry': 'Enter the number of bots to add'},
            'validate': lambda vals: int(vals['_extra_bots_entry']),
            'validate_error': 'Number of bots must be an integer',
            'format': lambda _extra_bots_entry: f'addbots {_extra_bots_entry}',
            'log': ('AddBots', lambda _extra_bots_entry: _extra_bots_entry),
        },
        'remove_bots': {
            'fields': [],
            'format': lambda: 'removebots 1 1',
            'log': ('RemoveBots', None),
        },
        'start_game': {
            'fields': [],
            'format': lambda: 'TBSmanuallystartgame',
            'log': ('StartGame', None),
        },
        'stat_fps': {
            'fields': [],
            'format': lambda: 'stat fps',
            'log': ('StatFPS', None),
        },
        'disconnect': {
            'fields': [],
            'format': lambda: 'disconnect',
            'log': ('Disconnect', None),
        },
        'exit_game': {
            'fields': [],
            'format': lambda: 'exit',
            'log': ('Exit', None),
        },
        'toggle_hud': {
            'fields': [],
            'format': lambda: 'togglehud',
            'log': ('ToggleHUD', None),
        },
        '_panel_end_game': {
            'fields': [],
            'confirm': ('End Game', 'End the current match?'),
            'format': lambda: 'TBSendgame 1',
            'log': ('EndGame', None),
        },
        '_panel_add_stage': {
            'fields': ['_panel_stage_entry'],
            'validate': lambda vals: float(vals['_panel_stage_entry']),
            'validate_error': 'Enter minutes (e.g. 0.5 for 30s, -0.5 for -30s)',
            'format': lambda _panel_stage_entry: f'TBSaddstagetime {float(_panel_stage_entry)}',
            'log': ('AddStageTime', lambda _panel_stage_entry: f'{_panel_stage_entry}m'),
        },
    }

    def kick_by_id(self):     self._run_cmd('kick_by_id')
    def ban_by_id(self):      self._run_cmd('ban_by_id')
    def unban_by_id(self):    self._run_cmd('unban_by_id')
    def serversay(self):      self._run_cmd('serversay')
    def adminsay(self):       self._run_cmd('adminsay')
    def add_bots(self):       self._run_cmd('add_bots')
    def remove_bots(self):    self._run_cmd('remove_bots')
    def start_game(self):     self._run_cmd('start_game')
    def stat_fps(self):       self._run_cmd('stat_fps')
    def disconnect(self):     self._run_cmd('disconnect')
    def exit_game(self):      self._run_cmd('exit_game')
    def toggle_hud(self):     self._run_cmd('toggle_hud')
    def _panel_end_game(self):  self._run_cmd('_panel_end_game')
    def _panel_add_stage(self): self._run_cmd('_panel_add_stage')

    def toggle_right_panel(self):
        if self._right_panel.winfo_viewable():
            self._right_panel.pack_forget()
        else:
            self._right_panel.pack(side='right', fill='y', padx=(0, 8), pady=(0, 8))

    def populate(self, players, set_all=True):
        if set_all:
            self.all_players = players
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.player_info.clear_details()
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
        if self._source_mode == 'stats':
            self._search_debounce = self.root.after(400, self.on_search)
        else:
            self._search_debounce = self.root.after(200, self.on_search)

    def on_search(self, event=None):
        if self._source_mode == 'stats':
            self.on_run()
            return
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
        if self._source_mode == 'stats':
            self.on_run()
            return
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
        self.player_info.show_details(p)
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
    def _return_focus(self):
        try:
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

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

