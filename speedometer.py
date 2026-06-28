#!/usr/bin/env python3
"""
STEALTH R/T GPS CLUSTER
Amber VFD-style GPS speedometer for Raspberry Pi 5 + 7" 1024x600 display
GPS receiver: GlobalSat BU-353N5 via gpsd

Runs in SIMULATION mode automatically if gpsd-py3 isn't installed or no
GPS is connected, so you can test the UI before the hardware arrives.

Controls:  ESC = quit  |  UP/DOWN = sim speed  |  R = reset leaderboard
"""

import os
if "SDL_VIDEODRIVER" not in os.environ:
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        pass
    else:
        os.environ["SDL_VIDEODRIVER"] = "kmsdrm"
os.environ.setdefault("SDL_FBDEV", "/dev/fb0")
os.environ["SDL_NOMOUSE"] = "1"

import math
import re
import time
import random
import json
import os.path
import tempfile
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
    _CHICAGO = ZoneInfo("America/Chicago")
except Exception:
    _CHICAGO = timezone.utc  # fallback: UTC if tzdata unavailable

import socket
import sys
import threading
import pygame

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
WIDTH, HEIGHT = 1024, 600
FPS = 30
MAX_SPEED = 120
FULLSCREEN = True

# --- 0-60 timer / leaderboard ---
ZERO_TO_SIXTY_TARGET = 60.0
LAUNCH_THRESHOLD = 2.0
STOP_THRESHOLD = 1.0
LEADERBOARD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "zero_to_sixty_times.json")
LEADERBOARD_SIZE = 5
NEW_RECORD_FLASH_SEC = 4.0

# --- 90s sports-car orange palette — warm halogen/incandescent gauge glow ---
BG          = (5, 2, 0)
PANEL       = (13, 5, 0)
BORDER      = (155, 78, 12)     # brighter panel outlines
AMBER       = (255, 128, 22)    # warmer primary orange
AMBER_HI    = (255, 178, 50)    # bright golden highlight
RED         = (255, 70, 25)     # alerts
LABEL       = (218, 118, 20)    # readable field labels
UNIT        = (178, 96, 14)     # readable unit text
DIM         = (138, 64, 10)     # visible dim/coords
SEG_OFF     = (32, 13, 2)
TRACK       = (50, 20, 3)
PILL_ON_BG  = (44, 17, 2)
PILL_ON_FG  = (255, 128, 18)
PILL_OFF_BG = (9, 4, 0)
PILL_OFF_FG = (88, 40, 6)
PILL_RED_BG = (55, 0, 0)
PILL_RED_FG = (255, 70, 25)

DIRS = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']

# ----------------------------------------------------------------------
# GPS DATA SOURCE
# ----------------------------------------------------------------------
class GpsdClient:
    """Background-thread gpsd JSON socket reader — no external libraries."""
    def __init__(self, host="127.0.0.1", port=2947):
        self._lock = threading.Lock()
        self._tpv = {}
        self._sky = {}
        self._connected = False
        t = threading.Thread(target=self._run, args=(host, port), daemon=True)
        t.start()

    def _run(self, host, port):
        while True:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((host, port))
                sock.settimeout(None)
                sock.sendall(b'?WATCH={"enable":true,"json":true}\n')
                with self._lock:
                    self._connected = True
                print(f"[gpsd] connected to {host}:{port}")
                buf = ""
                while True:
                    chunk = sock.recv(4096).decode("utf-8", errors="replace")
                    if not chunk:
                        break
                    buf += chunk
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        self._parse(line.strip())
            except OSError as e:
                print(f"[gpsd] socket error: {e}")
            except Exception as e:
                print(f"[gpsd] error: {e}")
            finally:
                with self._lock:
                    self._connected = False
            time.sleep(3)

    def _parse(self, line):
        if not line:
            return
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return
        cls = msg.get("class", "")
        with self._lock:
            if cls == "TPV":
                self._tpv = msg
            elif cls == "SKY":
                self._sky = msg

    @property
    def connected(self):
        with self._lock:
            return self._connected

    def snapshot(self):
        with self._lock:
            return dict(self._tpv), dict(self._sky)


class GPSSource:
    """Wraps gpsd via a background socket thread, falling back to a simulator."""
    def __init__(self):
        self.sim_t = 0.0
        self.sim_heading = 315.0
        self.live = False
        self._log_count = 0
        self._client = GpsdClient()
        print("[gps] attempting live gpsd connection …")

    def read(self, sim_speed, dt):
        if self._client.connected:
            tpv, sky = self._client.snapshot()
            self.live = True
            spd_ms  = float(tpv.get("speed") or 0.0)
            spd_mph = spd_ms * 2.23694
            if self._log_count < 10 or self._log_count % 150 == 0:
                print(f"[gps] raw speed={spd_ms:.3f} m/s -> {spd_mph:.2f} mph  "
                      f"mode={tpv.get('mode', '?')}  keys={sorted(tpv)}")
            self._log_count += 1
            alt_m = float(tpv.get("altMSL") or tpv.get("alt") or 0.0)
            # uSat is the authoritative used-satellite count from gpsd's SKY sentence
            sats_list = sky.get("satellites", []) if sky else []
            usat = (sky.get("uSat") or
                    sum(1 for s in sats_list if s.get("used", False)) or
                    0) if sky else 0
            return {
                "speed":   max(spd_mph, 0.0),
                "heading": float(tpv.get("track") or 0.0),
                "alt":     alt_m * 3.28084,
                "lat":     float(tpv.get("lat") or 0.0),
                "lon":     float(tpv.get("lon") or 0.0),
                "sats":    int(usat),
                "hdop":    float(sky.get("hdop") or 1.5) if sky else 1.5,
                "mode":    int(tpv.get("mode") or 1),
            }
        # --- simulation fallback ---
        if self.live:
            print("[gps] gpsd disconnected — falling back to simulation")
        self.live = False
        self.sim_t += dt
        self.sim_heading = (self.sim_heading
                            + (random.random() - 0.48) * 0.5 * (sim_speed / 20 + 0.3)) % 360
        alt = 258 + math.sin(self.sim_t * 0.1) * 15 + random.random() * 2
        moving = sim_speed > 0
        return {
            "speed":   sim_speed,
            "heading": self.sim_heading,
            "alt":     alt,
            "lat":     44.9778, "lon": -93.2650,
            "sats":    (9 + round(random.random() * 2)) if moving else (6 + round(random.random())),
            "hdop":    round((0.9 + random.random() * 0.4) if moving else (1.8 + random.random() * 0.5), 1),
            "mode":    3,
        }

def deg_to_compass(d):
    return DIRS[int((d % 360) / 22.5 + 0.5) % 16]

# ----------------------------------------------------------------------
# 0-60 LEADERBOARD PERSISTENCE
# ----------------------------------------------------------------------
def load_leaderboard():
    try:
        with open(LEADERBOARD_FILE, "r") as f:
            data = json.load(f)
        times = data.get("times", []) if isinstance(data, dict) else data
        clean = [e for e in times if isinstance(e, dict) and "seconds" in e]
        clean.sort(key=lambda e: e["seconds"])
        return clean[:LEADERBOARD_SIZE]
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return []

def save_leaderboard(times):
    try:
        d = os.path.dirname(LEADERBOARD_FILE) or "."
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".lb_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({"times": times}, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, LEADERBOARD_FILE)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    except OSError as e:
        print(f"[leaderboard] save failed: {e}")

# ----------------------------------------------------------------------
# 0-60 TIMER STATE MACHINE
# ----------------------------------------------------------------------
class ZeroToSixty:
    def __init__(self):
        self.state = "READY"
        self.run_start = None
        self.elapsed = 0.0
        self.last_time = None
        self.leaderboard = load_leaderboard()
        self.session_best = self.leaderboard[0]["seconds"] if self.leaderboard else None
        self.new_record_at = None

    def update(self, speed_mph, now):
        if self.state == "READY":
            if speed_mph >= LAUNCH_THRESHOLD:
                self.state = "RUNNING"
                self.run_start = now
                self.elapsed = 0.0
        elif self.state == "RUNNING":
            self.elapsed = now - self.run_start
            if speed_mph >= ZERO_TO_SIXTY_TARGET:
                self._finish(now)
            elif speed_mph <= STOP_THRESHOLD:
                self.state = "READY"
                self.run_start = None
                self.elapsed = 0.0
        elif self.state == "DONE":
            if speed_mph <= STOP_THRESHOLD:
                self.state = "READY"

    def _finish(self, now):
        t = self.elapsed
        self.last_time = t
        self.state = "DONE"
        entry = {
            "seconds": round(t, 2),
            "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "local": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        prev_best = self.leaderboard[0]["seconds"] if self.leaderboard else None
        self.leaderboard.append(entry)
        self.leaderboard.sort(key=lambda e: e["seconds"])
        self.leaderboard = self.leaderboard[:LEADERBOARD_SIZE]
        self.session_best = self.leaderboard[0]["seconds"]
        if self.leaderboard[0] is entry and (prev_best is None or t < prev_best):
            self.new_record_at = now
        save_leaderboard(self.leaderboard)

    def reset(self):
        self.leaderboard = []
        self.session_best = None
        self.last_time = None
        self.new_record_at = None
        save_leaderboard(self.leaderboard)

    def display_value(self):
        if self.state == "READY":
            return ("READY", False)
        if self.state == "RUNNING":
            return (f"{self.elapsed:0.1f}", False)
        rec = self.new_record_at is not None
        return (f"{self.last_time:0.2f}", rec)

# ----------------------------------------------------------------------
# FONT HELPERS
# ----------------------------------------------------------------------
def load_fonts():
    candidates = ["Orbitron", "DejaVu Sans Mono", "Liberation Mono", "monospace"]
    name = None
    for c in candidates:
        match = pygame.font.match_font(c.lower().replace(" ", ""))
        if match:
            name = match
            break
    def mk(size, bold=False):
        if name:
            f = pygame.font.Font(name, size)
            if bold:
                f.set_bold(True)
            return f
        return pygame.font.SysFont("monospace", size, bold=True)
    return {
        "huge":  mk(128),         # speed number
        "gauge": mk(64),          # in-gauge digital speed
        "big":   mk(34),          # stat box values
        "mid":   mk(26),          # compass, clock, coords
        "small": mk(19, bold=True),  # MPH label, overlays
        "tiny":  mk(16, bold=True),  # secondary labels
        "micro": mk(14, bold=True),  # panel labels and units
    }

def text(surf, font, s, x, y, color, anchor="center"):
    img = font.render(str(s), True, color)
    r = img.get_rect()
    setattr(r, anchor, (x, y))
    surf.blit(img, r)
    return r

def panel(surf, rect, radius=4):
    pygame.draw.rect(surf, PANEL, rect, border_radius=radius)
    pygame.draw.rect(surf, BORDER, rect, width=2, border_radius=radius)

def draw_corner_marks(surf, rect, color, size=10):
    """L-shaped bracket at each corner — 90s terminal aesthetic."""
    for cx, cy, dx, dy in [
        (rect.left,      rect.top,    1,  1),
        (rect.right - 1, rect.top,   -1,  1),
        (rect.left,      rect.bottom, 1, -1),
        (rect.right - 1, rect.bottom,-1, -1),
    ]:
        pygame.draw.line(surf, color, (cx, cy), (cx + dx * size, cy), 2)
        pygame.draw.line(surf, color, (cx, cy), (cx, cy + dy * size), 2)

def make_scanline_overlay(width, height):
    """Pre-computed CRT grid — horizontal scanlines + subtle vertical columns."""
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    for y in range(0, height, 3):
        pygame.draw.line(surf, (0, 0, 0, 44), (0, y), (width - 1, y))
    for x in range(0, width, 5):
        pygame.draw.line(surf, (0, 0, 0, 16), (x, 0), (x, height - 1))
    return surf

# ----------------------------------------------------------------------
# BOOT SPLASH
# ----------------------------------------------------------------------
BOOT_STEPS = [
    ("SYSTEM POWER ON",      "OK"),
    ("RASPBERRY PI 5  8GB",  "OK"),
    ("DISPLAY 1024x600 IPS", "OK"),
    ("INITIALIZING gpsd",    "OK"),
    ("BU-353N5 RECEIVER",    "DETECTED"),
    ("ACQUIRING SATELLITES", "SEARCHING"),
    ("GPS FIX ESTABLISHED",  "3D LOCK"),
    ("CLUSTER READY",        ""),
]

def run_boot(screen, fonts, clock):
    """Animated VFD boot sequence — 90s terminal style."""
    cx = WIDTH // 2
    brand_y  = 132
    bar_y    = 228
    bar_w, bar_h = 440, 10
    bar_x    = cx - bar_w // 2
    log_y0   = 256
    line_h   = 28

    shown = 0
    last_add = time.time()
    add_delay = 0.22
    intro = time.time()
    done_time = None
    cursor_on = True
    last_blink = time.time()

    running = True
    while running:
        now = time.time()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return False
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                return False

        if now - last_blink >= 0.45:
            cursor_on = not cursor_on
            last_blink = now

        screen.fill(BG)
        elapsed = now - intro

        # Horizontal rules framing the title
        pygame.draw.line(screen, BORDER, (40, brand_y - 24), (WIDTH - 40, brand_y - 24), 1)

        # Brand — flicker in first 0.8s
        flick = AMBER if elapsed >= 0.8 or int(elapsed * 14) % 3 != 0 else (150, 90, 10)
        text(screen, fonts["big"],  "S T E A L T H   R / T",        cx, brand_y,      flick)
        text(screen, fonts["tiny"], "GPS  NAVIGATION  CLUSTER  v1.0", cx, brand_y + 30, LABEL)

        pygame.draw.line(screen, BORDER, (40, brand_y + 50), (WIDTH - 40, brand_y + 50), 1)

        # Progress bar
        pygame.draw.rect(screen, SEG_OFF, (bar_x, bar_y, bar_w, bar_h), border_radius=3)
        pygame.draw.rect(screen, BORDER,  (bar_x, bar_y, bar_w, bar_h), width=1, border_radius=3)
        frac = shown / len(BOOT_STEPS)
        if frac > 0:
            pygame.draw.rect(screen, AMBER,
                             (bar_x, bar_y, int(bar_w * frac), bar_h), border_radius=3)
        text(screen, fonts["micro"], f"{int(frac * 100):3d}%",
             bar_x + bar_w + 10, bar_y + 5, LABEL, anchor="midleft")

        # Reveal log lines
        if elapsed > 0.7 and shown < len(BOOT_STEPS) and (now - last_add) > add_delay:
            shown += 1
            last_add = now

        for i in range(shown):
            lbl, status = BOOT_STEPS[i]
            ly = log_y0 + i * line_h
            is_last = (i == shown - 1 and shown < len(BOOT_STEPS))
            cursor = " _" if (is_last and cursor_on) else "  "
            text(screen, fonts["tiny"], f"  {lbl}{cursor}", bar_x, ly, AMBER, anchor="midleft")
            if status:
                col = AMBER_HI if status in ("OK", "3D LOCK", "DETECTED") else LABEL
                text(screen, fonts["tiny"], f"[ {status} ]",
                     bar_x + bar_w, ly, col, anchor="midright")

        if shown >= len(BOOT_STEPS) and done_time is None:
            done_time = now
        if done_time and (now - done_time) > 0.7:
            running = False

        pygame.display.flip()
        clock.tick(FPS)
    return True

# ----------------------------------------------------------------------
# DASH WIDGETS
# ----------------------------------------------------------------------
def draw_stat_box(screen, fonts, rect, label, value, unit, vfont="mid",
                  vcolor=AMBER, bar_frac=None, bar_color=None):
    panel(screen, rect)
    text(screen, fonts["micro"], label.upper(), rect.centerx, rect.y + 13, LABEL)
    text(screen, fonts[vfont], value, rect.centerx, rect.y + rect.h // 2 + 2, vcolor)
    text(screen, fonts["micro"], unit.upper(), rect.centerx, rect.bottom - 11, UNIT)
    if bar_frac is not None:
        bx = rect.x + 12
        bw = rect.w - 24
        by = rect.bottom - 7
        pygame.draw.rect(screen, TRACK, (bx, by, bw, 3), border_radius=2)
        fw = int(bw * min(bar_frac, 1.0))
        if fw > 0:
            pygame.draw.rect(screen, bar_color or AMBER, (bx, by, fw, 3), border_radius=2)

def draw_speed_segments(screen, x, y, w, h, frac):
    n = 26
    gap = 3
    seg_w = (w - gap * (n - 1)) / n
    lit = round(frac * n)
    for i in range(n):
        sx = x + i * (seg_w + gap)
        if i < lit:
            color = AMBER if i < 15 else (AMBER_HI if i < 21 else RED)
        else:
            color = SEG_OFF
        pygame.draw.rect(screen, color, (sx, y, seg_w, h), border_radius=1)

def draw_analog_gauge(screen, cx, cy, radius, speed, max_speed, spd_color, fonts):
    # Sunrise semicircle: 0 mph = left (180°), max = right (0°), arc through top.
    # cy is the horizon line; arc rises above it, digital speed sits below.
    track_w  = 20
    r        = radius
    rect     = pygame.Rect(cx - r,      cy - r,      r * 2,           r * 2)
    glow_r   = r + 9
    glow_rect = pygame.Rect(cx - glow_r, cy - glow_r, glow_r * 2,    glow_r * 2)
    inner_r  = r - track_w + 4
    inner_rect = pygame.Rect(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)

    def spd_angle(s):
        return math.pi * (1.0 - max(0.0, min(float(s), max_speed)) / max_speed)

    def spd_xy(s, rad):
        a = spd_angle(s)
        return (cx + rad * math.cos(a), cy - rad * math.sin(a))

    # --- Background: outer halo bloom + dim track ---
    pygame.draw.arc(screen, (16, 7, 1),  glow_rect, 0, math.pi, track_w + 18)
    pygame.draw.arc(screen, SEG_OFF,     rect,      0, math.pi, track_w)

    # --- Active arc zones: bloom → main arc → bright inner edge ---
    zones = [(0, 70, AMBER), (70, 100, AMBER_HI), (100, max_speed, RED)]
    for z_min, z_max, z_color in zones:
        if speed > z_min:
            sa = spd_angle(min(speed, z_max))
            ea = spd_angle(z_min)
            bloom = (z_color[0] // 5, z_color[1] // 5, z_color[2] // 5)
            edge  = tuple(min(255, c + 90) for c in z_color)
            pygame.draw.arc(screen, bloom,   glow_rect,  sa, ea, track_w + 18)
            pygame.draw.arc(screen, z_color, rect,       sa, ea, track_w)
            pygame.draw.arc(screen, edge,    inner_rect, sa, ea, 3)

    # --- Inner decorative ring (clean inner boundary) ---
    ring_r = r - track_w - 10
    ring_rect = pygame.Rect(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
    pygame.draw.arc(screen, BORDER, ring_rect, 0, math.pi, 1)

    # --- Horizon line ---
    pygame.draw.line(screen, BORDER, (cx - r, cy), (cx + r, cy), 1)

    # --- Fine ticks every 5 mph (subtle, between major/minor marks) ---
    for s in range(5, max_speed, 10):
        if s % 20 == 0:
            continue
        ip = spd_xy(s, r - track_w - 1)
        op = spd_xy(s, r - 2)
        pygame.draw.line(screen, (42, 18, 3),
                         (int(ip[0]), int(ip[1])), (int(op[0]), int(op[1])), 1)

    # --- Minor ticks every 10 mph ---
    for s in range(10, max_speed, 20):
        ip = spd_xy(s, r - track_w - 5)
        op = spd_xy(s, r - 2)
        pygame.draw.line(screen, LABEL,
                         (int(ip[0]), int(ip[1])), (int(op[0]), int(op[1])), 2)

    # --- Major ticks every 20 mph + labels ---
    for s in range(0, max_speed + 1, 20):
        ip = spd_xy(s, r - track_w - 8)
        op = spd_xy(s, r - 2)
        pygame.draw.line(screen, AMBER_HI,
                         (int(ip[0]), int(ip[1])), (int(op[0]), int(op[1])), 3)
        lx, ly = spd_xy(s, r + 15)
        lbl = fonts["micro"].render(str(s), True, AMBER)
        screen.blit(lbl, lbl.get_rect(center=(int(lx), int(ly))))

    # --- Rally needle: filled triangle, wide at hub, tapers to tip ---
    tip_x, tip_y = spd_xy(speed, r - track_w - 8)
    a   = spd_angle(speed)
    ux  =  math.cos(a)          # unit vector toward tip (screen space)
    uy  = -math.sin(a)
    px  =  math.sin(a)          # perpendicular (90° CCW in screen space)
    py  =  math.cos(a)
    bw, tail = 6, 22
    p1 = (cx + px * bw - ux * tail, cy + py * bw - uy * tail)
    p2 = (cx - px * bw - ux * tail, cy - py * bw - uy * tail)
    p3 = (tip_x, tip_y)
    pygame.draw.polygon(screen, DIM, [(v[0]+1, v[1]+1) for v in (p1, p2, p3)])
    pygame.draw.polygon(screen, spd_color, [p1, p2, p3])
    pygame.draw.line(screen, AMBER_HI,
                     (int(cx - ux * tail), int(cy - uy * tail)),
                     (int(tip_x), int(tip_y)), 1)

    # --- Layered hub ---
    pygame.draw.circle(screen, BORDER,    (int(cx), int(cy)), 16)
    pygame.draw.circle(screen, spd_color, (int(cx), int(cy)), 11)
    pygame.draw.circle(screen, BG,        (int(cx), int(cy)), 6)
    pygame.draw.circle(screen, DIM,       (int(cx), int(cy)), 4)

    # --- Digital speed below the horizon ---
    text(screen, fonts["gauge"], round(speed), cx + 1, cy + 51, DIM)
    text(screen, fonts["gauge"], round(speed), cx,     cy + 50, spd_color)
    text(screen, fonts["small"], "MPH", cx, cy + 90, LABEL)

def draw_pill(screen, fonts, x, y, label, state):
    """state: 'on' | 'off' | 'red'."""
    if state == "on":
        bg, fg = PILL_ON_BG, PILL_ON_FG
    elif state == "red":
        bg, fg = PILL_RED_BG, PILL_RED_FG
    else:
        bg, fg = PILL_OFF_BG, PILL_OFF_FG
    pad_x = 8
    img = fonts["micro"].render(label.upper(), True, fg)
    w = img.get_width() + pad_x * 2
    h = 22
    rect = pygame.Rect(x, y, w, h)
    pygame.draw.rect(screen, bg, rect, border_radius=2)
    pygame.draw.rect(screen, fg, rect, width=1, border_radius=2)
    screen.blit(img, img.get_rect(center=rect.center))
    return w

def draw_signal_bars(surf, x, y_bottom, n_lit):
    """4 ascending bars — classic cell phone signal icon. Returns total width drawn."""
    bar_w = 8
    gap   = 4
    heights = [12, 20, 30, 42]
    for i, h in enumerate(heights):
        bx    = x + i * (bar_w + gap)
        by    = y_bottom - h
        color = AMBER if i < n_lit else SEG_OFF
        pygame.draw.rect(surf, color, (bx, by, bar_w, h), border_radius=1)
    return len(heights) * (bar_w + gap) - gap

def draw_speed_limit_sign(screen, fonts, rect, limit_mph, current_speed):
    over    = (limit_mph is not None and current_speed > limit_mph + 5)
    val     = str(limit_mph) if limit_mph is not None else "--"
    num_col = RED if over else (AMBER if limit_mph is not None else DIM)
    panel(screen, rect)
    if over:
        pygame.draw.rect(screen, RED, rect, width=2, border_radius=4)
    text(screen, fonts["micro"], "SPEED LIMIT", rect.centerx, rect.y + 13, LABEL)
    text(screen, fonts["big"],   val,           rect.centerx, rect.y + rect.h // 2 + 2, num_col)
    text(screen, fonts["micro"], "MPH",         rect.centerx, rect.bottom - 11, UNIT)

_HWY_REF_RE = re.compile(r'^([A-Z]{1,3})\s+(\d+[A-Z]?)$', re.IGNORECASE)

def _clean_road_name(raw):
    """Format OSM name/ref for display: 'I 94;MN 95' -> 'I-94 / MN-95'."""
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    cleaned = []
    for p in parts:
        if _HWY_REF_RE.match(p):
            p = p.replace(" ", "-")
        cleaned.append(p)
    return " / ".join(cleaned) or None

def _text_fit(surf, font, s, cx, y, color, max_w):
    """Render text centered at (cx, y); truncate with '...' if wider than max_w."""
    img = font.render(s, True, color)
    if img.get_width() <= max_w:
        surf.blit(img, img.get_rect(center=(cx, y)))
        return
    dots = font.render("...", True, color)
    avail = max_w - dots.get_width()
    while len(s) > 0 and font.render(s, True, color).get_width() > avail:
        s = s[:-1]
    s = s.rstrip()
    prefix = font.render(s, True, color)
    total_w = prefix.get_width() + dots.get_width()
    bx = cx - total_w // 2
    by = y - prefix.get_height() // 2
    surf.blit(prefix, (bx, by))
    surf.blit(dots,   (bx + prefix.get_width(), by))

def draw_location_panel(screen, fonts, rect, city, street):
    """Two stacked panels: city name (top) and street name (bottom)."""
    gap      = 6
    city_h   = 120
    street_h = rect.h - city_h - gap
    city_r   = pygame.Rect(rect.x, rect.y,                     rect.w, city_h)
    street_r = pygame.Rect(rect.x, rect.y + city_h + gap,      rect.w, street_h)

    # City box
    panel(screen, city_r)
    text(screen, fonts["micro"], "CITY", city_r.centerx, city_r.y + 13, LABEL)
    city_val = city if city else "--"
    city_col = AMBER if city else DIM
    _text_fit(screen, fonts["small"], city_val,
              city_r.centerx, city_r.y + city_h // 2 + 4,
              city_col, city_r.w - 12)

    # Street box
    panel(screen, street_r)
    text(screen, fonts["micro"], "STREET", street_r.centerx, street_r.y + 13, LABEL)
    street_val = street if street else "--"
    street_col = AMBER if street else DIM
    _text_fit(screen, fonts["tiny"], street_val,
              street_r.centerx, street_r.y + street_h // 2 + 4,
              street_col, street_r.w - 12)

# ----------------------------------------------------------------------
# SPEED-LIMIT + CITY LOOKUP  (optional — cluster runs fine if unavailable)
# ----------------------------------------------------------------------
_sl_ready = False   # True once speed-limit index is loaded
_sl_fn    = None    # bound to speed_limit.get_speed_limit when ready
_cl_ready = False   # True once city index is loaded
_cl_fn    = None    # bound to city_lookup.get_city when ready

def _sl_preload():
    """Background thread: load speed-limit index then city index."""
    global _sl_fn, _sl_ready, _cl_fn, _cl_ready
    try:
        osm_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "osm")
        if osm_dir not in sys.path:
            sys.path.insert(0, osm_dir)
        import speed_limit as _sl_mod
        _sl_mod.preload()           # reads speedlimit_idx.dat + speedlimit_segs.pkl
        _sl_fn    = _sl_mod.get_speed_limit
        _sl_ready = True
        print("[speed_limit] index ready")
    except Exception as exc:
        print(f"[speed_limit] unavailable, street shows '--': {exc}")
    try:
        import city_lookup as _cl_mod
        _cl_mod.preload()           # reads city_places.pkl (~0.003 s)
        _cl_fn    = _cl_mod.get_city
        _cl_ready = True
        print("[city_lookup] index ready")
    except Exception as exc:
        print(f"[city_lookup] unavailable, city shows '--': {exc}")

# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------
def main():
    pygame.init()
    flags = pygame.FULLSCREEN if FULLSCREEN else 0
    screen = None

    explicit_driver = os.environ.get("SDL_VIDEODRIVER")
    if explicit_driver:
        try:
            screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
            print(f"[display] using SDL video driver: {explicit_driver}")
        except pygame.error as e:
            print(f"[display] ERROR: set_mode failed with driver '{explicit_driver}': {e}")
            pygame.quit()
            return
    else:
        tried = []
        for drv in ["kmsdrm", "x11", "wayland", "dummy"]:
            tried.append(drv)
            try:
                os.environ["SDL_VIDEODRIVER"] = drv
                already_init = (pygame.display.get_init() and
                                pygame.display.get_driver().upper() == drv.upper())
                if not already_init:
                    if pygame.display.get_init():
                        pygame.display.quit()
                    pygame.display.init()
                screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
                print(f"[display] using SDL video driver: {drv}")
                break
            except pygame.error:
                if pygame.display.get_init():
                    pygame.display.quit()
                continue

        if screen is None:
            print(f"[display] ERROR: no working video driver. Tried: {tried}")
            print("[display] On the Pi console try: SDL_VIDEODRIVER=kmsdrm python3 speedometer.py")
            pygame.quit()
            return

    pygame.display.set_caption("Stealth R/T GPS Cluster")
    try:
        pygame.mouse.set_visible(False)
    except pygame.error:
        pass
    clock = pygame.time.Clock()
    fonts = load_fonts()
    scanlines = make_scanline_overlay(WIDTH, HEIGHT)

    # Kick off speed-limit index load in background; finishes during boot splash
    threading.Thread(target=_sl_preload, daemon=True, name="sl-preload").start()

    if not run_boot(screen, fonts, clock):
        pygame.quit()
        return

    gps = GPSSource()

    zts = ZeroToSixty()
    reset_armed_until = None
    reset_done_at = None

    sim_speed = 0.0
    disp_speed = 0.0
    disp_sats = 0
    last_sats_t = 0.0
    trip_miles = 0.0
    start_t = time.time()
    last_t = time.time()

    # Speed-limit + location lookup state
    cached_limit_mph  = None   # int or None
    cached_road_name  = None   # cleaned string or None
    cached_city       = None   # string or None
    last_limit_t      = 0.0    # time of last speed-limit/street lookup
    last_city_t       = 0.0    # time of last city lookup

    # Layout
    col_x   = 14       # left/right margin
    ly      = 76       # top band height
    right_w = 170      # 0-60 timer box width
    right_x = WIDTH - col_x - right_w  # = 840

    running = True
    while running:
        now = time.time()
        dt = now - last_t
        last_t = now

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_UP:
                    sim_speed = min(sim_speed + 5, MAX_SPEED)
                elif e.key == pygame.K_DOWN:
                    sim_speed = max(sim_speed - 5, 0)
                elif e.key == pygame.K_r:
                    if reset_armed_until and now <= reset_armed_until:
                        zts.reset()
                        reset_armed_until = None
                        reset_done_at = now
                    else:
                        reset_armed_until = now + 3.0
                elif e.key == pygame.K_m and (e.mod & pygame.KMOD_CTRL):
                    pygame.quit()
                    try:
                        _here = os.path.dirname(os.path.abspath(__file__))
                        _script = os.path.join(_here, 'launch_minetest.sh')
                        os.execvp(_script, [_script])
                    except Exception:
                        pass
                    sys.exit(0)
                elif e.key == pygame.K_t and (e.mod & pygame.KMOD_CTRL):
                    pygame.quit()
                    try:
                        _here = os.path.dirname(os.path.abspath(__file__))
                        _script = os.path.join(_here, 'launch_terminal.sh')
                        os.execvp(_script, [_script])
                    except Exception:
                        pass
                    sys.exit(0)

        data = gps.read(sim_speed, dt)
        raw = data["speed"]
        _speed_diff = raw - disp_speed
        _smooth = 0.45 if _speed_diff < -3.0 else (0.30 if _speed_diff > 5.0 else 0.15)
        disp_speed += _speed_diff * _smooth

        if disp_speed > 0.5:
            trip_miles += (disp_speed / 3600.0) * dt

        zts.update(disp_speed, now)
        if zts.new_record_at and (now - zts.new_record_at) > NEW_RECORD_FLASH_SEC:
            zts.new_record_at = None
        if reset_armed_until and now > reset_armed_until:
            reset_armed_until = None
        if reset_done_at and (now - reset_done_at) > 2.0:
            reset_done_at = None

        elapsed_s = int(now - start_t)
        em, es = divmod(elapsed_s, 60)

        hdg = data["heading"]
        if now - last_sats_t >= 1.0:
            disp_sats = data["sats"]
            last_sats_t = now
        sats = disp_sats
        hdop = data["hdop"]
        lat, lon = data["lat"], data["lon"]
        mode = data["mode"]
        lost = sats < 4 or mode < 2

        # Speed-limit + street lookup: at most once per second
        if _sl_ready and (now - last_limit_t) >= 1.0:
            try:
                lim, rname = _sl_fn(lat, lon)
                cached_limit_mph = lim
                cached_road_name = _clean_road_name(rname)
            except Exception:
                pass    # keep previous cached values on error
            last_limit_t = now
        # City lookup: at most once every 5 seconds (changes slowly)
        if _cl_ready and (now - last_city_t) >= 5.0:
            try:
                cached_city = _cl_fn(lat, lon)
            except Exception:
                pass
            last_city_t = now
        over = disp_speed > 100
        local_dt = datetime.now(_CHICAGO)

        spd_color = RED if over else (AMBER_HI if disp_speed > 70 else AMBER)

        # Blinking colon in local clock (12-hour US Central)
        colon     = ":" if int(now * 2) % 2 == 0 else " "
        clock_str = local_dt.strftime(f"%I{colon}%M{colon}%S %p").lstrip("0")
        tz_label  = local_dt.strftime("%Z")
        date_str  = local_dt.strftime("%b %d").upper()

        # ---- DRAW ----
        screen.fill(BG)

        # Top band: brand block
        brand = pygame.Rect(col_x, 10, 152, 56)
        panel(screen, brand)
        text(screen, fonts["micro"], "STEALTH  R/T", brand.centerx, brand.y + 17, AMBER)
        text(screen, fonts["micro"], "GPS CLUSTER",  brand.centerx, brand.y + 36, LABEL)

        # GPS signal bars — old cell phone style
        n_bars = (0 if mode < 2 else
                  1 if (mode == 2 or hdop > 5.0) else
                  2 if hdop > 3.0 else
                  3 if hdop > 2.0 else 4)
        bars_x = brand.right + 16
        draw_signal_bars(screen, bars_x, 64, n_bars)
        lbl_x = bars_x + 48   # 44px bars + 4px gap
        if not gps.live:
            text(screen, fonts["micro"], "SIM MODE", lbl_x, 28, LABEL, anchor="midleft")
        elif lost:
            text(screen, fonts["micro"], "NO SIGNAL", lbl_x, 28, RED, anchor="midleft")
        else:
            text(screen, fonts["micro"], "3D FIX" if mode == 3 else "2D FIX",
                 lbl_x, 28, AMBER, anchor="midleft")
            text(screen, fonts["micro"], f"{sats} SATS", lbl_x, 48, LABEL, anchor="midleft")
        if over:
            text(screen, fonts["micro"], "! OVERSPD", lbl_x + 84, 28, RED, anchor="midleft")

        # Top band: UTC clock (right)
        clock_box = pygame.Rect(WIDTH - col_x - 204, 10, 204, 56)
        panel(screen, clock_box)
        text(screen, fonts["mid"],   clock_str,                clock_box.centerx, clock_box.y + 24,      AMBER)
        text(screen, fonts["micro"], f"{tz_label}  {date_str}", clock_box.centerx, clock_box.bottom - 11, LABEL)

        # ---- speed limit sign ----
        lim_rect = pygame.Rect(right_x, ly, right_w, 90)
        draw_speed_limit_sign(screen, fonts, lim_rect,
                              cached_limit_mph if _sl_ready else None,
                              disp_speed)

        # ---- 0-60 timer box ----
        z_val, z_record = zts.display_value()
        z_color = AMBER_HI if (z_record or zts.state == "RUNNING") else AMBER
        z_rect = pygame.Rect(right_x, lim_rect.bottom + 6, right_w, 150)
        draw_stat_box(screen, fonts, z_rect, "0-60 MPH", z_val,
                      "NEW RECORD" if z_record else "seconds", "big", z_color)
        if z_record and int(now * 3) % 2 == 0:
            pygame.draw.rect(screen, AMBER_HI, z_rect, width=2, border_radius=4)

        # ---- location panel (city + street) below 0-60 timer ----
        loc_rect = pygame.Rect(right_x, z_rect.bottom + 6, right_w,
                               HEIGHT - 10 - z_rect.bottom - 6)
        draw_location_panel(screen, fonts, loc_rect,
                            cached_city       if _cl_ready else None,
                            cached_road_name  if _sl_ready else None)

        # ---- center speedometer panel ----
        center = pygame.Rect(col_x, ly, right_x - col_x - 10, HEIGHT - ly - 10)
        panel(screen, center)
        draw_corner_marks(screen, center, AMBER_HI)

        # Convenience: offsets from center.y
        cy = center.y
        ccx = center.centerx
        div_x1 = center.x + 24
        div_x2 = center.right - 24

        # Sunrise analog gauge + digital speed below
        draw_analog_gauge(screen, ccx, cy + 248, 220, disp_speed, MAX_SPEED, spd_color, fonts)

        pygame.draw.line(screen, BORDER, (div_x1, cy + 358), (div_x2, cy + 358), 1)

        # Compass row
        comp_y = cy + 380
        text(screen, fonts["tiny"], f"{round(hdg):03d}°", ccx - 60, comp_y, LABEL)
        text(screen, fonts["mid"],  deg_to_compass(hdg),  ccx + 40, comp_y, AMBER)

        pygame.draw.line(screen, BORDER, (div_x1, cy + 402), (div_x2, cy + 402), 1)

        # Trip + Elapsed — anchored to panel edges to prevent overlap
        info_y = cy + 421
        text(screen, fonts["tiny"], f"TRIP  {trip_miles:.1f} mi",
             center.x + 24, info_y, LABEL, anchor="midleft")
        text(screen, fonts["tiny"], f"ELAPSED  {em:02d}:{es:02d}",
             center.right - 24, info_y, LABEL, anchor="midright")

        pygame.draw.line(screen, BORDER, (div_x1, cy + 440), (div_x2, cy + 440), 1)

        # Coordinates
        lat_str = f"LAT  {abs(lat):.4f}° {'N' if lat >= 0 else 'S'}"
        lon_str = f"LON  {abs(lon):.4f}° {'W' if lon < 0 else 'E'}"
        text(screen, fonts["tiny"], lat_str, ccx, cy + 456, DIM)
        text(screen, fonts["tiny"], lon_str, ccx, cy + 474, DIM)

        pygame.draw.line(screen, BORDER, (div_x1, cy + 490), (div_x2, cy + 490), 1)

        # Speed bar (no text labels — analog gauge already has mph scale)
        seg_x = center.x + 28
        seg_w = center.w - 56
        draw_speed_segments(screen, seg_x, cy + 502, seg_w, 12,
                            min(disp_speed / MAX_SPEED, 1.0))

        # ---- GPS lost overlay ----
        if lost:
            w_rect = pygame.Rect(WIDTH // 2 - 182, center.centery - 26, 364, 52)
            pygame.draw.rect(screen, (48, 0, 0), w_rect, border_radius=5)
            pygame.draw.rect(screen, RED, w_rect, width=2, border_radius=5)
            text(screen, fonts["small"], "!  GPS SIGNAL LOST  !", w_rect.centerx, w_rect.centery, RED)

        # ---- reset confirm / done overlays ----
        if reset_armed_until:
            r_rect = pygame.Rect(WIDTH // 2 - 202, HEIGHT - 58, 404, 44)
            pygame.draw.rect(screen, (42, 22, 0), r_rect, border_radius=4)
            pygame.draw.rect(screen, AMBER_HI, r_rect, width=2, border_radius=4)
            text(screen, fonts["small"], "PRESS R AGAIN TO CLEAR TIMES",
                 r_rect.centerx, r_rect.centery, AMBER_HI)
        elif reset_done_at:
            r_rect = pygame.Rect(WIDTH // 2 - 170, HEIGHT - 58, 340, 44)
            pygame.draw.rect(screen, (42, 22, 0), r_rect, border_radius=4)
            pygame.draw.rect(screen, AMBER, r_rect, width=2, border_radius=4)
            text(screen, fonts["small"], "LEADERBOARD CLEARED",
                 r_rect.centerx, r_rect.centery, AMBER)

        # Scanline overlay — drawn last to cover everything
        screen.blit(scanlines, (0, 0))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
