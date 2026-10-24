#!/usr/bin/env python3
import os
import random
import math
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
EAT_DURATION    = 2000       # ms comendo
TICK_MS         = 16

# --- Fuga ---
FLEE_SPEED      = 9.0
FLEE_ACCEL      = 0.9
FLEE_HOP_CHANCE = 0.03
FLEE_HOP_VY     = -6.0

# --- Física ---
GRAVITY         = 0.9
AIR_DRAG        = 0.985
BOUNCE          = 0.45
WALL_BOUNCE     = 0.6
FRICTION_GROUND = 0.80
MAX_FALL_SPEED  = 22
RELEASE_THROW_MULT = 1.6

# --- Tempo das animações de virar ---
TURN_FRAME_MS   = 120        # cada frame de virar dura 120ms

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
    def __init__(self, root):
        self.root = root
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
        self.turn_left  = 0        # ms restantes de animação de virar
        self._sleep_token = 0      # evita múltiplos wake_up agendados

        self._press_origin = None
        self._drag_offset  = (0, 0)
        self._dragging     = False
        self._prev_pointer = (0, 0)
        self._pointer_vel  = (0.0, 0.0)

        self._apply_geometry()
        self.root.after(TICK_MS, self.tick)
        self.root.after(30,     self.anim_loop)
        self.root.after(EAT_INTERVAL, self.random_eat)

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

    # --------------- Loop ---------------
    def tick(self):
        if self._dragging:
            pass
        else:
            self.update_behavior()
            self.update_physics()
        self._apply_geometry()
        self.root.after(TICK_MS, self.tick)

    def _apply_geometry(self):
        self.root.geometry(f"{self.w}x{self.h}+{int(self.x)}+{int(self.y)}")

    # --------------- Física ---------------
    def on_ground(self):
        return self.y >= self.ground_y - 0.5 and abs(self.vy) < 1.5

    def update_physics(self):
        # Física de virar: se estiver no meio de uma animação de virar,
        # mantém congelado horizontalmente até terminar.
        if self.state == "turn":
            self.vx = 0.0
            self.turn_left -= TICK_MS
            if self.turn_left <= 0:
                if self.turn_queue:
                    self.set_anim(self.turn_queue.pop(0))
                    self.turn_left = TURN_FRAME_MS
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

        # Colisão com o chão
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

        # ----- Colisão com paredes: vira, não rebate -----
        hit_wall_dir = None
        if self.x < 0:
            self.x = 0
            hit_wall_dir = +1          # estava indo para esquerda → deve ir p/ direita
        elif self.x + self.w > self.screen_w:
            self.x = self.screen_w - self.w
            hit_wall_dir = -1          # estava indo para direita → deve ir p/ esquerda

        if hit_wall_dir is not None:
            self.vx = 0.0
            # Só dispara a virada se não estiver já virando
            if self.state not in ("turn", "drag", "eat", "sleep"):
                self.begin_turn(hit_wall_dir)

        if self.y < 0:
            self.y = 0
            self.vy = abs(self.vy) * WALL_BOUNCE

        if not self.on_ground() and self.state not in ("eat", "sleep", "flee", "turn"):
            self.state = "air"

    # --------------- VIRAR ---------------
    def begin_turn(self, new_dir):
        """Inicia a sequência de animação de virar. Ao fim, anda na nova direção."""
        if new_dir == self.direction and self.state != "walk":
            return
        self.direction = new_dir
        self.state = "turn"
        self.turn_queue = (["turn_lr1", "turn_lr2"] if new_dir > 0
                           else ["turn_rl1", "turn_rl2"])
        self.set_anim(self.turn_queue.pop(0))
        self.turn_left = TURN_FRAME_MS

    # --------------- Comportamento ---------------
    def update_behavior(self):
        # A fuga pode continuar mesmo no ar
        if self.state == "flee":
            self.continue_flee()
            return

        # Virando: só termina no update_physics
        if self.state == "turn":
            return

        # Comer: NÃO é interrompido por cursor próximo (a menos que muito perto)
        if self.state == "eat":
            self.eat_left -= TICK_MS
            mx, my = self.root.winfo_pointerxy()
            cx, cy = self.x + self.w / 2, self.y + self.h / 2
            very_close = math.hypot(mx - cx, my - cy) < FLEE_DISTANCE * 0.5
            if self.eat_left <= 0 or very_close:
                self.state = "idle"
                self.set_anim("idle")
            return

        # Dormindo: só acorda se cursor chegar perto ou timeout
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
        dx, dy = mx - cx, my - cy
        dist = math.hypot(dx, dy)

        if dist < FLEE_DISTANCE:
            self.start_flee(dx)
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
        # Token para garantir que o wake_up agendado só vale uma vez
        self._sleep_token += 1
        token = self._sleep_token
        self.root.after(SLEEP_TIMEOUT, lambda: self._wake_by_timeout(token))

    def _wake_by_timeout(self, token):
        if token == self._sleep_token and self.state == "sleep":
            self.wake_up()

    def wake_up(self):
        if self.state == "sleep":
            self._sleep_token += 1     # invalida timeouts antigos
            self.state = "idle"
            self.set_anim("idle")
            self.last_move = self.now()

    # --------------- FUGA ---------------
    def start_flee(self, dx):
        if self.state == "sleep":
            self.wake_up()
        desired = +1 if dx < 0 else -1
        # Se precisa virar, faz animação de virar primeiro
        if desired != self.direction:
            self.begin_turn(desired)
            # Após virar, o estado vira "walk"; força fuga na sequência
            self._flee_after_turn = True
            return
        self.state = "flee"
        self.vy = min(self.vy, -2.0)
        self.vx = desired * (FLEE_SPEED * 0.4)
        self.set_anim("walk_right" if desired > 0 else "walk_left", fast=True)

    def continue_flee(self):
        desired = self.direction
        target_vx = desired * FLEE_SPEED
        if self.vx * desired < FLEE_SPEED:
            self.vx += desired * FLEE_ACCEL
            if self.vx * desired > FLEE_SPEED:
                self.vx = target_vx

        if self.on_ground() and random.random() < FLEE_HOP_CHANCE:
            self.vy = FLEE_HOP_VY

        self.set_anim("walk_right" if desired > 0 else "walk_left", fast=True)

        mx, my = self.root.winfo_pointerxy()
        cx, cy = self.x + self.w / 2, self.y + self.h / 2
        dist = math.hypot(mx - cx, my - cy)
        if dist > FLEE_DISTANCE * 1.8:
            self.state = "idle"
            self.set_anim("idle")

    # --------------- Comer espontâneo ---------------
    def random_eat(self):
        if self.state == "idle" and self.on_ground():
            self.state = "eat"
            self.eat_left = EAT_DURATION
            self.set_anim("eat")
        self.root.after(EAT_INTERVAL + random.randint(-5000, 5000),
                        self.random_eat)

    def now(self):
        return self.root.tk.call("clock", "milliseconds")

    # --------------- Drag ---------------
    def on_press(self, e):
        self._press_origin = (e.x_root, e.y_root)
        self._drag_offset  = (e.x_root - self.x, e.y_root - self.y)
        self._dragging = False
        self._prev_pointer = (e.x_root, e.y_root)
        self._pointer_vel = (0.0, 0.0)

    def on_drag(self, e):
        if self._press_origin is None:
            return
        dxp = abs(e.x_root - self._press_origin[0])
        dyp = abs(e.y_root - self._press_origin[1])
        if not self._dragging and (dxp + dyp) > DRAG_THRESHOLD:
            self._dragging = True
            # Cancela estados especiais ao arrastar
            self.state = "drag"
            self.vx = self.vy = 0.0
            self._sleep_token += 1
            self.eat_left = 0
            self.set_anim("idle")

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
    root = tk.Tk()
    Pet(root)
    root.mainloop()


if __name__ == "__main__":
    main()
