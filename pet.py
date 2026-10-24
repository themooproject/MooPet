#!/usr/bin/env python3
import os
import sys
import random
import math
import time
import argparse
import subprocess
import tkinter as tk
from PIL import Image, ImageTk, ImageSequence

# ------------------------------------------------------------------
PET_DIR = os.path.dirname(os.path.abspath(__file__))

FLEE_DISTANCE   = 150
DRAG_THRESHOLD  = 4
ANIM_FRAME_MS   = 80
FLEE_ANIM_FRAME_MS = 40
WALK_SPEED      = 3
IDLE_TIMEOUT    = 5000
SLEEP_TIMEOUT   = 15000
EAT_INTERVAL    = 20000
EAT_DURATION    = 2000
TICK_MS         = 16

FLEE_SPEED      = 9.0
FLEE_ACCEL      = 0.9
FLEE_HOP_CHANCE = 0.03
FLEE_HOP_VY     = -6.0

GRAVITY         = 0.9
AIR_DRAG        = 0.985
BOUNCE          = 0.45
WALL_BOUNCE     = 0.6
FRICTION_GROUND = 0.80
MAX_FALL_SPEED  = 22
RELEASE_THROW_MULT = 1.6

TURN_FRAME_MS   = 120

# --- Modo irritante ---
IRR_SPEED = 11.0
CURSOR_CHASE_BITE_DIST   = 40
CURSOR_CARRY_DURATION_MS = (1200, 2200)
CHAOS_INTERVAL_MS        = (4000, 8000)
CHAOS_DURATION_MS        = (2000, 4000)

STEAL_MIN_W = 200
STEAL_MIN_H = 150
BLOCKED_CLASSES = {
    "plasmashell", "kwin", "kwin_x11", "kded", "ksmserver",
    "systemsettings", "kinfocenter", "kglobalaccel",
    "ksplash", "ksmserver-logout",
}

ANIM = {
    "idle":       "idle.gif",
    "walk_right": "walking_right.gif",
    "walk_left":  "walking_left.gif",
    "sleep":      "sleep.gif",
    "eat":        "eat.gif",
    "turn_lr1":   "turn_forward_lr1.gif",
    "turn_lr2":   "turn_forward_lr2.gif",
    "turn_rl1":   "turn_backward_rl1.gif",
    "turn_rl2":   "turn_backward_rl2.gif",
}


# ==================================================================
# X11 helpers
# ==================================================================
_XLIB_OK = False
try:
    from Xlib import X as _X, display as _xdisplay
    _XLIB_OK = True
except Exception:
    _XLIB_OK = False

HAS_XDOTOOL = False
try:
    subprocess.run(["xdotool", "--version"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=True, timeout=1)
    HAS_XDOTOOL = True
except Exception:
    pass

_disp = None
_root = None
_atoms = {}

def _x_init():
    global _disp, _root, _atoms
    if not _XLIB_OK:
        return False
    if _disp is not None:
        return True
    try:
        _disp = _xdisplay.Display()
        _root = _disp.screen().root
        A = _disp.intern_atom
        _atoms = {
            "NET_CLIENT_LIST": A("_NET_CLIENT_LIST"),
            "NET_WM_STATE": A("_NET_WM_STATE"),
            "NET_WM_STATE_MAXIMIZED_HORZ": A("_NET_WM_STATE_MAXIMIZED_HORZ"),
            "NET_WM_STATE_MAXIMIZED_VERT": A("_NET_WM_STATE_MAXIMIZED_VERT"),
            "NET_WM_STATE_FULLSCREEN": A("_NET_WM_STATE_FULLSCREEN"),
            "NET_WM_NAME": A("_NET_WM_NAME"),
            "NET_WM_PID": A("_NET_WM_PID"),
            "NET_ACTIVE_WINDOW": A("_NET_ACTIVE_WINDOW"),
            "NET_FRAME_EXTENTS": A("_NET_FRAME_EXTENTS"),
            "WM_PROTOCOLS": A("WM_PROTOCOLS"),
            "WM_DELETE_WINDOW": A("WM_DELETE_WINDOW"),
        }
        return True
    except Exception:
        _disp = None
        return False


def x_list_windows():
    if not _x_init(): return []
    try:
        prop = _root.get_full_property(_atoms["NET_CLIENT_LIST"], _X.AnyPropertyType)
        return list(prop.value) if prop else []
    except Exception:
        return []


def x_active_window():
    if not _x_init(): return None
    try:
        prop = _root.get_full_property(_atoms["NET_ACTIVE_WINDOW"], _X.AnyPropertyType)
        return int(prop.value[0]) if prop else None
    except Exception:
        return None


def x_window_info(wid):
    if not _x_init(): return None
    try:
        w = _disp.create_resource_object("window", wid)
        geo = w.get_geometry()
        trans = w.translate_coords(_root, 0, 0)
        x = -trans.x
        y = -trans.y
        states = w.get_full_property(_atoms["NET_WM_STATE"], _X.AnyPropertyType)
        st = set(states.value) if states else set()
        maximized = (_atoms["NET_WM_STATE_MAXIMIZED_HORZ"] in st or
                     _atoms["NET_WM_STATE_MAXIMIZED_VERT"] in st)
        fullscreen = _atoms["NET_WM_STATE_FULLSCREEN"] in st
        wc = w.get_wm_class() or ("", "")
        cls = (wc[1] or wc[0] or "").lower()
        name = ""
        try:
            nm = w.get_full_property(_atoms["NET_WM_NAME"], _X.AnyPropertyType)
            if nm and nm.value:
                name = nm.value.decode("utf-8", "replace")
        except Exception:
            pass
        pid = None
        try:
            pp = w.get_full_property(_atoms["NET_WM_PID"], _X.AnyPropertyType)
            if pp and pp.value:
                pid = int(pp.value[0])
        except Exception:
            pass
        return {
            "wid": wid, "x": x, "y": y,
            "w": geo.width, "h": geo.height,
            "maximized": maximized, "fullscreen": fullscreen,
            "class": cls, "pid": pid, "name": name,
        }
    except Exception:
        return None


def x_move_window(wid, x, y):
    if not _x_init(): return False
    try:
        w = _disp.create_resource_object("window", wid)
        w.configure(x=int(x), y=int(y))
        _disp.sync()
        return True
    except Exception:
        return False


def x_frame_extents(wid):
    if not _x_init():
        return (0, 0, 0, 0)
    try:
        w = _disp.create_resource_object("window", wid)
        prop = w.get_full_property(_atoms["NET_FRAME_EXTENTS"], _X.AnyPropertyType)
        if prop and len(prop.value) >= 4:
            return tuple(int(v) for v in prop.value[:4])
    except Exception:
        pass
    return (0, 0, 0, 0)


def close_window(wid):
    """Pedido suave: WM_DELETE_WINDOW + xdotool windowclose."""
    if not _x_init():
        return False
    try:
        w = _disp.create_resource_object("window", wid)
        prot = w.get_full_property(_atoms["WM_PROTOCOLS"], _X.AnyPropertyType)
        if prot and _atoms["WM_DELETE_WINDOW"] in prot.value:
            from Xlib import protocol
            ev = protocol.event.ClientMessage(
                window=w,
                client_type=_atoms["WM_DELETE_WINDOW"],
                data=(32, [0, 0, 0, 0, 0]),
            )
            w.send_event(ev, event_mask=_X.NoEventMask)
            _disp.sync()
    except Exception:
        pass
    if HAS_XDOTOOL:
        try:
            subprocess.Popen(["xdotool", "windowclose", str(wid)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    return True


def force_close_window(wid):
    """Destroi a janela no X server. Sem dialogo, sem dó."""
    if HAS_XDOTOOL:
        try:
            subprocess.Popen(["xdotool", "windowkill", str(wid)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            pass
    return False


def cursor_pos():
    if HAS_XDOTOOL:
        try:
            out = subprocess.run(["xdotool", "getmouselocation", "--shell"],
                                 capture_output=True, text=True, timeout=0.2)
            vals = {}
            for line in out.stdout.strip().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    vals[k] = v
            return int(vals["X"]), int(vals["Y"])
        except Exception:
            pass
    if _XLIB_OK:
        try:
            if _disp is None: _x_init()
            if _disp is not None:
                p = _disp.screen().root.query_pointer()
                return p.root_x, p.root_y
        except Exception:
            pass
    return None


def move_cursor(x, y):
    if HAS_XDOTOOL:
        try:
            subprocess.Popen(["xdotool", "mousemove", str(int(x)), str(int(y))],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            pass
    if _XLIB_OK:
        try:
            if _disp is None: _x_init()
            if _disp is not None:
                _disp.screen().root.warp_pointer(int(x), int(y))
                _disp.sync()
                return True
        except Exception:
            pass
    return False


# ==================================================================
class AnimatedGIF:
    def __init__(self, path):
        self.frames, self.durations = [], []
        img = Image.open(path)
        for frame in ImageSequence.Iterator(img):
            frame = frame.convert("RGBA")
            self.frames.append(ImageTk.PhotoImage(frame))
            self.durations.append(frame.info.get("duration", ANIM_FRAME_MS))
        if not self.frames:
            self.frames.append(ImageTk.PhotoImage(img.convert("RGBA")))
            self.durations.append(ANIM_FRAME_MS)
        self.width  = self.frames[0].width()
        self.height = self.frames[0].height()
        self.index  = 0

    def frame(self):
        return self.frames[self.index]


class Pet:
    def __init__(self, root, irritant=False):
        self.root = root
        self.irritant = irritant
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.wm_attributes("-transparentcolor", "#FF00FF")
            self.bg = "#FF00FF"
        except tk.TclError:
            self.bg = "#000000"
        root.configure(bg=self.bg)

        self.anims = {}
        for name, fn in ANIM.items():
            p = os.path.join(PET_DIR, fn)
            if os.path.exists(p):
                self.anims[name] = AnimatedGIF(p)
        if "idle" not in self.anims:
            raise SystemExit("Faltando idle.gif na pasta do pet!")

        self.w = self.anims["idle"].width
        self.h = self.anims["idle"].height

        self.label = tk.Label(root, bd=0, bg=self.bg, highlightthickness=0)
        self.label.pack()
        self.label.bind("<ButtonPress-1>",   self.on_press)
        self.label.bind("<B1-Motion>",       self.on_drag)
        self.label.bind("<ButtonRelease-1>", self.on_release)
        root.bind_all("<Escape>", self.panic)

        self.screen_w = root.winfo_screenwidth()
        self.screen_h = root.winfo_screenheight()
        self.taskbar_h = 48
        self.ground_y = self.screen_h - self.h - self.taskbar_h

        self.x  = self.screen_w - 200
        self.y  = self.ground_y
        self.vx = 0.0
        self.vy = 0.0

        self.state     = "idle"
        self.direction = -1
        self.anim      = "idle"
        self.frame_accum = 0
        self.frame_ms  = ANIM_FRAME_MS
        self.last_move = 0
        self.eat_left  = 0
        self.turn_queue = []
        self.turn_left  = 0
        self._sleep_token = 0
        self._flee_after_turn = False

        self._press_origin = None
        self._drag_offset  = (0, 0)
        self._dragging     = False
        self._prev_pointer = (0, 0)
        self._pointer_vel  = (0.0, 0.0)

        # Modo irritante
        self._cursor_loop_active = False
        self._cursor_stage = "chase"
        self._cursor_data = {}
        self._chaos_active = False
        self._chaos_kind = None
        self._chaos_data = {}
        self._chaos_until = 0
        self._calm_until = 0

        self._apply_geometry()
        self.root.after(TICK_MS, self.tick)
        self.root.after(30,     self.anim_loop)
        self.root.after(EAT_INTERVAL, self.random_eat)

        if self.irritant:
            if not _XLIB_OK:
                print("[AVISO] python-xlib nao instalado.", file=sys.stderr)
            if not HAS_XDOTOOL:
                print("[AVISO] xdotool nao instalado.", file=sys.stderr)
            print("[IRRITANTE] modo ativo", file=sys.stderr)
            self._irr_boot()

    # --------------- Animação ---------------
    def set_anim(self, name, fast=False):
        if name not in self.anims:
            name = "idle" if "idle" in self.anims else list(self.anims)[0]
        if self.anim != name:
            self.anim = name
            self.frame_accum = 0
            self.anims[self.anim].index = 0
        self.frame_ms = FLEE_ANIM_FRAME_MS if fast else ANIM_FRAME_MS

    def anim_loop(self):
        a = self.anims[self.anim]
        self.frame_accum += 30
        if self.frame_accum >= self.frame_ms:
            self.frame_accum = 0
            a.index = (a.index + 1) % len(a.frames)
        self.label.configure(image=a.frame())
        self.root.after(30, self.anim_loop)

    # --------------- Loop principal ---------------
    def tick(self):
        if not self._dragging and not self.irritant:
            self.update_behavior()
            self.update_physics()
        self._apply_geometry()
        self.root.after(TICK_MS, self.tick)

    def _apply_geometry(self):
        self.root.geometry(f"{self.w}x{self.h}+{int(self.x)}+{int(self.y)}")

    # --------------- Física (só modo normal) ---------------
    def on_ground(self):
        return self.y >= self.ground_y - 0.5 and abs(self.vy) < 1.5

    def update_physics(self):
        if self.state == "turn":
            self.vx = 0.0
            self.turn_left -= TICK_MS
            if self.turn_left <= 0:
                if self.turn_queue:
                    self.set_anim(self.turn_queue.pop(0))
                    self.turn_left = TURN_FRAME_MS
                else:
                    if self._flee_after_turn:
                        self._flee_after_turn = False
                        self.state = "flee"
                        self.vy = min(self.vy, -2.0)
                        self.vx = self.direction * (FLEE_SPEED * 0.4)
                        self.set_anim("walk_right" if self.direction > 0
                                      else "walk_left", fast=True)
                    else:
                        self.state = "walk"
                        self.set_anim("walk_right" if self.direction > 0
                                      else "walk_left")

        self.vy += GRAVITY
        if self.vy > MAX_FALL_SPEED:
            self.vy = MAX_FALL_SPEED
        self.x += self.vx
        self.y += self.vy
        self.vx *= AIR_DRAG

        if self.y >= self.ground_y:
            self.y = self.ground_y
            if self.vy > 0:
                if self.vy > 3:
                    self.vy = -self.vy * BOUNCE
                else:
                    self.vy = 0
            if abs(self.vy) < 0.5:
                self.vx *= FRICTION_GROUND
                if self.state != "flee" and abs(self.vx) < 0.15:
                    self.vx = 0.0

        if self.x < 0:
            self.x = 0
            if self.vx < 0: self.vx = 0
        elif self.x + self.w > self.screen_w:
            self.x = self.screen_w - self.w
            if self.vx > 0: self.vx = 0
        if self.y < 0:
            self.y = 0
            self.vy = abs(self.vy) * WALL_BOUNCE

    # --------------- Comportamento normal ---------------
    def update_behavior(self):
        if self.state == "flee":
            self._continue_flee()
            return
        if self.state == "turn":
            return
        if self.state == "eat":
            self.eat_left -= TICK_MS
            if self.eat_left <= 0:
                self.state = "idle"
                self.set_anim("idle")
            return
        if self.state == "sleep":
            mx, my = self.root.winfo_pointerxy()
            cx, cy = self.x + self.w / 2, self.y + self.h / 2
            if math.hypot(mx - cx, my - cy) < FLEE_DISTANCE:
                self.wake_up()
            return
        if not self.on_ground() or abs(self.vx) > 0.5:
            return
        mx, my = self.root.winfo_pointerxy()
        cx, cy = self.x + self.w / 2, self.y + self.h / 2
        if math.hypot(mx - cx, my - cy) < FLEE_DISTANCE:
            self._start_flee(mx - cx)
            self.last_move = self.now()
            return
        if self.state != "sleep" and self.now() - self.last_move > IDLE_TIMEOUT:
            self.go_to_sleep()
            return
        if self.state == "walk":
            self.vx = self.direction * WALK_SPEED * 0.6
            self.last_move = self.now()
        else:
            if random.random() < 0.008:
                self.state = "walk"
                self.last_move = self.now()
                self.set_anim("walk_right" if self.direction > 0
                              else "walk_left")

    def go_to_sleep(self):
        self.state = "sleep"
        self.vx = 0.0
        self.set_anim("sleep")
        self._sleep_token += 1
        tok = self._sleep_token
        self.root.after(SLEEP_TIMEOUT, lambda: self._wake_by_timeout(tok))

    def _wake_by_timeout(self, tok):
        if tok == self._sleep_token and self.state == "sleep":
            self.wake_up()

    def wake_up(self):
        if self.state == "sleep":
            self._sleep_token += 1
            self.state = "idle"
            self.set_anim("idle")
            self.last_move = self.now()

    def _start_flee(self, dx):
        if self.state == "sleep":
            self.wake_up()
        desired = +1 if dx < 0 else -1
        if desired != self.direction:
            self.begin_turn(desired)
            self._flee_after_turn = True
            return
        self.state = "flee"
        self.vy = min(self.vy, -2.0)
        self.vx = desired * (FLEE_SPEED * 0.4)
        self.set_anim("walk_right" if desired > 0 else "walk_left", fast=True)

    def _continue_flee(self):
        desired = self.direction
        if self.vx * desired < FLEE_SPEED:
            self.vx += desired * FLEE_ACCEL
            if self.vx * desired > FLEE_SPEED:
                self.vx = desired * FLEE_SPEED
        if self.on_ground() and random.random() < FLEE_HOP_CHANCE:
            self.vy = FLEE_HOP_VY
        self.set_anim("walk_right" if desired > 0 else "walk_left", fast=True)
        mx, my = self.root.winfo_pointerxy()
        cx, cy = self.x + self.w / 2, self.y + self.h / 2
        if math.hypot(mx - cx, my - cy) > FLEE_DISTANCE * 1.8:
            self.state = "idle"
            self.set_anim("idle")

    def begin_turn(self, new_dir):
        if new_dir == self.direction and self.state != "walk":
            return
        self.direction = new_dir
        self.state = "turn"
        self.turn_queue = (["turn_lr1", "turn_lr2"] if new_dir > 0
                           else ["turn_rl1", "turn_rl2"])
        self.set_anim(self.turn_queue.pop(0))
        self.turn_left = TURN_FRAME_MS

    def random_eat(self):
        if (not self.irritant and self.state == "idle" and self.on_ground()):
            self.state = "eat"
            self.eat_left = EAT_DURATION
            self.set_anim("eat")
        self.root.after(EAT_INTERVAL + random.randint(-5000, 5000),
                        self.random_eat)

    def now(self):
        return self.root.tk.call("clock", "milliseconds")

    # ================================================================
    # MODO IRRITANTE — cursor sequestrado + caos periódico
    # ================================================================
    def _irr_boot(self):
        self._cursor_loop_active = True
        self._cursor_stage = "chase"
        self._cursor_data = {}
        self._chaos_active = False
        self._chaos_kind = None
        self._chaos_data = {}
        self._chaos_until = 0
        self._calm_until = 0
        self.root.after(200, self._cursor_loop)
        self.root.after(random.randint(*CHAOS_INTERVAL_MS), self._chaos_loop)

    # ----- LOOP A: perseguir → morder → levar cursor → soltar -----
    def _cursor_loop(self):
        if not self._cursor_loop_active or not self.irritant:
            return
        if self._dragging or self.now() < self._calm_until:
            self.root.after(100, self._cursor_loop)
            return
        if self._chaos_active:
            self.root.after(TICK_MS, self._cursor_loop)
            return

        stage = self._cursor_stage

        if stage == "chase":
            c = cursor_pos()
            if c is None:
                self.root.after(TICK_MS, self._cursor_loop); return
            cx = self.x + self.w/2
            cy = self.y + self.h/2
            dx = c[0] - cx
            dy = c[1] - cy
            dist = math.hypot(dx, dy)
            if dist < CURSOR_CHASE_BITE_DIST:
                self._cursor_stage = "bite"
                self._cursor_data["bite_until"] = self.now() + 200
                self.set_anim("eat", fast=True)
                print("[IRRITANTE] mordeu cursor", file=sys.stderr)
                self.root.after(TICK_MS, self._cursor_loop)
                return
            if dist > 0:
                ux, uy = dx / dist, dy / dist
                self.x += ux * IRR_SPEED
                self.y += uy * IRR_SPEED
                self.x = max(0, min(self.x, self.screen_w - self.w))
                self.y = max(0, min(self.y, self.screen_h - self.h))
                if abs(ux) > 0.2:
                    self.direction = +1 if ux > 0 else -1
            self.set_anim("walk_right" if self.direction > 0 else "walk_left",
                          fast=True)
            self.root.after(TICK_MS, self._cursor_loop)

        elif stage == "bite":
            self.set_anim("eat", fast=True)
            bx = self.x + self.w/2 + self.direction * 18
            by = self.y + self.h/2
            move_cursor(bx, by)
            if self.now() >= self._cursor_data["bite_until"]:
                self._cursor_stage = "carry"
                dur = random.randint(*CURSOR_CARRY_DURATION_MS)
                self._cursor_data["carry_until"] = self.now() + dur
                self._cursor_data["carry_dir"] = random.choice([-1, +1])
            self.root.after(TICK_MS, self._cursor_loop)

        elif stage == "carry":
            if self.now() >= self._cursor_data["carry_until"]:
                self._cursor_stage = "release"
                self.set_anim("idle")
                print("[IRRITANTE] soltou cursor", file=sys.stderr)
                self.root.after(80, self._cursor_loop)
                return
            d = self._cursor_data["carry_dir"]
            if self.x <= 5 and d < 0:
                self._cursor_data["carry_dir"] = +1
            elif self.x + self.w >= self.screen_w - 5 and d > 0:
                self._cursor_data["carry_dir"] = -1
            d = self._cursor_data["carry_dir"]
            self.x += d * IRR_SPEED * 0.9
            self.x = max(0, min(self.x, self.screen_w - self.w))
            self.set_anim("walk_right" if d > 0 else "walk_left", fast=True)
            bx = self.x + self.w/2 + d * 18
            by = self.y + self.h/2
            move_cursor(bx, by)
            self.root.after(TICK_MS, self._cursor_loop)

        elif stage == "release":
            self.set_anim("idle")
            self._cursor_stage = "chase"
            self.root.after(0, self._cursor_loop)

    # ----- LOOP B: caos a cada 4-8s -----
    def _chaos_loop(self):
        if not self.irritant or not self._cursor_loop_active:
            return
        if self._dragging or self.now() < self._calm_until:
            self.root.after(2000, self._chaos_loop)
            return

        options = []
        if self._pick_victim() is not None:
            options.append("steal_window")
        wid = x_active_window()
        if wid:
            options.append("block_close")
            options.append("block_window")
        if not options:
            self.root.after(2000, self._chaos_loop)
            return

        kind = random.choice(options)
        self._chaos_active = True
        self._chaos_kind = kind
        self._chaos_data = {"started": self.now()}
        self._chaos_until = self.now() + random.randint(*CHAOS_DURATION_MS)
        print(f"[IRRITANTE] caos: {kind}", file=sys.stderr)

        if kind == "steal_window":
            v = self._pick_victim()
            if v is None:
                self._chaos_active = False
                self.root.after(random.randint(*CHAOS_INTERVAL_MS), self._chaos_loop)
                return
            self._chaos_data["victim"] = v
            self._chaos_data["target"] = (
                v["x"] + (v["w"] if v["x"] + v["w"]/2 > self.x else -self.w),
                v["y"] + v["h"] - self.h)
            self._chaos_data["phase"] = "travel"
        elif kind == "block_close":
            info = x_window_info(wid)
            if info is None:
                self._chaos_active = False
                self.root.after(random.randint(*CHAOS_INTERVAL_MS), self._chaos_loop)
                return
            left, right, top, bottom = x_frame_extents(wid)
            if top == 0:
                top = 30
            target_x = info["x"] + info["w"] + right - self.w
            target_y = info["y"] - top
            self._chaos_data["info"] = info
            self._chaos_data["target"] = (target_x, target_y)
            self._chaos_data["phase"] = "travel"
        elif kind == "block_window":
            info = x_window_info(wid)
            if info is None:
                self._chaos_active = False
                self.root.after(random.randint(*CHAOS_INTERVAL_MS), self._chaos_loop)
                return
            self._chaos_data["info"] = info
            self._chaos_data["target"] = (info["x"] + info["w"]/2 - self.w/2,
                                          info["y"] + info["h"]/2 - self.h/2)
            self._chaos_data["phase"] = "travel"

        self.root.after(TICK_MS, self._chaos_tick)

    def _chaos_tick(self):
        if not self._chaos_active or not self.irritant:
            return
        if self.now() >= self._chaos_until:
            self._chaos_end(); return

        kind = self._chaos_kind
        phase = self._chaos_data.get("phase", "travel")

        if phase == "travel":
            tx, ty = self._chaos_data["target"]
            cx = self.x + self.w/2
            cy = self.y + self.h/2
            dx, dy = tx - cx, ty - cy
            dist = math.hypot(dx, dy)
            if dist < IRR_SPEED * 1.5:
                self._chaos_data["phase"] = "act"
                self._chaos_data["act_start"] = self.now()
                self.root.after(TICK_MS, self._chaos_tick)
                return
            ux, uy = dx / dist, dy / dist
            self.x += ux * IRR_SPEED
            self.y += uy * IRR_SPEED
            self.x = max(0, min(self.x, self.screen_w - self.w))
            self.y = max(0, min(self.y, self.screen_h - self.h))
            if abs(ux) > 0.2:
                self.direction = +1 if ux > 0 else -1
            self.set_anim("walk_right" if self.direction > 0 else "walk_left",
                          fast=True)
            self.root.after(TICK_MS, self._chaos_tick)
            return

        t = self.now() - self._chaos_data["act_start"]

        if kind == "steal_window":
            self._chaos_steal_window(t)
        elif kind == "block_close":
            self.set_anim("idle")
            if "clicked" not in self._chaos_data and t > 200:
                self._chaos_data["clicked"] = True
                info = self._chaos_data["info"]
                wid = info["wid"]
                if "*" in info.get("name", ""):
                    print("[IRRITANTE] trabalho nao salvo, nao fecho",
                          file=sys.stderr)
                else:
                    close_window(wid)
                    print(f"[IRRITANTE] pedi pra fechar {info['class']}",
                          file=sys.stderr)
                    self.root.after(400, lambda w=wid, c=info['class']:
                                    self._force_if_alive(w, c))
        elif kind == "block_window":
            self.set_anim("idle")
        self.root.after(TICK_MS, self._chaos_tick)

    def _force_if_alive(self, wid, cls):
        """Se a janela ainda existe depois do pedido suave, destroi."""
        if x_window_info(wid) is not None:
            if force_close_window(wid):
                print(f"[IRRITANTE] matei {cls} (windowkill)",
                      file=sys.stderr)
            else:
                print(f"[IRRITANTE] nao consegui matar {cls}",
                      file=sys.stderr)
        else:
            print(f"[IRRITANTE] {cls} fechou sozinho", file=sys.stderr)

    def _chaos_steal_window(self, t):
        v = self._chaos_data.get("victim")
        if v is None or x_window_info(v["wid"]) is None:
            self._chaos_end(); return
        if "carry_off" not in self._chaos_data:
            self._chaos_data["carry_off"] = (v["x"] - self.x, v["y"] - self.y)
            self._chaos_data["carry_dir"] = -1 if self.x > self.screen_w/2 else +1
            self._chaos_data["fails"] = 0
        d = self._chaos_data["carry_dir"]
        if self.x <= 5 and d < 0:
            self._chaos_data["carry_dir"] = +1
        elif self.x + self.w >= self.screen_w - 5 and d > 0:
            self._chaos_data["carry_dir"] = -1
        d = self._chaos_data["carry_dir"]
        self.x += d * IRR_SPEED * 0.8
        self.x = max(0, min(self.x, self.screen_w - self.w))
        self.set_anim("walk_right" if d > 0 else "walk_left", fast=True)
        wx = self.x + self._chaos_data["carry_off"][0]
        wy = self.y + self._chaos_data["carry_off"][1]
        x_move_window(v["wid"], wx, wy)
        info = x_window_info(v["wid"])
        if info and abs(info["x"] - wx) > 4:
            self._chaos_data["fails"] += 1
            if self._chaos_data["fails"] > 8:
                self._chaos_end()

    def _chaos_end(self):
        self._chaos_active = False
        self._chaos_kind = None
        self._chaos_data = {}
        self.set_anim("idle")
        self.root.after(random.randint(*CHAOS_INTERVAL_MS), self._chaos_loop)

    def _pick_victim(self):
        if not _x_init(): return None
        my_pid = os.getpid()
        for wid in x_list_windows():
            info = x_window_info(wid)
            if not info: continue
            if info["maximized"] or info["fullscreen"]: continue
            if info["w"] < STEAL_MIN_W or info["h"] < STEAL_MIN_H: continue
            if info["class"] in BLOCKED_CLASSES: continue
            if info["pid"] == my_pid: continue
            if info["y"] > self.screen_h - 10: continue
            return info
        return None

    # ================================================================
    def panic(self, _evt=None):
        self._calm_until = self.now() + 30000
        self._chaos_active = False
        self._chaos_kind = None
        self._chaos_data = {}
        self._cursor_stage = "chase"
        self._cursor_data = {}
        self.state = "idle"
        self.set_anim("idle")
        print("[IRRITANTE] PANICO — 30s", file=sys.stderr)

    # ================================================================
    def on_press(self, e):
        self._press_origin = (e.x_root, e.y_root)
        self._drag_offset  = (e.x_root - self.x, e.y_root - self.y)
        self._dragging = False
        self._prev_pointer = (e.x_root, e.y_root)
        self._pointer_vel = (0.0, 0.0)

    def on_drag(self, e):
        if self._press_origin is None: return
        dxp = abs(e.x_root - self._press_origin[0])
        dyp = abs(e.y_root - self._press_origin[1])
        if not self._dragging and (dxp + dyp) > DRAG_THRESHOLD:
            self._dragging = True
            self.state = "drag"
            self.vx = self.vy = 0.0
            self._sleep_token += 1
            self.eat_left = 0
            self.set_anim("idle")
            if self._chaos_active:
                self._chaos_active = False
                self._chaos_kind = None
                self._chaos_data = {}
            self._cursor_stage = "chase"
            self._cursor_data = {}
        if self._dragging:
            px, py = self._prev_pointer
            self._pointer_vel = (
                self._pointer_vel[0] * 0.6 + (e.x_root - px) * 0.4,
                self._pointer_vel[1] * 0.6 + (e.y_root - py) * 0.4,
            )
            self._prev_pointer = (e.x_root, e.y_root)
            self.x = e.x_root - self._drag_offset[0]
            self.y = e.y_root - self._drag_offset[1]
            self._apply_geometry()

    def on_release(self, e):
        if self._dragging:
            self.vx = self._pointer_vel[0] * RELEASE_THROW_MULT
            self.vy = self._pointer_vel[1] * RELEASE_THROW_MULT
            self.vx = max(-40, min(40, self.vx))
            self.vy = max(-40, min(40, self.vy))
            self.x = max(0, min(self.x, self.screen_w - self.w))
            self.state = "idle"
            self.set_anim("idle")
            self.last_move = self.now()
        self._dragging = False
        self._press_origin = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--modo-irritante", "--irritant",
                        dest="irritant", action="store_true")
    parser.add_argument("-q", "--quantidade", "--vacas",
                        dest="quantidade", type=int, default=1,
                        metavar="N",
                        help="quantidade de vacas na tela (padrao: 1)")
    args = parser.parse_args()

    n = max(1, args.quantidade)

    if n > 1:
        # [NOVO] Lança N processos filhos, cada um com os mesmos args
        # menos os de quantidade. Cada filho roda este mesmo script,
        # então o comportamento é idêntico ao de 1 vaca.
        base_cmd = [sys.executable, os.path.abspath(__file__)]
        skip_next = False
        for a in sys.argv[1:]:
            if skip_next:
                skip_next = False
                continue
            if a in ("-q", "--quantidade", "--vacas"):
                skip_next = True
                continue
            if a.startswith("--quantidade=") or a.startswith("--vacas="):
                continue
            base_cmd.append(a)

        procs = []
        for i in range(n):
            if i > 0:
                time.sleep(0.15)   # evita competição no boot do X11
            procs.append(subprocess.Popen(base_cmd))

        try:
            for p in procs:
                p.wait()
        except KeyboardInterrupt:
            print("\n[INFO] encerrando...", file=sys.stderr)
            for p in procs:
                try:
                    p.terminate()
                except Exception:
                    pass
            for p in procs:
                try:
                    p.wait(timeout=2)
                except Exception:
                    try:
                        p.kill()
                    except Exception:
                        pass
        return

    # n == 1: comportamento original, sem mudanças
    root = tk.Tk()
    Pet(root, irritant=args.irritant)
    root.mainloop()


if __name__ == "__main__":
    main()
