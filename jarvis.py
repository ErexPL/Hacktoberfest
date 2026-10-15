import ctypes
import difflib
import io
import json
import math
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.request
import wave
import webbrowser
import zipfile
from collections import deque
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
import numpy as np
import pyttsx3
import sounddevice as sd
from google import genai
from google.genai import types
from pynput import keyboard
from pynput.keyboard import Key, Controller as KeyboardController
from pynput.mouse import Button, Controller as MouseController
from PyQt6.QtCore import Qt, QBuffer, QIODevice, QTimer, pyqtSignal, QObject, QRectF, QPointF
from PyQt6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import QApplication, QWidget

# Automatyczna instalacja biblioteki vosk (nasłuchiwanie słowa "Jarvis" offline)
try:
    import vosk
except ImportError:
    print("[INSTALACJA]: Doinstalowywanie biblioteki 'vosk'...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "vosk"])
    import vosk

vosk.SetLogLevel(-1)

# Automatyczna instalacja biblioteki pycaw i comtypes (głośność + natywne TTS SAPI5)
try:
    import comtypes
    from comtypes import CLSCTX_ALL
    from comtypes.client import CreateObject
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
except ImportError:
    print("[INSTALACJA]: Doinstalowywanie bibliotek 'pycaw' oraz 'comtypes'...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pycaw", "comtypes"])
    import comtypes
    from comtypes import CLSCTX_ALL
    from comtypes.client import CreateObject
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

# Automatyczna instalacja biblioteki pyperclip (schowek + Discord)
try:
    import pyperclip
except ImportError:
    print("[INSTALACJA]: Doinstalowywanie biblioteki 'pyperclip'...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyperclip"])
    import pyperclip

# Wyczyszczenie martwych proxy i wymuszenie stabilnego IPv4 dla Windowsa
for proxy_var in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
    os.environ.pop(proxy_var, None)

_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _ipv4_only_getaddrinfo

# ==========================================
# KONFIGURACJA
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "apikey")
MODEL_NAME = "gemini-3.5-flash-lite"
SAMPLE_RATE = 16000

# Przezroczystość kamery na całym ekranie (0.18 = delikatny duch dłoni)
CAMERA_OPACITY = 0.18

# Czy Jarvis ma widzieć Twój ekran podczas wykonywania poleceń (przełączane też klawiszem F8)
SCREEN_VISION_DEFAULT = True

# Parametry automatycznego wykrywania końca mowy (VAD)
SPEECH_START_RMS = 420.0      # Głośność, od której Jarvis uznaje, że zacząłeś mówić
SILENCE_DURATION_SEC = 1.25   # Ile sekund ciszy po mówieniu automatycznie wysyła wiadomość
NO_SPEECH_TIMEOUT_SEC = 7.0   # Po ilu sekundach bez głosu zamknąć nakładkę

# --- DISCORD ---
DISCORD_OPEN_DELAY = 4.0
DISCORD_LAUNCH_TIMEOUT = 25.0
DISCORD_SEARCH_DELAY = 1.0
DISCORD_AUTO_SEND = True

DISCORD_ALIASES = {
    "maks": "deathshot",
    "piotr": "piczu",
    "dawid":"erexpl"
}
DISCORD_FUZZY_CUTOFF = 0.6

BASE_DIR = Path(__file__).parent
HAND_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
HAND_MODEL_PATH = BASE_DIR / "hand_landmarker.task"

VOSK_MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
VOSK_MODEL_DIR = BASE_DIR / "vosk-model-small-en-us-0.15"

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),                   # Kciuk
    (0, 5), (5, 6), (6, 7), (7, 8),                   # Wskazujący
    (5, 9), (9, 10), (10, 11), (11, 12),              # Środkowy
    (9, 13), (13, 14), (14, 15), (15, 16),            # Serdeczny
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20)   # Mały
]

SYSTEM_PROMPT = """
Jesteś zaawansowanym systemem operacyjnym J.A.R.V.I.S. Otrzymujesz polecenie głosowe użytkownika (oraz opcjonalnie zrzut ekranu użytkownika, jeśli pyta o coś na ekranie) i zwracasz WYŁĄCZNIE zestaw instrukcji wykonawczych.
Każda instrukcja MUSI mieć dokładnie taki format:

[ACTION: nazwa_akcji]
[ARG: argument]
[CONTENT_START]
treść lub kod (może być puste, jeśli akcja tego nie wymaga)
[CONTENT_END]

Dostępne akcje (możesz łączyć kilka naraz w jednej odpowiedzi):
1. build_file
  - ARG: ścieżka lub nazwa pliku (np. main.cpp, skrypt.py)
  - CONTENT: pełny, czysty kod źródłowy lub tekst pliku (bez znaczników markdown ```)
2. clipboard
  - ARG: krótki opis (np. Kod C++)
  - CONTENT: tekst lub kod, który ma zostać automatycznie skopiowany do schowka użytkownika
3. browser
  - ARG: pełny adres URL (np. [https://youtube.com](https://youtube.com)), "search: fraza" (wyszukiwanie Google) LUB "yt: fraza" (wyszukiwanie na YouTube)
  - CONTENT: zostaw puste
4. cmd
  - ARG: polecenie terminala Windows (np. g++ main.cpp -o main, start notepad, calc, explorer)
  - CONTENT: zostaw puste
5. system_control
  - ARG: jedna z komend systemowych:
    * "volume:XX" (ustawia głośność na XX%, np. volume:50)
    * "mute" / "unmute"
    * "media_play_pause" (wznów/zatrzymaj muzykę lub film)
    * "media_next" (następny utwór)
    * "media_prev" (poprzedni utwór)
    * "screenshot" (zrób zrzut ekranu i zapisz na Pulpicie)
    * "minimize_all" (zminimalizuj wszystkie okna / pokaż pulpit)
    * "maximize_window" (zmaksymalizuj aktywne okno)
    * "snap_left" / "snap_right" (przypnij aktywne okno do lewej/prawej połowy ekranu)
    * "close_window" (zamknij aktywne okno)
    * "lock_pc" (zablokuj ekran komputera)
  - CONTENT: zostaw puste
6. hand_control
  - ARG: "on" (włącz sterowanie dłonią/kamerą) lub "off" (wyłącz)
  - CONTENT: zostaw puste
7. ai_speech
  - ARG: "on" (włącz czytanie odpowiedzi na głos) lub "off" (wyłącz czytanie odpowiedzi)
  - CONTENT: zostaw puste
8. vision_mode
  - ARG: "on" (włącz analizę ekranu) lub "off" (wyłącz analizę ekranu)
  - CONTENT: zostaw puste
9. discord_message
  - ARG: nazwa odbiorcy w mianowniku lub dokładny login z listy znanych kontaktów Discord
  - CONTENT: sama treść wiadomości do wysłania w imieniu użytkownika
10. reply
  - ARG: krótki tytuł statusu (np. Gotowe, Analiza ekranu, Wysłano wiadomość)
  - CONTENT: konkretna, naturalna odpowiedź po polsku w stylu Jarvisa. ZAWSZE dodawaj akcję reply na samym końcu.
"""

if DISCORD_ALIASES:
    SYSTEM_PROMPT += "\nZnane kontakty Discord (jak użytkownik mówi -> dokładny login do wpisania w ARG):\n"
    for _spoken, _login in DISCORD_ALIASES.items():
        SYSTEM_PROMPT += f'- "{_spoken}" -> {_login}\n'
    SYSTEM_PROMPT += (
        "Jeśli nazwa wypowiedziana przez użytkownika brzmi podobnie do jednego z kontaktów, użyj loginu z listy.\n"
    )

# ==========================================
# SYNTEZATOR DŹWIĘKÓW SCI-FI (ZERO PLIKÓW ZEW.)
# ==========================================
class SoundFX:
    """Generuje futurystyczne dźwięki interfejsu Jarvisa w pamięci RAM za pomocą NumPy."""
    def __init__(self, fs: int = 44100):
        self.fs = fs
        self.sounds = {
            "wake": self._make_chime([520, 880, 1320], [0.05, 0.06, 0.11], vol=0.18),
            "send": self._make_chime([740, 980], [0.04, 0.06], vol=0.14),
            "success": self._make_chime([660, 880, 1100], [0.04, 0.04, 0.09], vol=0.15),
            "click": self._make_chime([1400], [0.025], vol=0.12),
            "off": self._make_chime([880, 480], [0.05, 0.09], vol=0.15),
        }

    def _make_chime(self, freqs: list[float], durations: list[float], vol: float = 0.15) -> np.ndarray:
        segments = []
        for f, d in zip(freqs, durations):
            t = np.linspace(0, d, int(self.fs * d), endpoint=False, dtype=np.float32)
            env = np.exp(-t * (18.0 / max(d, 0.01))) * np.minimum(t / 0.006, 1.0)
            wave_seg = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * (f * 1.5) * t)) * env * vol
            segments.append(wave_seg.astype(np.float32))
        return np.concatenate(segments)

    def play(self, name: str):
        arr = self.sounds.get(name)
        if arr is None:
            return
        def _run():
            try:
                sd.play(arr, self.fs, blocking=False)
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

sfx = SoundFX()

# ==========================================
# ADAPTACYJNY FILTR KURSORA (1-EURO VELOCITY FILTER)
# ==========================================
class AdaptiveCursorFilter:
    """
    Eliminuje drżenie dłoni przy precyzyjnym celowaniu, a przy szybkim ruchu ręki
    automatycznie zwiększa czułość, dając zerowe opóźnienie (0 lag).
    """
    def __init__(self, screen_w: int, screen_h: int):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.x = screen_w / 2.0
        self.y = screen_h / 2.0
        self.min_alpha = 0.08     # Bardzo silne wygładzanie przy precyzyjnym celowaniu
        self.max_alpha = 0.72     # Błyskawiczna reakcja przy szybkim ruchu
        self.vel_scale = 0.018    # Próg prędkości przejścia
        self.deadzone_px = 2.2    # Martwa strefa mikroruchów

    def update(self, target_x: float, target_y: float, pre_pinch_lock: bool = False) -> tuple[int, int]:
        dx = target_x - self.x
        dy = target_y - self.y
        dist_px = math.hypot(dx, dy)

        if dist_px < self.deadzone_px:
            return int(self.x), int(self.y)

        norm_vel = dist_px / max(self.screen_w, 1)
        alpha = self.min_alpha + (self.max_alpha - self.min_alpha) * min(norm_vel / self.vel_scale, 1.0)

        # Magnetyczna stabilizacja w momencie zbliżania palców do kliknięcia (Pinch)
        if pre_pinch_lock:
            alpha *= 0.18

        self.x += dx * alpha
        self.y += dy * alpha
        return int(self.x), int(self.y)

# ==========================================
# KOMUNIKACJA WĄTKÓW Z GUI
# ==========================================
class JarvisSignals(QObject):
    volume_changed = pyqtSignal(float)
    status_changed = pyqtSignal(str)
    action_badge_changed = pyqtSignal(str)
    state_changed = pyqtSignal(str)
    speech_mode_changed = pyqtSignal(bool)
    hand_mode_changed = pyqtSignal(bool)
    vision_mode_changed = pyqtSignal(bool)
    gesture_changed = pyqtSignal(str, float)
    hide_overlay = pyqtSignal()
    show_overlay = pyqtSignal()
    finish_listening = pyqtSignal()
    abort_listening = pyqtSignal()
    camera_frame_ready = pyqtSignal(QImage)
    hand_overlay_visible = pyqtSignal(bool)

# ==========================================
# MODUŁ CZYTANIA ODPOWIEDZI (AI SPEECH ON / OFF)
# ==========================================
class SpeechManager:
    def __init__(self, signals: JarvisSignals):
        self.signals = signals
        self.enabled = True
        self.speaking_event = threading.Event()
        self._stop_requested = threading.Event()
        self._queue: queue.Queue[tuple[str, bool]] = queue.Queue()

        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def set_enabled(self, state: bool, announce: bool = True):
        self.enabled = state
        self.signals.speech_mode_changed.emit(self.enabled)
        state_str = "ON" if self.enabled else "OFF"
        print(f"[AI SPEECH]: Czytanie odpowiedzi ustawione na: {state_str}")

        if not self.enabled:
            self.stop_speaking()
            sfx.play("off")
        else:
            sfx.play("success")
            if announce:
                self.speak("System głosowy aktywny.", force=True)

    def toggle(self):
        self.set_enabled(not self.enabled, announce=True)

    def stop_speaking(self):
        self._stop_requested.set()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break

    def speak(self, text: str, force: bool = False):
        clean_text = text.strip()
        if not clean_text:
            return
        if not self.enabled and not force:
            print(f"[AI SPEECH OFF - pominięto czytanie]: {clean_text}")
            return

        self._stop_requested.clear()
        self.speaking_event.set()
        self._queue.put((clean_text, force))

    def wait_until_done(self, timeout: float = 45.0):
        if not self.enabled and self._queue.empty() and not self.speaking_event.is_set():
            return
        start = time.monotonic()
        time.sleep(0.08)
        while (self.speaking_event.is_set() or not self._queue.empty()) and (time.monotonic() - start) < timeout:
            if self._stop_requested.is_set():
                break
            time.sleep(0.05)

    def _worker(self):
        comtypes.CoInitialize()
        sapi_voice = None
        fallback_engine = None

        try:
            sapi_voice = CreateObject("SAPI.SpVoice")
            sapi_voice.Rate = 1
            sapi_voice.Volume = 100
            voices = sapi_voice.GetVoices()
            for i in range(voices.Count):
                v = voices.Item(i)
                desc = v.GetDescription().lower()
                if "pl" in desc or "polish" in desc or "paulina" in desc or "polski" in desc:
                    sapi_voice.Voice = v
                    break
        except Exception as e:
            print(f"[SAPI INIT INFO]: Przełączam na pyttsx3 ({e})")
            sapi_voice = None

        if sapi_voice is None:
            try:
                fallback_engine = pyttsx3.init()
                fallback_engine.setProperty("rate", 185)
                fallback_engine.setProperty("volume", 1.0)
                for v in fallback_engine.getProperty("voices"):
                    v_info = f"{v.id} {v.name}".lower()
                    if "pl" in v_info or "polish" in v_info or "paulina" in v_info or "polski" in v_info:
                        fallback_engine.setProperty("voice", v.id)
                        break
            except Exception as e:
                print(f"[TTS BŁĄD]: Nie udało się zainicjować silnika mowy: {e}")

        while True:
            text, force = self._queue.get()
            try:
                if not self.enabled and not force:
                    continue

                self.speaking_event.set()
                self._stop_requested.clear()

                if sapi_voice is not None:
                    sapi_voice.Speak(text, 1)
                    phase = 0.0
                    while not sapi_voice.WaitUntilDone(40):
                        if self._stop_requested.is_set() or (not self.enabled and not force):
                            sapi_voice.Speak("", 2)
                            break
                        phase += 0.35
                        sim_vol = 0.25 + 0.35 * abs(math.sin(phase)) * abs(math.cos(phase * 0.7))
                        self.signals.volume_changed.emit(sim_vol)
                    self.signals.volume_changed.emit(0.0)

                elif fallback_engine is not None:
                    fallback_engine.say(text)
                    fallback_engine.runAndWait()

            except Exception as e:
                print(f"[TTS WORKER BŁĄD]: {e}")
            finally:
                self._queue.task_done()
                if self._queue.empty():
                    time.sleep(0.2)
                    self.speaking_event.clear()

# ==========================================
# PEŁNOEKRANOWA PRZEZROCZYSTA NAKŁADKA KAMERY
# ==========================================
class HandCameraOverlay(QWidget):
    """Pełnoekranowe okno o bardzo małym kryciu, które przepuszcza kliknięcia myszy."""
    def __init__(self, signals: JarvisSignals):
        super().__init__()
        self.signals = signals
        self.current_image: QImage | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowOpacity(CAMERA_OPACITY)

        self.signals.camera_frame_ready.connect(self.update_frame)
        self.signals.hand_overlay_visible.connect(self.set_overlay_visible)

    def _apply_click_through_win32(self):
        hwnd = int(self.winId())
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_TOOLWINDOW = 0x00000080
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
        )

    def set_overlay_visible(self, visible: bool):
        if visible:
            self.showFullScreen()
            self._apply_click_through_win32()
        else:
            self.hide()
            self.current_image = None

    def update_frame(self, image: QImage):
        self.current_image = image
        if self.isVisible():
            self.update()

    def paintEvent(self, _event):
        if self.current_image is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(self.rect(), self.current_image)

# ==========================================
# STAŁY HOLOGRAFICZNY MINI-HUD (PRAWY GÓRNY RÓG)
# ==========================================
class StarkMiniHud(QWidget):
    """
    Niewielki, futurystyczny panel HUD w prawym górnym rogu ekranu (Click-Through).
    Pokazuje status Jarvisa, aktywne moduły oraz aktualnie rozpoznawany gest dłoni.
    """
    def __init__(self, signals: JarvisSignals):
        super().__init__()
        self.signals = signals
        self.hud_visible = True
        self.jarvis_state = "STANDBY"
        self.speech_on = True
        self.hand_on = False
        self.vision_on = SCREEN_VISION_DEFAULT
        self.gesture_name = "BRAK"
        self.gesture_val = 0.0
        self.phase = 0.0

        user32 = ctypes.windll.user32
        screen_w = user32.GetSystemMetrics(0)

        self.w_width = 330
        self.w_height = 135
        self.setGeometry(screen_w - self.w_width - 22, 22, self.w_width, self.w_height)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.signals.state_changed.connect(self._on_state)
        self.signals.speech_mode_changed.connect(self._on_speech)
        self.signals.hand_mode_changed.connect(self._on_hand)
        self.signals.vision_mode_changed.connect(self._on_vision)
        self.signals.gesture_changed.connect(self._on_gesture)
        self.signals.hide_overlay.connect(lambda: self._on_state("STANDBY"))

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(40)

        self.show()
        self._apply_click_through_win32()

    def _apply_click_through_win32(self):
        hwnd = int(self.winId())
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_TOOLWINDOW = 0x00000080
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
        )

    def toggle_hud(self):
        self.hud_visible = not self.hud_visible
        if self.hud_visible:
            self.show()
            self._apply_click_through_win32()
        else:
            self.hide()

    def _on_state(self, st: str):
        self.jarvis_state = st.upper()
        self.update()

    def _on_speech(self, val: bool):
        self.speech_on = val
        self.update()

    def _on_hand(self, val: bool):
        self.hand_on = val
        if not val:
            self.gesture_name = "OFF"
        self.update()

    def _on_vision(self, val: bool):
        self.vision_on = val
        self.update()

    def _on_gesture(self, name: str, val: float):
        self.gesture_name = name
        self.gesture_val = val
        self.update()

    def _tick(self):
        if self.isVisible():
            self.phase += 0.1
            self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)

        painter.fillPath(path, QColor(6, 14, 26, 175))
        border_col = QColor(0, 215, 255, 130) if self.hand_on else QColor(0, 160, 220, 80)
        painter.setPen(QPen(border_col, 1.5))
        painter.drawPath(path)

        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.setPen(QColor(0, 225, 255, 230))
        painter.drawText(14, 22, "J.A.R.V.I.S.  //  STARK OS MK-II")

        dot_alpha = int(150 + 100 * math.sin(self.phase * 2.0))
        if self.jarvis_state == "LISTENING":
            dot_col = QColor(0, 230, 255, dot_alpha)
        elif self.jarvis_state == "THINKING":
            dot_col = QColor(200, 100, 255, dot_alpha)
        elif self.jarvis_state == "SPEAKING":
            dot_col = QColor(0, 255, 160, dot_alpha)
        else:
            dot_col = QColor(0, 200, 130, 190)

        painter.setBrush(dot_col)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.width() - 24, 12, 10, 10)

        modules = [
            ("VISION [F8]", self.vision_on),
            ("HAND [F10]", self.hand_on),
            ("SPEECH [F11]", self.speech_on),
        ]
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        x_off = 14
        for label, active in modules:
            w_pill = 96
            pill_rect = QRectF(x_off, 34, w_pill, 22)
            p_path = QPainterPath()
            p_path.addRoundedRect(pill_rect, 5, 5)
            bg = QColor(0, 200, 150, 55) if active else QColor(40, 55, 75, 90)
            fg = QColor(110, 255, 200, 240) if active else QColor(130, 150, 175, 160)
            painter.fillPath(p_path, bg)
            painter.setPen(QPen(fg, 1.0))
            painter.drawPath(p_path)
            painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, label)
            x_off += w_pill + 7

        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        painter.setPen(QColor(205, 230, 255, 220))
        if self.hand_on:
            painter.drawText(14, 78, f"GEST:  {self.gesture_name}")
            bar_bg = QRectF(14, 88, self.width() - 28, 7)
            painter.fillRect(bar_bg, QColor(25, 45, 70, 160))
            fill_w = (self.width() - 28) * float(np.clip(self.gesture_val, 0.0, 1.0))
            if fill_w > 1:
                painter.fillRect(QRectF(14, 88, fill_w, 7), QColor(0, 230, 255, 220))
            painter.setFont(QFont("Segoe UI", 8))
            painter.setPen(QColor(145, 185, 220, 190))
            painter.drawText(14, 116, "Pinch: LPM | Środkowy: PPM | 3-Palce: Scroll | V: Alt+Tab")
        else:
            painter.drawText(14, 80, f"STATUS:  {self.jarvis_state}  (Powiedz 'Jarvis' lub [F9])")
            painter.setFont(QFont("Segoe UI", 8))
            painter.setPen(QColor(145, 185, 220, 180))
            painter.drawText(14, 108, "[F10] Kamera Hand Control   |   [F12] Ukryj HUD")

# ==========================================
# MODUŁ STEROWANIA DŁONIĄ (HAND CONTROL 2.0)
# ==========================================
class HandControlManager:
    def __init__(self, signals: JarvisSignals):
        self.signals = signals
        self.running = False
        self.thread = None
        self.mouse = MouseController()
        self.kb = KeyboardController()

        user32 = ctypes.windll.user32
        self.screen_w = user32.GetSystemMetrics(0)
        self.screen_h = user32.GetSystemMetrics(1)

        self.margin = 0.12
        self.pinch_start_ratio = 0.23
        self.pinch_stop_ratio = 0.37
        self.pinch_confirm_frames = 3
        self.cursor_filter = AdaptiveCursorFilter(self.screen_w, self.screen_h)

    def _ensure_model_downloaded(self) -> bool:
        if HAND_MODEL_PATH.exists():
            return True
        try:
            self.signals.status_changed.emit("Pobieram model dłoni MediaPipe (~7.5 MB)...")
            urllib.request.urlretrieve(HAND_MODEL_URL, str(HAND_MODEL_PATH))
            return True
        except Exception as e:
            print(f"[BŁĄD POBIERANIA MODELU DŁONI]: {e}")
            return False

    def start(self):
        if self.running:
            return
        self.running = True
        self.signals.hand_mode_changed.emit(True)
        sfx.play("success")
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.signals.hand_mode_changed.emit(False)
        sfx.play("off")

    def toggle(self):
        if self.running:
            self.stop()
            speak_text("Wyłączono tryb hand control.")
        else:
            self.start()
            speak_text("Włączono tryb hand control.")

    @staticmethod
    def _dist(p1, p2) -> float:
        return math.hypot(p1.x - p2.x, p1.y - p2.y)

    def _get_palm_size(self, lm) -> float:
        return max(self._dist(lm[0], lm[9]), 0.01)

    def _is_hand_facing_camera(self, lm) -> bool:
        palm_len = self._get_palm_size(lm)
        palm_width = self._dist(lm[5], lm[17])
        return (palm_width / palm_len) > 0.36

    def _is_fist(self, lm) -> bool:
        wrist = lm[0]
        for tip_idx, pip_idx in ((8, 6), (12, 10), (16, 14), (20, 18)):
            if self._dist(wrist, lm[tip_idx]) > self._dist(wrist, lm[pip_idx]) * 1.05:
                return False
        return True

    def _is_three_finger_scroll(self, lm) -> bool:
        wrist = lm[0]
        palm_size = self._get_palm_size(lm)
        idx_ext = self._dist(wrist, lm[8]) > self._dist(wrist, lm[6]) * 1.18
        mid_ext = self._dist(wrist, lm[12]) > self._dist(wrist, lm[10]) * 1.18
        ring_ext = self._dist(wrist, lm[16]) > self._dist(wrist, lm[14]) * 1.15
        pinky_curled = self._dist(wrist, lm[20]) < self._dist(wrist, lm[18]) * 1.08
        thumb_away = self._dist(lm[4], lm[8]) > palm_size * 0.35
        return idx_ext and mid_ext and ring_ext and pinky_curled and thumb_away

    def _get_peace_state(self, lm) -> str:
        wrist = lm[0]
        palm_size = self._get_palm_size(lm)

        index_ext = self._dist(wrist, lm[8]) > self._dist(wrist, lm[6]) * 1.18
        middle_ext = self._dist(wrist, lm[12]) > self._dist(wrist, lm[10]) * 1.18
        ring_curled = self._dist(wrist, lm[16]) < self._dist(wrist, lm[14]) * 1.06
        pinky_curled = self._dist(wrist, lm[20]) < self._dist(wrist, lm[18]) * 1.06
        thumb_away = self._dist(lm[4], lm[8]) > palm_size * 0.35

        if not (index_ext and middle_ext and ring_curled and pinky_curled and thumb_away):
            return "NONE"

        tip_sep = self._dist(lm[8], lm[12]) / palm_size
        if tip_sep > 0.34:
            return "PEACE_SPREAD"
        elif tip_sep < 0.25:
            return "PEACE_JOINED"
        return "PEACE_TRANSITION"

    def _is_circle_hand(self, lm) -> bool:
        palm_size = self._get_palm_size(lm)
        tips_touch = self._dist(lm[4], lm[8]) < palm_size * 0.34
        inner_hole_open = self._dist(lm[3], lm[6]) > palm_size * 0.28
        index_base_up = self._dist(lm[0], lm[6]) > palm_size * 0.85
        return tips_touch and inner_hole_open and index_base_up

    def _is_open_palm(self, lm) -> bool:
        wrist = lm[0]
        palm_size = self._get_palm_size(lm)
        for tip_idx, pip_idx in ((8, 6), (12, 10), (16, 14), (20, 18)):
            if self._dist(wrist, lm[tip_idx]) < self._dist(wrist, lm[pip_idx]) * 1.18:
                return False
        if self._dist(lm[4], lm[5]) < palm_size * 0.45:
            return False
        return True

    def _init_volume_interface(self):
        try:
            comtypes.CoInitialize()
            devices = AudioUtilities.GetSpeakers()
            if hasattr(devices, "EndpointVolume"):
                return devices.EndpointVolume
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
        except Exception:
            return None

    def _set_system_volume(self, vol_interface, level_0_to_1: float):
        level = float(np.clip(level_0_to_1, 0.0, 1.0))
        if vol_interface is not None:
            try:
                vol_interface.SetMasterVolumeLevelScalar(level, None)
            except Exception:
                pass

    def _draw_sci_fi_hand(self, frame, landmarks, mode_color, reticle_pos: tuple[int, int] | None = None, progress: float = 0.0):
        h, w, _ = frame.shape
        pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]

        for i, j in HAND_CONNECTIONS:
            cv2.line(frame, pts[i], pts[j], mode_color, 2, cv2.LINE_AA)

        for idx, pt in enumerate(pts):
            radius = 7 if idx in (4, 8, 12) else 4
            cv2.circle(frame, pt, radius, (255, 255, 255), cv2.FILLED, cv2.LINE_AA)

        if reticle_pos is not None:
            rx, ry = reticle_pos
            cv2.circle(frame, (rx, ry), 16, mode_color, 2, cv2.LINE_AA)
            cv2.circle(frame, (rx, ry), 4, (255, 255, 255), cv2.FILLED, cv2.LINE_AA)
            if progress > 0.05:
                angle = int(360 * min(progress, 1.0))
                cv2.ellipse(frame, (rx, ry), (22, 22), -90, 0, angle, (0, 255, 160), 3, cv2.LINE_AA)

    def _worker(self):
        if not self._ensure_model_downloaded():
            self.running = False
            self.signals.hand_mode_changed.emit(False)
            return

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            self.signals.status_changed.emit("Błąd: Nie można otworzyć kamery!")
            speak_text("Nie udało się uzyskać dostępu do kamery.")
            self.running = False
            self.signals.hand_mode_changed.emit(False)
            return

        vol_interface = self._init_volume_interface()

        base_options = mp_python.BaseOptions(model_asset_path=str(HAND_MODEL_PATH))
        options = mp_vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.70,
            min_hand_presence_confidence=0.70,
            min_tracking_confidence=0.70,
        )

        is_pinching = False
        pinch_hold_frames = 0
        pinch_release_frames = 0

        right_click_frames = 0
        last_right_click_time = 0.0

        scroll_anchor_y: float | None = None
        scroll_frames = 0

        is_alt_tab_active = False
        peace_spread_frames = 0
        peace_joined_frames = 0

        two_palms_frames = 0
        last_minimize_time = 0.0
        media_fist_frames = 0
        last_media_toggle_time = 0.0

        prev_raw_x, prev_raw_y = 0.5, 0.5
        smooth_vol = 0.5
        last_ts_ms = 0

        self.signals.hand_overlay_visible.emit(True)

        try:
            with mp_vision.HandLandmarker.create_from_options(options) as landmarker:
                while self.running and cap.isOpened():
                    success, frame = cap.read()
                    if not success:
                        time.sleep(0.01)
                        continue

                    frame = cv2.flip(frame, 1)
                    h, w, _ = frame.shape
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                    ts_ms = int(time.monotonic() * 1000)
                    if ts_ms <= last_ts_ms:
                        ts_ms = last_ts_ms + 1
                    last_ts_ms = ts_ms

                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                    result = landmarker.detect_for_video(mp_image, ts_ms)

                    hands_list = result.hand_landmarks if result.hand_landmarks else []
                    two_hand_gesture_active = False

                    # =========================================================
                    # 1. GESTY DWÓCH DŁONI:
                    #    A) 2 Otwarte Dłonie -> Minimalizacja (Win+D)
                    #    B) 1. Dłoń Kółko 'O' + 2. Dłoń Pięść -> Play/Pause Mediów
                    #    C) 1. Dłoń Kółko 'O' + 2. Dłoń Wskazujący -> Głośność (0-100%)
                    # =========================================================
                    if len(hands_list) >= 2:
                        h0, h1 = hands_list[0], hands_list[1]

                        if self._is_open_palm(h0) and self._is_open_palm(h1):
                            two_hand_gesture_active = True
                            two_palms_frames += 1
                            prog = min(two_palms_frames / 7.0, 1.0)
                            self.signals.gesture_changed.emit("MINIMALIZACJA (2 DŁONIE)", prog)

                            for h_lm in (h0, h1):
                                self._draw_sci_fi_hand(frame, h_lm, (255, 0, 255))

                            if two_palms_frames >= 7 and (time.time() - last_minimize_time) > 2.5:
                                if is_pinching:
                                    self.mouse.release(Button.left)
                                    is_pinching = False
                                if is_alt_tab_active:
                                    self.kb.release(Key.alt)
                                    is_alt_tab_active = False

                                with self.kb.pressed(Key.cmd):
                                    self.kb.tap("d")
                                sfx.play("off")
                                last_minimize_time = time.time()
                                two_palms_frames = 0
                        else:
                            two_palms_frames = 0
                            circle_hand = None
                            second_hand = None

                            if self._is_circle_hand(h0):
                                circle_hand, second_hand = h0, h1
                            elif self._is_circle_hand(h1):
                                circle_hand, second_hand = h1, h0

                            if circle_hand is not None and second_hand is not None:
                                two_hand_gesture_active = True
                                if is_pinching:
                                    self.mouse.release(Button.left)
                                    is_pinching = False
                                    pinch_hold_frames = 0

                                if self._is_fist(second_hand):
                                    media_fist_frames += 1
                                    prog = min(media_fist_frames / 5.0, 1.0)
                                    self.signals.gesture_changed.emit("MEDIA PLAY / PAUSE", prog)
                                    self._draw_sci_fi_hand(frame, circle_hand, (0, 215, 255))
                                    self._draw_sci_fi_hand(frame, second_hand, (255, 120, 0))

                                    if media_fist_frames >= 5 and (time.time() - last_media_toggle_time) > 1.5:
                                        self.kb.tap(Key.media_play_pause)
                                        sfx.play("click")
                                        last_media_toggle_time = time.time()
                                        media_fist_frames = 0
                                else:
                                    media_fist_frames = 0
                                    idx_tip = second_hand[8]
                                    v_top = self.margin + 0.05
                                    v_bot = 1.0 - self.margin - 0.05
                                    raw_vol = 1.0 - ((idx_tip.y - v_top) / max(v_bot - v_top, 0.1))
                                    target_vol = float(np.clip(raw_vol, 0.0, 1.0))

                                    smooth_vol += (target_vol - smooth_vol) * 0.25
                                    self._set_system_volume(vol_interface, smooth_vol)

                                    vol_pct = int(round(smooth_vol * 100))
                                    self.signals.gesture_changed.emit(f"GŁOŚNOŚĆ: {vol_pct}%", smooth_vol)

                                    self._draw_sci_fi_hand(frame, circle_hand, (0, 215, 255))
                                    self._draw_sci_fi_hand(frame, second_hand, (0, 255, 160))

                                    c_x = int(((circle_hand[4].x + circle_hand[8].x) / 2.0) * w)
                                    c_y = int(((circle_hand[4].y + circle_hand[8].y) / 2.0) * h)
                                    s_x, s_y = int(idx_tip.x * w), int(idx_tip.y * h)

                                    cv2.circle(frame, (c_x, c_y), 22, (0, 215, 255), 3, cv2.LINE_AA)
                                    cv2.circle(frame, (s_x, s_y), 14, (0, 255, 160), cv2.FILLED, cv2.LINE_AA)
                                    cv2.line(frame, (c_x, c_y), (s_x, s_y), (0, 255, 200), 2, cv2.LINE_AA)
                                    cv2.putText(
                                        frame,
                                        f"VOL: {vol_pct}%",
                                        (s_x - 50, max(s_y - 25, 40)),
                                        cv2.FONT_HERSHEY_SIMPLEX,
                                        0.8,
                                        (0, 255, 160),
                                        2,
                                        cv2.LINE_AA,
                                    )
                    else:
                        two_palms_frames = 0
                        media_fist_frames = 0

                    # =========================================================
                    # 2. OBSŁUGA POJEDYNCZEJ DŁONI:
                    #    - 3 Palce -> Płynny Scroll
                    #    - Peace Sign ('V') -> Alt+Tab + Złączenie 2 palców -> Wybór
                    #    - Kciuk + Środkowy -> Prawy Klik (PPM)
                    #    - Kciuk + Wskazujący -> Precyzyjny Pinch LPM + Przeciąganie
                    # =========================================================
                    if not two_hand_gesture_active and len(hands_list) >= 1:
                        lm = hands_list[0]
                        thumb_tip = lm[4]
                        index_mcp = lm[5]
                        index_tip = lm[8]
                        middle_mcp = lm[9]
                        middle_tip = lm[12]

                        palm_size = self._get_palm_size(lm)
                        peace_state = self._get_peace_state(lm)
                        three_scroll = (not is_alt_tab_active) and (not is_pinching) and self._is_three_finger_scroll(lm)

                        if three_scroll:
                            scroll_frames += 1
                            hand_y = lm[9].y
                            if scroll_anchor_y is None:
                                scroll_anchor_y = hand_y
                            diff_y = scroll_anchor_y - hand_y
                            if abs(diff_y) > 0.025 and scroll_frames >= 2:
                                scroll_steps = int(np.clip(diff_y * 22.0, -5, 5))
                                if scroll_steps != 0:
                                    self.mouse.scroll(0, scroll_steps)
                            self.signals.gesture_changed.emit("SCROLL (3 PALCE)", min(abs(diff_y) * 5.0, 1.0))
                            self._draw_sci_fi_hand(frame, lm, (255, 180, 0), (int(lm[9].x * w), int(lm[9].y * h)))
                        else:
                            scroll_anchor_y = None
                            scroll_frames = 0

                            if is_alt_tab_active or peace_state != "NONE":
                                raw_x = (index_mcp.x + middle_mcp.x) / 2.0
                                raw_y = (index_mcp.y + middle_mcp.y) / 2.0
                            else:
                                raw_x = thumb_tip.x * 0.4 + index_tip.x * 0.4 + index_mcp.x * 0.2
                                raw_y = thumb_tip.y * 0.4 + index_tip.y * 0.4 + index_mcp.y * 0.2

                            hand_speed = math.hypot(raw_x - prev_raw_x, raw_y - prev_raw_y)
                            prev_raw_x, prev_raw_y = raw_x, raw_y

                            norm_x = float(np.clip((raw_x - self.margin) / (1.0 - 2.0 * self.margin), 0.0, 1.0))
                            norm_y = float(np.clip((raw_y - self.margin) / (1.0 - 2.0 * self.margin), 0.0, 1.0))

                            target_x = norm_x * self.screen_w
                            target_y = norm_y * self.screen_h

                            pinch_dist_2d = self._dist(thumb_tip, index_tip)
                            norm_pinch = pinch_dist_2d / palm_size
                            z_diff = abs(thumb_tip.z - index_tip.z)

                            pre_pinch_lock = (not is_pinching) and (not is_alt_tab_active) and (norm_pinch < 0.34)
                            cur_x, cur_y = self.cursor_filter.update(target_x, target_y, pre_pinch_lock=pre_pinch_lock)
                            self.mouse.position = (cur_x, cur_y)

                            if peace_state == "PEACE_SPREAD":
                                peace_spread_frames += 1
                                peace_joined_frames = 0

                                if is_pinching:
                                    self.mouse.release(Button.left)
                                    is_pinching = False
                                    pinch_hold_frames = 0

                                self.signals.gesture_changed.emit("ALT+TAB (PEACE V)", min(peace_spread_frames / 5.0, 1.0))
                                if not is_alt_tab_active and peace_spread_frames >= 5:
                                    self.kb.press(Key.alt)
                                    time.sleep(0.02)
                                    self.kb.tap(Key.tab)
                                    is_alt_tab_active = True
                                    sfx.play("click")

                            elif peace_state == "PEACE_JOINED":
                                peace_spread_frames = 0
                                if is_alt_tab_active:
                                    peace_joined_frames += 1
                                    self.signals.gesture_changed.emit("WYBÓR OKNA (ZŁĄCZONE)", min(peace_joined_frames / 4.0, 1.0))
                                    if peace_joined_frames >= 4:
                                        self.mouse.click(Button.left)
                                        time.sleep(0.04)
                                        self.kb.release(Key.alt)
                                        is_alt_tab_active = False
                                        peace_joined_frames = 0
                                        sfx.play("click")
                            else:
                                peace_spread_frames = 0
                                peace_joined_frames = 0

                            if not is_alt_tab_active and peace_state == "NONE":
                                facing_ok = self._is_hand_facing_camera(lm)
                                mid_pinch_norm = self._dist(thumb_tip, middle_tip) / palm_size
                                idx_extended = self._dist(lm[0], index_tip) > self._dist(lm[0], lm[6]) * 1.15

                                if not is_pinching and mid_pinch_norm < 0.24 and idx_extended and facing_ok:
                                    right_click_frames += 1
                                    self.signals.gesture_changed.emit("PRAWY KLIK (PPM)", min(right_click_frames / 4.0, 1.0))
                                    if right_click_frames >= 4 and (time.time() - last_right_click_time) > 0.7:
                                        self.mouse.click(Button.right)
                                        sfx.play("click")
                                        last_right_click_time = time.time()
                                        right_click_frames = 0
                                else:
                                    right_click_frames = 0

                                    pinch_valid = (
                                        norm_pinch < self.pinch_start_ratio
                                        and z_diff < 0.08
                                        and facing_ok
                                        and hand_speed < 0.038
                                    )

                                    if not is_pinching:
                                        if pinch_valid:
                                            pinch_hold_frames += 1
                                            self.signals.gesture_changed.emit(
                                                "ŁAPANIE (PINCH)", pinch_hold_frames / float(self.pinch_confirm_frames)
                                            )
                                            if pinch_hold_frames >= self.pinch_confirm_frames:
                                                self.mouse.press(Button.left)
                                                is_pinching = True
                                                pinch_release_frames = 0
                                                sfx.play("click")
                                        else:
                                            pinch_hold_frames = max(0, pinch_hold_frames - 1)
                                            self.signals.gesture_changed.emit("KURSOR AKTYWNY", max(0.0, 1.0 - norm_pinch))
                                    else:
                                        self.signals.gesture_changed.emit("PRZECIĄGANIE (HOLD)", 1.0)
                                        if norm_pinch > self.pinch_stop_ratio:
                                            pinch_release_frames += 1
                                            if pinch_release_frames >= 3:
                                                self.mouse.release(Button.left)
                                                is_pinching = False
                                                pinch_hold_frames = 0
                                        else:
                                            pinch_release_frames = 0

                            if is_alt_tab_active:
                                skel_color = (0, 165, 255)
                            elif is_pinching:
                                skel_color = (0, 255, 0)
                            else:
                                skel_color = (255, 220, 0)

                            cx, cy = int(raw_x * w), int(raw_y * h)
                            prog_ring = 1.0 if is_pinching else (pinch_hold_frames / float(self.pinch_confirm_frames))
                            self._draw_sci_fi_hand(frame, lm, skel_color, (cx, cy), prog_ring)
                    elif not two_hand_gesture_active:
                        self.signals.gesture_changed.emit("SZUKAM DŁONI...", 0.0)

                    x1, y1 = int(w * self.margin), int(h * self.margin)
                    x2, y2 = int(w * (1.0 - self.margin)), int(h * (1.0 - self.margin))
                    cropped_bgr = frame[y1:y2, x1:x2]
                    cropped_rgb = cv2.cvtColor(cropped_bgr, cv2.COLOR_BGR2RGB)

                    ch, cw, ch_channels = cropped_rgb.shape
                    bytes_per_line = ch_channels * cw
                    qimg = QImage(cropped_rgb.data, cw, ch, bytes_per_line, QImage.Format.Format_RGB888).copy()
                    self.signals.camera_frame_ready.emit(qimg)

        finally:
            if is_pinching:
                self.mouse.release(Button.left)
            if is_alt_tab_active:
                self.kb.release(Key.alt)
            cap.release()
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass
            self.signals.hand_overlay_visible.emit(False)


# ==========================================
# WYKONYWANIE INSTRUKCJI (NARZĘDZIA JARVISA)
# ==========================================
speech_manager: SpeechManager | None = None
hand_manager: HandControlManager | None = None
controller_ref = None
sys_kb = KeyboardController()

def speak_text(text: str, force: bool = False):
    if speech_manager is not None:
        speech_manager.speak(text, force=force)

def action_build_file(arg: str, content: str, signals: JarvisSignals):
    path = Path(arg.strip())
    path.parent.mkdir(parents=True, exist_ok=True)
    clean_content = re.sub(r"^```\w*\n|```$", "", content.strip(), flags=re.MULTILINE)
    path.write_text(clean_content.strip() + "\n", encoding="utf-8")
    signals.action_badge_changed.emit(f"BUILD FILE // {path.name}")
    signals.status_changed.emit(f"Utworzono plik: {path.name}")
    sfx.play("success")

def action_clipboard(arg: str, content: str, signals: JarvisSignals):
    clean_content = re.sub(r"^```\w*\n|```$", "", content.strip(), flags=re.MULTILINE)
    pyperclip.copy(clean_content)
    signals.action_badge_changed.emit(f"CLIPBOARD // {arg.strip() or 'SKOPIOWANO'}")
    signals.status_changed.emit("Skopiowano wygenerowaną treść do schowka.")
    sfx.play("success")

def action_browser(arg: str, _content: str, signals: JarvisSignals):
    query = arg.strip()
    if query.lower().startswith("search:"):
        search_term = query[7:].strip()
        url = f"[https://www.google.com/search?q=](https://www.google.com/search?q=){quote_plus(search_term)}"
    elif query.lower().startswith("yt:"):
        yt_term = query[3:].strip()
        url = f"[https://www.youtube.com/results?search_query=](https://www.youtube.com/results?search_query=){quote_plus(yt_term)}"
    elif not query.startswith(("http://", "https://")):
        url = f"https://{query}"
    else:
        url = query
    webbrowser.open(url)
    signals.action_badge_changed.emit(f"BROWSER // {query[:28]}")
    signals.status_changed.emit(f"Otwieram w przeglądarce: {query}")
    sfx.play("success")

def action_cmd(arg: str, _content: str, signals: JarvisSignals):
    cmd = arg.strip()
    signals.action_badge_changed.emit(f"TERMINAL // {cmd[:28]}")
    signals.status_changed.emit(f"CMD: {cmd}")
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    if result.stdout:
        print(f"\n[CMD OUTPUT]:\n{result.stdout}")
    if result.stderr:
        print(f"\n[CMD STDERR]:\n{result.stderr}")
    sfx.play("success")

def action_system_control(arg: str, _content: str, signals: JarvisSignals):
    cmd = arg.strip().lower()
    signals.action_badge_changed.emit(f"SYSTEM // {cmd.upper()}")

    if cmd.startswith("volume:"):
        try:
            pct = float(cmd.split(":", 1)[1].strip().replace("%", ""))
            comtypes.CoInitialize()
            devices = AudioUtilities.GetSpeakers()
            ep = devices.EndpointVolume if hasattr(devices, "EndpointVolume") else ctypes.cast(
                devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None),
                ctypes.POINTER(IAudioEndpointVolume),
            )
            ep.SetMasterVolumeLevelScalar(float(np.clip(pct / 100.0, 0.0, 1.0)), None)
        except Exception as e:
            print(f"[SYSTEM VOLUME BŁĄD]: {e}")
    elif cmd == "mute":
        sys_kb.tap(Key.media_volume_mute)
    elif cmd == "unmute":
        sys_kb.tap(Key.media_volume_mute)
    elif cmd == "media_play_pause":
        sys_kb.tap(Key.media_play_pause)
    elif cmd == "media_next":
        sys_kb.tap(Key.media_next)
    elif cmd == "media_prev":
        sys_kb.tap(Key.media_previous)
    elif cmd == "minimize_all":
        with sys_kb.pressed(Key.cmd):
            sys_kb.tap("d")
    elif cmd == "maximize_window":
        with sys_kb.pressed(Key.cmd):
            sys_kb.tap(Key.up)
    elif cmd == "snap_left":
        with sys_kb.pressed(Key.cmd):
            sys_kb.tap(Key.left)
    elif cmd == "snap_right":
        with sys_kb.pressed(Key.cmd):
            sys_kb.tap(Key.right)
    elif cmd == "close_window":
        with sys_kb.pressed(Key.alt):
            sys_kb.tap(Key.f4)
    elif cmd == "lock_pc":
        ctypes.windll.user32.LockWorkStation()
    elif cmd == "screenshot":
        screen = QApplication.primaryScreen()
        if screen is not None:
            signals.hide_overlay.emit()
            time.sleep(0.35)
            pix = screen.grabWindow(0)
            desktop = Path.home() / "Desktop"
            out_path = desktop / f"Jarvis_Screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            pix.save(str(out_path), "PNG")
            QApplication.clipboard().setPixmap(pix)
            print(f"[SCREENSHOT]: Zapisano {out_path}")
    sfx.play("success")

def action_hand_control(arg: str, _content: str, signals: JarvisSignals):
    mode = arg.strip().lower()
    if hand_manager is None:
        return
    if mode in ("on", "start", "true", "1", "wlacz", "włącz"):
        hand_manager.start()
        signals.action_badge_changed.emit("HAND CONTROL // ONLINE")
    else:
        hand_manager.stop()
        signals.action_badge_changed.emit("HAND CONTROL // OFFLINE")

def action_ai_speech(arg: str, _content: str, signals: JarvisSignals):
    mode = arg.strip().lower()
    if speech_manager is None:
        return
    if mode in ("on", "start", "true", "1", "wlacz", "włącz"):
        speech_manager.set_enabled(True, announce=False)
        signals.action_badge_changed.emit("AI SPEECH // ON")
    else:
        speech_manager.set_enabled(False, announce=False)
        signals.action_badge_changed.emit("AI SPEECH // OFF")

def action_vision_mode(arg: str, _content: str, signals: JarvisSignals):
    mode = arg.strip().lower()
    if controller_ref is None:
        return
    on_state = mode in ("on", "start", "true", "1", "wlacz", "włącz")
    controller_ref.set_vision_enabled(on_state)
    signals.action_badge_changed.emit(f"SCREEN VISION // {'ON' if on_state else 'OFF'}")

def action_reply(_arg: str, content: str, signals: JarvisSignals):
    reply_text = content.strip()
    signals.status_changed.emit(reply_text)
    speak_text(reply_text)

# ------------------------------------------
# DISCORD (automatyzacja aplikacji przez Quick Switcher Ctrl+K)
# ------------------------------------------
discord_kb = KeyboardController()

def _paste_text(text: str):
    pyperclip.copy(text)
    time.sleep(0.15)
    with discord_kb.pressed(Key.ctrl):
        discord_kb.tap("v")
    time.sleep(0.15)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

_user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
_user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
_user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
_user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
_user32.GetForegroundWindow.restype = ctypes.c_void_p
_user32.IsIconic.argtypes = [ctypes.c_void_p]
_user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
_user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
_user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
_user32.EnumWindows.argtypes = [_EnumWindowsProc, ctypes.c_void_p]
_kernel32.OpenProcess.restype = ctypes.c_void_p
_kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
_kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
_kernel32.QueryFullProcessImageNameW.argtypes = [
    ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)
]

DISCORD_EXES = ("discord.exe", "discordptb.exe", "discordcanary.exe")

def _window_exe(hwnd) -> str:
    pid = ctypes.c_ulong(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = _kernel32.OpenProcess(0x1000, False, pid.value)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(1024)
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        _kernel32.CloseHandle(handle)

def _find_discord_window():
    found = []
    def _cb(hwnd, _lparam):
        if _user32.IsWindowVisible(hwnd):
            length = _user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                _user32.GetWindowTextW(hwnd, buf, length + 1)
                if "updater" not in buf.value.lower() and _window_exe(hwnd) in DISCORD_EXES:
                    found.append(hwnd)
        return True
    _user32.EnumWindows(_EnumWindowsProc(_cb), 0)
    return found[0] if found else None

def _discord_is_foreground() -> bool:
    hwnd = _user32.GetForegroundWindow()
    return bool(hwnd) and _window_exe(hwnd) in DISCORD_EXES

def _focus_window(hwnd) -> bool:
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, 9)
    for _ in range(3):
        _user32.SetForegroundWindow(hwnd)
        _user32.BringWindowToTop(hwnd)
        time.sleep(0.3)
        if _discord_is_foreground():
            return True
        discord_kb.press(Key.alt)
        discord_kb.release(Key.alt)
    return _discord_is_foreground()

def _wait_for_discord_window(timeout: float):
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = _find_discord_window()
        if hwnd:
            return hwnd
        time.sleep(0.5)
    return None

def _ensure_discord_focused() -> bool:
    hwnd = _find_discord_window()
    fresh_start = False

    if not hwnd:
        fresh_start = True
        try:
            os.startfile("discord://-/channels/@me")
        except OSError:
            pass
        hwnd = _wait_for_discord_window(10.0)

    if not hwnd:
        local = os.environ.get("LOCALAPPDATA", "")
        for folder, exe in (("Discord", "Discord.exe"), ("DiscordPTB", "DiscordPTB.exe"), ("DiscordCanary", "DiscordCanary.exe")):
            update_exe = Path(local) / folder / "Update.exe"
            if update_exe.exists():
                subprocess.Popen([str(update_exe), "--processStart", exe])
                hwnd = _wait_for_discord_window(DISCORD_LAUNCH_TIMEOUT)
                if hwnd:
                    break

    if not hwnd:
        discord_kb.tap(Key.cmd)
        time.sleep(0.8)
        _paste_text("Discord")
        time.sleep(1.2)
        discord_kb.tap(Key.enter)
        hwnd = _wait_for_discord_window(DISCORD_LAUNCH_TIMEOUT)

    if not hwnd:
        return False

    if fresh_start:
        time.sleep(DISCORD_OPEN_DELAY)
        hwnd = _find_discord_window() or hwnd
    return _focus_window(hwnd)

def _normalize_name(text: str) -> str:
    text = text.replace("ł", "l").replace("Ł", "L")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", text.lower())

def _resolve_discord_recipient(spoken: str) -> str:
    name = spoken.strip().lstrip("@")
    norm = _normalize_name(name)
    if not norm:
        return name

    lookup = {_normalize_name(k): v for k, v in DISCORD_ALIASES.items()}
    for login in DISCORD_ALIASES.values():
        lookup.setdefault(_normalize_name(login), login)

    if norm in lookup:
        return lookup[norm]

    close = difflib.get_close_matches(norm, list(lookup.keys()), n=1, cutoff=DISCORD_FUZZY_CUTOFF)
    if close:
        return lookup[close[0]]
    return name

def action_discord_message(arg: str, content: str, signals: JarvisSignals):
    recipient = _resolve_discord_recipient(arg)
    message = content.strip()

    if not recipient or not message:
        signals.status_changed.emit("Discord: brak odbiorcy lub treści wiadomości.")
        speak_text("Nie podałeś odbiorcy lub treści wiadomości.", force=True)
        return

    signals.action_badge_changed.emit(f"DISCORD // @{recipient}")
    signals.hide_overlay.emit()
    time.sleep(0.5)

    try:
        old_clipboard = pyperclip.paste()
    except Exception:
        old_clipboard = ""

    try:
        if not _ensure_discord_focused():
            signals.status_changed.emit("Nie udało się otworzyć Discorda.")
            speak_text("Nie udało się otworzyć Discorda.", force=True)
            return

        with discord_kb.pressed(Key.ctrl):
            discord_kb.tap("k")
        time.sleep(0.5)
        _paste_text("@" + recipient)
        time.sleep(DISCORD_SEARCH_DELAY)
        discord_kb.tap(Key.enter)
        time.sleep(0.8)

        if not _discord_is_foreground():
            speak_text("Discord stracił fokus, nie wysłałem wiadomości.", force=True)
            return

        _paste_text(message)
        if DISCORD_AUTO_SEND:
            discord_kb.tap(Key.enter)
        sfx.play("success")
    except Exception as e:
        signals.status_changed.emit(f"Błąd Discorda: {e}")
    finally:
        time.sleep(0.3)
        try:
            pyperclip.copy(old_clipboard)
        except Exception:
            pass

ACTIONS = {
    "build_file": action_build_file,
    "clipboard": action_clipboard,
    "browser": action_browser,
    "cmd": action_cmd,
    "system_control": action_system_control,
    "hand_control": action_hand_control,
    "ai_speech": action_ai_speech,
    "vision_mode": action_vision_mode,
    "discord_message": action_discord_message,
    "reply": action_reply,
}

def parse_and_execute(ai_text: str, signals: JarvisSignals):
    print(f"\n--- SUROWA ODPOWIEDŹ GEMINI ---\n{ai_text}\n-------------------------------")
    pattern = r"\[ACTION:\s*(\w+)\]\s*\[ARG:\s*(.*?)\]\s*\[CONTENT_START\](.*?)\[CONTENT_END\]"
    matches = re.findall(pattern, ai_text, re.DOTALL)

    if not matches:
        fallback_msg = ai_text.strip() or "Nie rozpoznano instrukcji."
        signals.status_changed.emit(fallback_msg)
        speak_text(fallback_msg)
        return

    for action_name, arg, content in matches:
        func = ACTIONS.get(action_name.strip().lower())
        if func:
            func(arg, content, signals)

# ==========================================
# HOLOGRAFICZNA SFERA 3D Z PIERŚCIENIAMI I PLEXUSEM
# ==========================================
class JarvisOverlay(QWidget):
    def __init__(self, signals: JarvisSignals):
        super().__init__()
        self.signals = signals
        self.current_volume = 0.0
        self.smooth_volume = 0.0
        self.pulse_phase = 0.0
        self.rot_y = 0.0
        self.rot_x = 0.0
        self.ring_angle = 0.0
        self.state = "idle"
        self.status_text = ""
        self.action_badge = "STARK OS // GOTOWY"
        self.speech_enabled = True
        self.vision_enabled = SCREEN_VISION_DEFAULT
        self.eq_bars = np.zeros(36, dtype=np.float32)

        self.num_outer_points = 400
        self.num_inner_points = 110
        self.outer_points = self._create_fibonacci_sphere(self.num_outer_points)
        self.inner_points = self._create_fibonacci_sphere(self.num_inner_points) * 0.56
        self.ring1_points = self._create_ring_points(90, 1.34, tilt_x=0.55)
        self.ring2_points = self._create_ring_points(90, 1.50, tilt_x=-0.48)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.signals.volume_changed.connect(self.update_volume)
        self.signals.status_changed.connect(self.update_status)
        self.signals.action_badge_changed.connect(self.update_badge)
        self.signals.state_changed.connect(self.update_state)
        self.signals.speech_mode_changed.connect(self.update_speech_mode)
        self.signals.vision_mode_changed.connect(self.update_vision_mode)
        self.signals.show_overlay.connect(self.activate_overlay)
        self.signals.hide_overlay.connect(self.close_overlay)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(16)

    @staticmethod
    def _create_fibonacci_sphere(samples: int) -> np.ndarray:
        idx = np.arange(samples, dtype=np.float32)
        phi = np.pi * (3.0 - np.sqrt(5.0))
        y = 1.0 - (idx / float(samples - 1)) * 2.0
        radius = np.sqrt(np.maximum(0.0, 1.0 - y * y))
        theta = phi * idx
        x = np.cos(theta) * radius
        z = np.sin(theta) * radius
        return np.stack([x, y, z], axis=1)

    @staticmethod
    def _create_ring_points(samples: int, radius_mult: float, tilt_x: float) -> np.ndarray:
        angles = np.linspace(0, 2 * np.pi, samples, endpoint=False, dtype=np.float32)
        x = np.cos(angles) * radius_mult
        z = np.sin(angles) * radius_mult
        y = np.sin(angles) * (radius_mult * math.sin(tilt_x))
        return np.stack([x, y, z], axis=1)

    def activate_overlay(self):
        self.action_badge = "NASŁUCHIWANIE AKTYWNE" + ("  |  VISION: ON" if self.vision_enabled else "")
        self.status_text = "Słucham... Mów polecenie\n(Wyśle się automatycznie po ciszy  |  [ENTER] wyślij teraz  |  [ESC] anuluj)"
        self.state = "listening"
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.grabKeyboard()

    def close_overlay(self):
        self.releaseKeyboard()
        self.hide()

    def update_volume(self, vol: float):
        self.current_volume = vol

    def update_status(self, text: str):
        self.status_text = text
        self.update()

    def update_badge(self, badge: str):
        self.action_badge = badge
        self.update()

    def update_state(self, state: str):
        self.state = state
        self.update()

    def update_speech_mode(self, enabled: bool):
        self.speech_enabled = enabled
        self.update()

    def update_vision_mode(self, enabled: bool):
        self.vision_enabled = enabled
        self.update()

    def animate(self):
        if not self.isVisible():
            return
        self.smooth_volume += (self.current_volume - self.smooth_volume) * 0.28
        self.ring_angle += 0.022

        angles = np.linspace(0, 2 * np.pi, len(self.eq_bars), endpoint=False)
        target_eq = (
            self.smooth_volume
            * (0.5 + 0.5 * np.sin(angles * 4.0 + self.pulse_phase * 2.2))
            + 0.05 * np.cos(angles * 3.0 - self.pulse_phase)
        )
        self.eq_bars += (np.clip(target_eq, 0.02, 1.0) - self.eq_bars) * 0.35

        if self.state == "thinking":
            self.pulse_phase += 0.12
            self.rot_y += 0.036
            self.rot_x += 0.020
        elif self.state == "listening":
            self.pulse_phase += 0.07 + self.smooth_volume * 0.13
            self.rot_y += 0.015 + self.smooth_volume * 0.03
            self.rot_x += 0.008
        else:
            self.pulse_phase += 0.08 + self.smooth_volume * 0.10
            self.rot_y += 0.019 + self.smooth_volume * 0.02
            self.rot_x += 0.009

        self.update()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.state == "listening":
                self.signals.finish_listening.emit()
        elif event.key() == Qt.Key.Key_Escape:
            if speech_manager is not None:
                speech_manager.stop_speaking()
            self.signals.abort_listening.emit()
            self.close_overlay()

    def _project_points(self, pts: np.ndarray, cx: float, cy: float, rot_y: float, rot_x: float):
        cy_rot, sy_rot = math.cos(rot_y), math.sin(rot_y)
        cx_rot, sx_rot = math.cos(rot_x), math.sin(rot_x)

        x1 = pts[:, 0] * cy_rot + pts[:, 2] * sy_rot
        z1 = -pts[:, 0] * sy_rot + pts[:, 2] * cy_rot
        y1 = pts[:, 1]

        y2 = y1 * cx_rot - z1 * sx_rot
        z2 = y1 * sx_rot + z1 * cx_rot
        x2 = x1

        fov = 440.0
        scale = fov / np.maximum(fov - z2, 80.0)
        screen_x = cx + x2 * scale
        screen_y = cy + y2 * scale
        return screen_x, screen_y, z2

    def _draw_sphere_layer(
        self,
        painter: QPainter,
        points: np.ndarray,
        cx: float,
        cy: float,
        base_radius: float,
        wave_amp: float,
        wave_freq: float,
        rgb_front: tuple[int, int, int],
        rgb_back: tuple[int, int, int],
        dot_scale: float,
        draw_plexus: bool = False,
    ):
        px, py, pz = points[:, 0], points[:, 1], points[:, 2]
        wave = (
            np.sin(px * wave_freq + self.pulse_phase)
            * np.cos(py * wave_freq - self.pulse_phase * 0.8)
            * np.sin(pz * (wave_freq * 0.7) + self.pulse_phase * 0.6)
        )
        radii = base_radius * (1.0 + wave * wave_amp)
        pts = points * radii[:, None]

        screen_x, screen_y, z2 = self._project_points(pts, cx, cy, self.rot_y, self.rot_x)
        order = np.argsort(z2)
        max_z = max(base_radius * 1.25, 1.0)

        r_f, g_f, b_f = rgb_front
        r_b, g_b, b_b = rgb_back

        if draw_plexus:
            front_mask = z2 > (base_radius * 0.45)
            f_indices = np.where(front_mask)[0][::3]
            if len(f_indices) > 1:
                fx = screen_x[f_indices]
                fy = screen_y[f_indices]
                pen = QPen(QColor(r_f, g_f, b_f, 38), 1.0)
                painter.setPen(pen)
                for i in range(len(f_indices)):
                    for j in range(i + 1, min(i + 6, len(f_indices))):
                        dist_sq = (fx[i] - fx[j]) ** 2 + (fy[i] - fy[j]) ** 2
                        if dist_sq < 1500.0:
                            painter.drawLine(int(fx[i]), int(fy[i]), int(fx[j]), int(fy[j]))

        painter.setPen(Qt.PenStyle.NoPen)
        for idx in order:
            depth = float(np.clip((z2[idx] + max_z) / (2.0 * max_z), 0.0, 1.0))
            alpha = int(35 + 220 * (depth ** 1.4))
            r = int(r_b + (r_f - r_b) * depth)
            g = int(g_b + (g_f - g_b) * depth)
            b = int(b_b + (b_f - b_b) * depth)

            dot_r = (1.1 + 2.4 * depth) * dot_scale
            sx = screen_x[idx]
            sy = screen_y[idx]

            if depth > 0.78:
                glow_r = dot_r * 2.1
                painter.setBrush(QColor(r_f, g_f, b_f, int(alpha * 0.22)))
                painter.drawEllipse(int(sx - glow_r), int(sy - glow_r), int(glow_r * 2), int(glow_r * 2))

            painter.setBrush(QColor(r, g, b, alpha))
            painter.drawEllipse(int(sx - dot_r), int(sy - dot_r), max(2, int(dot_r * 2)), max(2, int(dot_r * 2)))

    def _draw_orbital_rings(self, painter: QPainter, cx: float, cy: float, base_radius: float, rgb_front: tuple[int, int, int]):
        r_f, g_f, b_f = rgb_front
        painter.setPen(Qt.PenStyle.NoPen)
        for ring_pts, speed_mult in ((self.ring1_points, 1.0), (self.ring2_points, -0.75)):
            pts = ring_pts * base_radius
            sx, sy, z2 = self._project_points(pts, cx, cy, self.ring_angle * speed_mult, self.rot_x * 0.5)
            max_z = max(base_radius * 1.5, 1.0)
            for i in range(len(sx)):
                depth = float(np.clip((z2[i] + max_z) / (2.0 * max_z), 0.0, 1.0))
                alpha = int(20 + 135 * depth)
                painter.setBrush(QColor(r_f, g_f, b_f, alpha))
                painter.drawEllipse(int(sx[i] - 2), int(sy[i] - 2), 4, 4)

    def _draw_audio_eq_halo(self, painter: QPainter, cx: float, cy: float, base_radius: float, rgb_front: tuple[int, int, int]):
        r_f, g_f, b_f = rgb_front
        num = len(self.eq_bars)
        inner_r = base_radius * 1.58
        painter.setPen(QPen(QColor(r_f, g_f, b_f, 120), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i, val in enumerate(self.eq_bars):
            ang = (i / float(num)) * 2.0 * math.pi + self.ring_angle * 0.3
            bar_len = 6.0 + float(val) * 45.0
            x1 = cx + math.cos(ang) * inner_r
            y1 = cy + math.sin(ang) * inner_r
            x2 = cx + math.cos(ang) * (inner_r + bar_len)
            y2 = cy + math.sin(ang) * (inner_r + bar_len)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.fillRect(self.rect(), QColor(4, 9, 18, 208))

        cx = self.width() / 2.0
        cy = self.height() / 2.0 - 20.0

        if self.state == "listening":
            base_radius = 112.0 + self.smooth_volume * 88.0
            wave_amp = 0.08 + self.smooth_volume * 0.28
            wave_freq = 3.8
            rgb_front = (110, 245, 255)
            rgb_back = (0, 90, 205)
            core_glow_color = QColor(0, 185, 255, 58)
        elif self.state == "thinking":
            base_radius = 118.0 + math.sin(self.pulse_phase * 2.0) * 14.0
            wave_amp = 0.19
            wave_freq = 5.0
            rgb_front = (225, 130, 255)
            rgb_back = (100, 20, 190)
            core_glow_color = QColor(165, 60, 255, 65)
        else:
            base_radius = 116.0 + self.smooth_volume * 60.0 + math.sin(self.pulse_phase * 1.5) * 10.0
            wave_amp = 0.12 + self.smooth_volume * 0.22
            wave_freq = 4.2
            rgb_front = (90, 255, 195)
            rgb_back = (0, 130, 95)
            core_glow_color = QColor(0, 230, 150, 58)

        glow_radius = base_radius * 1.8
        glow_grad = QRadialGradient(cx, cy, glow_radius)
        glow_grad.setColorAt(0.0, core_glow_color)
        glow_grad.setColorAt(0.55, QColor(core_glow_color.red(), core_glow_color.green(), core_glow_color.blue(), 18))
        glow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(glow_grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(cx - glow_radius), int(cy - glow_radius), int(glow_radius * 2), int(glow_radius * 2))

        self._draw_audio_eq_halo(painter, cx, cy, base_radius, rgb_front)
        self._draw_orbital_rings(painter, cx, cy, base_radius, rgb_front)

        self._draw_sphere_layer(
            painter, self.inner_points, cx, cy, base_radius,
            wave_amp * 0.6, wave_freq * 1.3, (255, 255, 255), rgb_front, 0.75, draw_plexus=False
        )
        self._draw_sphere_layer(
            painter, self.outer_points, cx, cy, base_radius,
            wave_amp, wave_freq, rgb_front, rgb_back, 1.0, draw_plexus=True
        )

        badge_w = 420
        badge_rect = QRectF(cx - badge_w / 2.0, cy + 215, badge_w, 30)
        b_path = QPainterPath()
        b_path.addRoundedRect(badge_rect, 8, 8)
        painter.fillPath(b_path, QColor(0, 190, 255, 35))
        painter.setPen(QPen(QColor(rgb_front[0], rgb_front[1], rgb_front[2], 140), 1.2))
        painter.drawPath(b_path)
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.setPen(QColor(rgb_front[0], rgb_front[1], rgb_front[2], 240))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self.action_badge)

        painter.setPen(QColor(235, 248, 255))
        painter.setFont(QFont("Segoe UI", 16, QFont.Weight.Medium))
        text_rect = self.rect().adjusted(120, int(cy + 260), -120, -90)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap,
            self.status_text,
        )

        footer_text = (
            f"AI SPEECH: {'ON' if self.speech_enabled else 'OFF'} [F11]    |    "
            f"SCREEN VISION: {'ON' if self.vision_enabled else 'OFF'} [F8]    |    "
            f"HAND CONTROL [F10]    |    HUD [F12]"
        )
        painter.setPen(QColor(130, 195, 235, 190))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        footer_rect = self.rect().adjusted(50, self.height() - 52, -50, -15)
        painter.drawText(footer_rect, Qt.AlignmentFlag.AlignCenter, footer_text)

# ==========================================
# KONTROLER JARVISA (AUDIO + SCREEN VISION + PAMIĘĆ ROZMOWY)
# ==========================================
class JarvisController:
    def __init__(self, signals: JarvisSignals):
        self.signals = signals
        self.is_running = False
        self.finish_event = threading.Event()
        self.aborted = False
        self.vision_enabled = SCREEN_VISION_DEFAULT
        self.history: deque[str] = deque(maxlen=6)
        self.client = genai.Client(api_key=GEMINI_API_KEY)

        self.signals.finish_listening.connect(self._finish)
        self.signals.abort_listening.connect(self._abort)

    def _finish(self):
        self.finish_event.set()

    def _abort(self):
        self.aborted = True
        self.finish_event.set()
        sfx.play("off")

    def set_vision_enabled(self, enabled: bool):
        self.vision_enabled = enabled
        self.signals.vision_mode_changed.emit(self.vision_enabled)
        sfx.play("success" if enabled else "off")

    def toggle_vision(self):
        self.set_vision_enabled(not self.vision_enabled)

    def _capture_screen_jpeg(self) -> bytes | None:
        if not self.vision_enabled:
            return None
        try:
            screen = QApplication.primaryScreen()
            if screen is None:
                return None
            pix = screen.grabWindow(0)
            if pix.width() > 1280:
                pix = pix.scaledToWidth(1280, Qt.TransformationMode.SmoothTransformation)
            qbuf = QBuffer()
            qbuf.open(QIODevice.OpenModeFlag.WriteOnly)
            pix.save(qbuf, "JPG", 72)
            return bytes(qbuf.data())
        except Exception as e:
            print(f"[VISION CAPTURE INFO]: {e}")
            return None

    def trigger_session(self):
        if self.is_running:
            return
        self.is_running = True
        self.aborted = False
        self.finish_event.clear()
        sfx.play("wake")
        threading.Thread(target=self._session_worker, daemon=True).start()

    def _session_worker(self):
        try:
            screenshot_bytes = self._capture_screen_jpeg()

            self.signals.show_overlay.emit()
            self.signals.state_changed.emit("listening")
            audio_bytes = self._record_until_silence()

            if self.aborted or not audio_bytes:
                self.signals.hide_overlay.emit()
                return

            sfx.play("send")
            self.signals.state_changed.emit("thinking")
            self.signals.action_badge_changed.emit("GEMINI AI // PRZETWARZANIE")
            self.signals.status_changed.emit("Analizuję polecenie w Gemini...")

            contents_list = []
            if screenshot_bytes:
                contents_list.append(types.Part.from_bytes(data=screenshot_bytes, mime_type="image/jpeg"))

            contents_list.append(types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"))

            context_prompt = "Wykonaj polecenie głosowe użytkownika i zwróć odpowiednie bloki instrukcji."
            if screenshot_bytes:
                context_prompt += (
                    " Dołączono aktualny zrzut ekranu użytkownika – użyj go, jeśli polecenie dotyczy tego, "
                    "co jest na ekranie (kod, błąd, tekst, zadanie, aplikacja)."
                )
            if self.history:
                context_prompt += "\nOstatni kontekst sesji:\n" + "\n".join(self.history)

            contents_list.append(context_prompt)

            response = self.client.models.generate_content(
                model=MODEL_NAME,
                contents=contents_list,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.1,
                ),
            )

            if self.aborted:
                self.signals.hide_overlay.emit()
                return

            ai_out = response.text or ""
            self.history.append(ai_out[:350])

            self.signals.state_changed.emit("speaking")
            parse_and_execute(ai_out, self.signals)

            if speech_manager is not None and speech_manager.enabled:
                speech_manager.wait_until_done()
                time.sleep(0.6)
            else:
                time.sleep(3.5)

            self.signals.hide_overlay.emit()

        except Exception as e:
            print(f"[BŁĄD]: {e}")
            self.signals.status_changed.emit(f"Błąd: {e}")
            time.sleep(3.0)
            self.signals.hide_overlay.emit()
        finally:
            self.is_running = False

    def _record_until_silence(self) -> bytes:
        frames = []
        session_start = time.monotonic()
        speech_started = False
        last_voice_time = session_start
        ambient_samples = []
        dynamic_threshold = SPEECH_START_RMS

        def callback(indata, _frames_count, _time_info, _status):
            nonlocal speech_started, last_voice_time, dynamic_threshold
            frames.append(indata.copy())
            rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
            norm_vol = min(rms / 3500.0, 1.0)
            self.signals.volume_changed.emit(norm_vol)

            now = time.monotonic()

            if not speech_started and (now - session_start) < 0.25:
                ambient_samples.append(rms)
                if ambient_samples:
                    avg_ambient = sum(ambient_samples) / len(ambient_samples)
                    dynamic_threshold = max(SPEECH_START_RMS, min(avg_ambient * 2.4, 1200.0))
                return

            if not speech_started:
                if rms > dynamic_threshold:
                    speech_started = True
                    last_voice_time = now
                    self.signals.status_changed.emit("Słyszę Cię... Mów dalej (wyślę automatycznie, gdy skończysz)")
            else:
                if rms > dynamic_threshold * 0.65:
                    last_voice_time = now

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=callback):
            while not self.finish_event.is_set():
                now = time.monotonic()
                if speech_started:
                    if (now - last_voice_time) >= SILENCE_DURATION_SEC:
                        break
                else:
                    if (now - session_start) >= NO_SPEECH_TIMEOUT_SEC:
                        self.aborted = True
                        break
                time.sleep(0.03)

        self.signals.volume_changed.emit(0.0)
        if self.aborted or not frames or not speech_started:
            return b""

        audio_data = np.concatenate(frames, axis=0)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_data.tobytes())
        return buf.getvalue()

# ==========================================
# CZUŁE I SZYBKIE NASŁUCHIWANIE SŁOWA "JARVIS" W TLE
# ==========================================
class WakeWordDetector:
    """
    Szybki, czuły detektor słowa kluczowego 'Jarvis' (działa na PartialResult oraz Result,
    dzięki czemu reaguje natychmiast po wypowiedzeniu słowa).
    """
    def __init__(self, controller: JarvisController):
        self.controller = controller
        self.running = True

    def _ensure_vosk_model(self) -> bool:
        if VOSK_MODEL_DIR.exists():
            return True
        zip_path = BASE_DIR / "vosk_model.zip"
        try:
            print("[WAKE WORD]: Pobieranie lekkiego modelu głosowego Vosk (~40 MB, jednorazowo)...")
            urllib.request.urlretrieve(VOSK_MODEL_URL, str(zip_path))
            print("[WAKE WORD]: Rozpakowywanie modelu Vosk...")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(BASE_DIR)
            zip_path.unlink(missing_ok=True)
            print("[WAKE WORD]: Gotowe! Możesz wywoływać asystenta mówiąc 'Jarvis'.")
            return True
        except Exception as e:
            print(f"[BŁĄD POBIERANIA MODELU VOSK]: {e}")
            return False

    def start(self):
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        if not self._ensure_vosk_model():
            return

        model = vosk.Model(str(VOSK_MODEL_DIR))
        grammar = json.dumps([
            "jarvis",
            "hey jarvis",
            "ai speech on",
            "ai speech off",
            "speech on",
            "speech off",
            "[unk]",
        ])

        while self.running:
            is_speaking = speech_manager.speaking_event.is_set() if speech_manager else False
            if self.controller.is_running or is_speaking:
                time.sleep(0.1)
                continue

            recognizer = vosk.KaldiRecognizer(model, SAMPLE_RATE, grammar)
            detected_cmd = None

            def audio_callback(indata, _frames, _time, _status):
                nonlocal detected_cmd
                speaking_now = speech_manager.speaking_event.is_set() if speech_manager else False
                if self.controller.is_running or speaking_now or detected_cmd:
                    return
                data_bytes = bytes(indata)
                if recognizer.AcceptWaveform(data_bytes):
                    res = json.loads(recognizer.Result())
                    text = res.get("text", "").lower()
                else:
                    res = json.loads(recognizer.PartialResult())
                    text = res.get("partial", "").lower()

                if "speech off" in text:
                    detected_cmd = "speech_off"
                elif "speech on" in text:
                    detected_cmd = "speech_on"
                elif "jarvis" in text:
                    detected_cmd = "jarvis"

            try:
                with sd.RawInputStream(
                    samplerate=SAMPLE_RATE,
                    blocksize=4000,
                    channels=1,
                    dtype="int16",
                    callback=audio_callback,
                ):
                    while self.running and not self.controller.is_running:
                        if speech_manager and speech_manager.speaking_event.is_set():
                            break
                        if detected_cmd == "jarvis":
                            print("\n[WAKE WORD]: Wykryto słowo 'Jarvis'!")
                            self.controller.trigger_session()
                            time.sleep(0.6)
                            break
                        elif detected_cmd == "speech_on" and speech_manager is not None:
                            speech_manager.set_enabled(True, announce=True)
                            time.sleep(0.8)
                            break
                        elif detected_cmd == "speech_off" and speech_manager is not None:
                            speech_manager.set_enabled(False, announce=False)
                            time.sleep(0.8)
                            break
                        time.sleep(0.04)
            except Exception as e:
                print(f"[WAKE WORD STREAM INFO]: {e}")
                time.sleep(1.0)

# ==========================================
# URUCHOMIENIE APLIKACJI
# ==========================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    signals = JarvisSignals()

    speech_manager = SpeechManager(signals)
    hand_overlay = HandCameraOverlay(signals)
    hand_manager = HandControlManager(signals)
    mini_hud = StarkMiniHud(signals)
    overlay = JarvisOverlay(signals)
    controller = JarvisController(signals)
    controller_ref = controller

    wake_detector = WakeWordDetector(controller)
    wake_detector.start()

    hotkey_listener = keyboard.GlobalHotKeys({
        "<f8>": controller.toggle_vision,
        "<f9>": controller.trigger_session,
        "<f10>": hand_manager.toggle,
        "<f11>": speech_manager.toggle,
        "<f12>": mini_hud.toggle_hud,
    })
    hotkey_listener.start()

    print("=== J.A.R.V.I.S. STARK OS MK-II URUCHOMIONY ===")
    print("SKRÓTY KLAWISZOWE:")
    print("  [F8]  - Włącz/Wyłącz Screen Vision (Jarvis widzi Twój ekran)")
    print("  [F9]  - Wywołaj Jarvisa (lub po prostu powiedz 'JARVIS')")
    print("  [F10] - Włącz/Wyłącz Hand Control 2.0 (sterowanie kamerą)")
    print("  [F11] - Włącz/Wyłącz AI Speech (czytanie odpowiedzi)")
    print("  [F12] - Pokaż/Ukryj prawy górny panel Stark Mini-HUD")

    sys.exit(app.exec())