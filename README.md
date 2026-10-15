# 🤖 J.A.R.V.I.S. — Stark OS MK-II (AI Desktop Assistant & Hand Control)

Zaawansowany, głosowy i wizyjny asystent systemu Windows inspirowany systemem **J.A.R.V.I.S.** z filmów o Iron Manie. Projekt łączy multimodalny model **Google Gemini**, lokalny detektor słowa kluczowego (**Vosk Offline Wake-Word**), bezdotykowe sterowanie komputerem za pomocą kamery (**MediaPipe Hand Landmarker**) oraz holograficzny interfejs **3D Particle Sphere & Stark Mini-HUD** renderowany w 60 FPS (**PyQt6**).

---

## ✨ Główne Funkcje

### 🎙️ 1. Obsługa Głosowa (Hands-Free)
* **Aktywacja słowem „Jarvis” (Offline Wake-Word):** Ciągłe nasłuchiwanie w tle przy użyciu lekkiego silnika Vosk (nie wymaga internetu do czuwania).
* **Automatyczne wysyłanie po zakończeniu mowy (VAD):** Detekcja aktywności głosu automatycznie kończy nagrywanie i wysyła polecenie do Gemini po ~1.25 s ciszy – bez konieczności wciskania klawisza `Enter`.
* **AI Speech (ON / OFF):** Natywna synteza mowy Windows (**SAPI5 / pyttsx3**) z dynamiczną synchronizacją sfery 3D z głosem asystenta oraz możliwością natychmiastowego wyciszenia komendą głosową (`ai speech off` / `ai speech on`) lub klawiszem `[F11]`.

### 🖐️ 2. Hand Control 2.0 (Sterowanie Komputerem przez Kamerę)
* **Ghost Camera Overlay (Click-Through):** Pełnoekranowy podgląd kamery o niskim kryciu (`18%`), który przepuszcza kliknięcia myszy na wylot (`WS_EX_TRANSPARENT | WS_EX_LAYERED`), dzięki czemu widzisz dokładnie, gdzie znajdują się Twoje dłonie względem ikon i okien.
* **Adaptacyjny Filtr Kursora (1-Euro Velocity Filter):** Eliminuje drżenie dłoni przy precyzyjnym celowaniu w małe przyciski, jednocześnie zapewniając zerowe opóźnienie (0 lag) przy szybkich ruchach przez cały ekran.
* **Magnetic Pre-Pinch Lock:** Kursor automatycznie stabilizuje się w miejscu w ułamku sekundy, w którym zbliżasz palce do kliknięcia, zapobiegając zsunięciu się kursora z paska okna.

### 👁️ 3. Screen Vision (Jarvis Widzi Twój Ekran)
* Przed otwarciem nakładki Jarvis wykonuje w pamięci RAM zrzut ekranu i dołącza go do zapytania w Gemini.
* Możesz pytać o zawartość ekranu, np.: *„Jarvis, co robię źle w tym kodzie?”*, *„Rozwiąż zadanie, które mam otwarte”* lub *„Przepisz tekst z tego obrazka do schowka”*.

### 💬 4. Automatyzacja Systemu, Kodu i Discorda
* **Integracja z Discordem:** Automatyczne uruchamianie/aktywowanie okna Discorda, wyszukiwanie znajomych przez *Quick Switcher* (`Ctrl+K`) na podstawie skonfigurowanych aliasów głosowych i wysyłanie wiadomości.
* **Generowanie plików i schowek:** Tworzenie gotowych plików z kodem (`build_file`) lub bezpośrednie kopiowanie wygenerowanego kodu do schowka (`clipboard`).
* **Kontrola systemu i multimediów:** Sterowanie głośnością, przełączanie utworów (`Play/Pause/Next/Prev`), przypinanie okien do krawędzi ekranu (`Win + Left/Right`), zrzuty ekranu na Pulpit oraz wykonywanie poleceń terminala (`cmd`).

### 🌐 5. Interfejs Holograficzny 3D & Syntezator Sci-Fi
* **3D Fibonacci Particle Sphere + Plexus:** Trójwymiarowa sfera z 510 punktów z głębią ostrości (`Z-buffer`), siecią połączeń neuronowych, dwoma pierścieniami żyroskopowymi i okrągłym korektorem audio (EQ).
* **Stark Mini-HUD:** Stały, półprzezroczysty panel w prawym górnym rogu ekranu pokazujący status systemu, aktywne moduły i aktualnie wykonywany gest dłoni.
* **Proceduralne dźwięki Sci-Fi (`SoundFX`):** Dźwięki interfejsu generowane matematycznie w czasie rzeczywistym za pomocą `NumPy` (brak zewnętrznych plików `.wav`).

---

## 📦 Wymagania i Co Musi Być Pobrane

### 1. Wymagania Systemowe
* **System operacyjny:** Windows 10 lub Windows 11 (wymagane ze względu na natywne API `win32` / `user32.dll` / `SAPI5` / `CoreAudio`)
* **Python:** wersja **3.10 – 3.15** (64-bit)
* **Sprzęt:** Mikrofon oraz kamera internetowa (dla trybu Hand Control)

### 2. Biblioteki Python (pip)
Wszystkie wymagane pakiety zainstalujesz jedną komendą w terminalu:

```bash
pip install google-genai PyQt6 opencv-python mediapipe numpy sounddevice pyttsx3 pynput vosk pycaw comtypes pyperclip
```

> **Uwaga:** Biblioteki `vosk`, `pycaw`, `comtypes` oraz `pyperclip` posiadają w kodzie mechanizm auto-instalacji – jeśli o nich zapomnisz, skrypt sam doinstaluje je przy pierwszym uruchomieniu.

### 3. Modele AI (Pobierane Automatycznie!)
Nie musisz ręcznie pobierać żadnych modeli – przy pierwszym uruchomieniu skrypt **sam pobierze i wypakuje** do swojego folderu dwa pliki:
1. **`vosk-model-small-en-us-0.15`** (~40 MB) – lekki model offline do wykrywania słowa kluczowego *„Jarvis”* oraz komend *„AI speech on/off”*.
2. **`hand_landmarker.task`** (~7.5 MB) – oficjalny model Google MediaPipe do śledzenia 21 punktów każdej dłoni w 3D.

---

## 🚀 Konfiguracja i Uruchomienie

### Krok 1: Klucz API Gemini
Otwórz plik `jarvis.py` i w sekcji `# KONFIGURACJA` upewnij się, że Twój klucz API Gemini jest wpisany poprawnie (lub ustaw zmienną środowiskową `GEMINI_API_KEY`):

```python
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "TWÓJ_KLUCZ_API_GEMINI")
MODEL_NAME = "gemini-3.5-flash-lite"
```

### Krok 2: Konfiguracja kontaktów Discord (Opcjonalnie)
W słowniku `DISCORD_ALIASES` możesz dopisać ksywki swoich znajomych oraz ich dokładne nazwy użytkowników na Discordzie:

```python
DISCORD_ALIASES = {
    "maks": "deathshot",
    "piotr": "piczu",
}
```

### Krok 3: Uruchomienie
W terminalu (w folderze z projektem) wpisz:

```bash
python jarvis.py
```

---

## ⌨️ Skróty Klawiszowe

| Klawisz | Działanie |
| :--- | :--- |
| **`[F8]`** | Włącz / Wyłącz **Screen Vision** (analizę zrzutu ekranu przez Gemini) |
| **`[F9]`** | Ręczne wywołanie Jarvisa (alternatywa dla powiedzenia *„Jarvis”*) |
| **`[F10]`** | Włącz / Wyłącz **Hand Control 2.0** (sterowanie kursorem i oknami przez kamerę) |
| **`[F11]`** | Włącz / Wyłącz **AI Speech** (czytanie odpowiedzi na głos) |
| **`[F12]`** | Pokaż / Ukryj prawy górny panel **Stark Mini-HUD** |
| **`[ENTER]`** | Natychmiastowe wysłanie polecenia głosowego (bez czekania na ciszę) |
| **`[ESC]`** | Anulowanie nasłuchiwania / natychmiastowe przerwanie mowy Jarvisa |

---

## 🖐️ Ściągawka Gestów (Hand Control 2.0)

Po włączeniu trybu kamery (`[F10]` lub głosowo: *„Jarvis, odpal mode hand control”*):

### Gesty Jednej Dłoni
| Gest | Jak wykonać? | Działanie |
| :--- | :--- | :--- |
| **Swobodna dłoń** | Poruszaj dłonią przed kamerą | Płynny ruch kursora myszy z adaptacyjnym filtrem drgań |
| **Lewy Klik / Przeciąganie (Pinch)** | Złącz czubek **kciuka i palca wskazującego** (rozszerz, aby puścić) | Wciśnięcie i przytrzymanie **LPM** (przenoszenie okien, klikanie) |
| **Prawy Klik (Middle Pinch)** | Dotknij **kciukiem czubka palca środkowego** (wskazujący wyprostowany) | Pojedyncze kliknięcie **Prawym Przyciskiem Myszy (PPM)** |
| **Scroll (3 Palce)** | Wyprostuj **wskazujący, środkowy i serdeczny** (mały palec zwinięty) | Ruch dłoni w górę/dół płynnie przewija strony i kod |
| **Widok Alt+Tab (Peace Sign)** | Pokaż znak **„V”** (wskazujący i środkowy wyprostowane i **rozszerzone**) | Wciska i przytrzymuje `Alt + Tab` (podgląd otwartych okien) |
| **Wybór okna w Alt+Tab** | Będąc w `Alt+Tab`, **złącz ze sobą 2 palce** ze znaku „V” | Klika wskazane okno i puszcza klawisz `Alt` |

### Gesty Dwóch Dłoni
| Gest | Jak wykonać? | Działanie |
| :--- | :--- | :--- |
| **Suwak Głośności** | **1. dłoń** tworzy kółko **„O”** (kciuk + wskazujący), a **2. dłoń** porusza palcem wskazującym góra/dół | Płynna regulacja głośności systemowej od **0% do 100%** |
| **Play / Pause Mediów** | **1. dłoń** trzyma kółko **„O”**, a **2. dłoń** zaciska się w **pięść** | Wstrzymuje lub wznawia odtwarzanie muzyki/wideo (`Media Play/Pause`) |
| **Pokaż Pulpit (Push)** | Pokaż do kamery **2 w pełni otwarte dłonie** | Minimalizuje wszystkie otwarte okna (`Win + D`) |

---

## 🗣️ Przykładowe Komendy Głosowe

Po powiedzeniu **„Jarvis”**:
* *„Odpal mode hand control”* / *„Wyłącz hand control”*
* *„AI speech off”* / *„AI speech on”* (działa również bezpośrednio w tle bez mówienia „Jarvis”)
* *„Napisz na Discordzie do Maksa, że zaraz wchodzę na serwer”*
* *„Stwórz plik main.cpp z szybkim sortowaniem w C++”*
* *„Spójrz na mój ekran i powiedz, dlaczego ten kod zwraca błąd”* (gdy włączone jest `Screen Vision`)
* *„Skopiuj mi do schowka wzór na równanie kwadratowe w Pythonie”*
* *„Wyszukaj na YouTube muzykę do programowania”*
* *„Ustaw głośność na 40 procent”* / *„Następny utwór”* / *„Zrób zrzut ekranu”*