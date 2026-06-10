import os
import threading
from playsound import playsound

# Папка, где лежат mp3 файлы
AUDIO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "audio_cache"))

# Кэш для всех аудио
audio_files = {}

# =========================
# 🔹 Предзагрузка всех 40 mp3
# =========================
def preload():
    for num in range(1, 41):
        filename = os.path.join(AUDIO_DIR, f"zakaz{num}.mp3")
        if os.path.exists(filename):
            audio_files[num] = filename
        else:
            print(f"⚠ Файл {filename} не найден")

# =========================
# 🔹 Воспроизведение по номеру
# =========================
def announce(num: int):
    def _play():
        if num not in audio_files:
            print(f"❌ Нет аудио для заказа {num}")
            return
        playsound(audio_files[num])  # синхронное воспроизведение
    # поток НЕ daemon → звук гарантированно проигрывается
    threading.Thread(target=_play).start()

# =========================
# 🔹 STARTUP
# =========================
preload()

# =========================
# 🔹 TEST
# =========================
if __name__ == "__main__":
    announce(12)  # моментально проиграет zakaz12.mp3

