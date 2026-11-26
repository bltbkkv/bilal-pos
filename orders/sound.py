import os
import threading
import queue
import hashlib

import numpy as np
import sounddevice as sd
from django.conf import settings
# torch импортируется ЛЕНИВО, внутри _load_models() — см. ниже.
# Сам импорт torch + распаковка NeMo/kani-tts моделей стоит заметного
# времени, и если весь нужный звук уже лежит в дисковом кэше, эта цена
# вообще не должна платиться при каждом запуске программы.

# ВАЖНО: sound.py лежит внутри приложения orders/, а папка models/ —
# в корне проекта (рядом с manage.py). Поэтому путь считаем от
# settings.BASE_DIR, а не от os.path.dirname(__file__) — иначе получится
# несуществующий orders/models/... (как было в прошлой версии).
MODELS_DIR = os.path.join(str(settings.BASE_DIR), "models")

# Кэш готового аудио на диске: один раз посчитали фразу — при следующих
# запусках просто читаем .npy файл, а не гоняем её через модель заново.
# Это и есть главная причина долгого старта: preload_cache() раньше
# синтезировал одни и те же 82 фразы через нейросеть при КАЖДОМ запуске.
DISK_CACHE_DIR = os.path.join(str(settings.BASE_DIR), "tts_cache")
os.makedirs(DISK_CACHE_DIR, exist_ok=True)

# Полностью выключить голос (на слабой кассе он самый тяжёлый): переменная
# окружения VOICE_OFF=1. Тогда озвучка не играет и нейросеть не трогается вовсе.
VOICE_OFF = os.getenv("VOICE_OFF") == "1"

NUM_WORDS = {
    0: "ноль", 1: "один", 2: "два", 3: "три", 4: "четыре",
    5: "пять", 6: "шесть", 7: "семь", 8: "восемь", 9: "девять",
    10: "десять", 11: "одиннадцать", 12: "двенадцать",
    13: "тринадцать", 14: "четырнадцать", 15: "пятнадцать",
    16: "шестнадцать", 17: "семнадцать", 18: "восемнадцать",
    19: "девятнадцать", 20: "двадцать", 21: "двадцать один",
    22: "двадцать два", 23: "двадцать три", 24: "двадцать четыре",
    25: "двадцать пять", 26: "двадцать шесть", 27: "двадцать семь",
    28: "двадцать восемь", 29: "двадцать девять", 30: "тридцать",
    31: "тридцать один", 32: "тридцать два", 33: "тридцать три",
    34: "тридцать четыре", 35: "тридцать пять", 36: "тридцать шесть",
    37: "тридцать семь", 38: "тридцать восемь", 39: "тридцать девять",
    40: "сорок"
}

NUM_WORDS_EN = {
    0: "zero", 1: "one", 2: "two", 3: "three", 4: "four",
    5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
    10: "ten", 11: "eleven", 12: "twelve",
    13: "thirteen", 14: "fourteen", 15: "fifteen",
    16: "sixteen", 17: "seventeen", 18: "eighteen",
    19: "nineteen", 20: "twenty", 21: "twenty one",
    22: "twenty two", 23: "twenty three", 24: "twenty four",
    25: "twenty five", 26: "twenty six", 27: "twenty seven",
    28: "twenty eight", 29: "twenty nine", 30: "thirty",
    31: "thirty one", 32: "thirty two", 33: "thirty three",
    34: "thirty four", 35: "thirty five", 36: "thirty six",
    37: "thirty seven", 38: "thirty eight", 39: "thirty nine",
    40: "forty"
}


def num_to_text(num: int) -> str:
    return NUM_WORDS.get(num, str(num))


def num_to_text_en(num: int) -> str:
    return NUM_WORDS_EN.get(num, str(num))


# ---------------------------------------------------------------------------
# Состояние моделей / кэша.
# Модели грузятся в фоновом потоке (см. _warmup_and_preload), чтобы импорт
# этого модуля (а значит и старт Django) не занимал ~2 минуты.
# ---------------------------------------------------------------------------
model_ru = None
model_en = None
_models_loaded = False
_model_lock = threading.Lock()      # torch-инференс не гарантированно потокобезопасен
_ready_event = threading.Event()    # выставляется, когда стартовый набор фраз готов к озвучке

cache = {}
_cache_lock = threading.Lock()

# Очередь фраз на озвучку. Единственный поток ниже (_player_worker)
# читает из неё и реально трогает аудио-устройство — это гарантирует,
# что sd.play()/sd.wait() НИКОГДА не вызываются параллельно из разных
# потоков. Именно параллельный доступ к аудио-устройству и/или к модели
# ронял программу при быстрых повторных нажатиях кнопки вызова.
_play_queue = queue.Queue()
_MAX_QUEUE_SIZE = 3  # не даём очереди раздуваться, если кнопку долбят


def _load_models():
    """Импортирует torch и распаковывает модели. Тяжёлая операция —
    вызывается только когда реально нужен синтез новой, ещё не
    закэшированной фразы (на диске её тоже нет)."""
    global model_ru, model_en, _models_loaded
    if _models_loaded:
        return
    with _model_lock:
        if _models_loaded:  # повторная проверка внутри лока
            return
        import torch  # ленивый импорт — не платим цену torch, если не нужно
        model_ru = torch.package.PackageImporter(
            os.path.join(MODELS_DIR, "v3_1_ru.pt")
        ).load_pickle("tts_models", "model")
        model_en = torch.package.PackageImporter(
            os.path.join(MODELS_DIR, "v3_en.pt")
        ).load_pickle("tts_models", "model")
        _models_loaded = True


def _disk_cache_path(text: str) -> str:
    # md5 от текста — стабильное имя файла независимо от кириллицы/длины
    h = hashlib.md5(text.encode("utf-8")).hexdigest()
    return os.path.join(DISK_CACHE_DIR, f"{h}.npy")


def _load_from_disk(text: str):
    path = _disk_cache_path(text)
    if os.path.exists(path):
        try:
            return np.load(path)
        except Exception as e:
            print(f"[sound] Повреждённый файл кэша {path}: {e}")
    return None


def _save_to_disk(text: str, audio: np.ndarray):
    try:
        np.save(_disk_cache_path(text), audio)
    except Exception as e:
        print(f"[sound] Не удалось сохранить кэш на диск: {e}")


def _synth(text: str, lang: str) -> np.ndarray:
    _load_models()  # грузит модели только если ещё не загружены
    with _model_lock:
        if lang == "en":
            audio = model_en.apply_tts(text=text, speaker="en_0", sample_rate=24000)
        else:
            audio = model_ru.apply_tts(text=text, sample_rate=24000)
    return audio.numpy()


def _get_or_synth(text: str, lang: str) -> np.ndarray:
    # 1) память
    with _cache_lock:
        audio = cache.get(text)
    if audio is not None:
        return audio

    # 2) диск — самый частый случай при обычном запуске: фраза уже
    #    считалась в один из прошлых разов, модель вообще не нужна
    audio = _load_from_disk(text)
    if audio is not None:
        with _cache_lock:
            cache[text] = audio
        return audio

    # 3) синтез через модель — только для действительно новой фразы
    audio = _synth(text, lang)
    with _cache_lock:
        cache[text] = audio
    _save_to_disk(text, audio)
    return audio


def _get_cached(text: str):
    """Только из кэша (память → диск). Нейросеть НЕ трогает — для горячего пути
    (нажатие «Вызвать»), чтобы на слабой кассе вызов никогда не грузил torch."""
    with _cache_lock:
        audio = cache.get(text)
    if audio is not None:
        return audio
    audio = _load_from_disk(text)
    if audio is not None:
        with _cache_lock:
            cache[text] = audio
    return audio


def _player_worker():
    """Единственный поток, которому разрешено вызывать sd.play()/sd.wait()."""
    while True:
        text, lang = _play_queue.get()
        # Если запрос прилетел раньше, чем кэш прогрелся — ждём.
        _ready_event.wait()
        try:
            audio = _get_cached(text)          # только кэш — на вызове нейросеть не грузим
            if audio is None:
                continue                       # фразы нет в кэше — молча пропускаем, кассу не вешаем
            sd.play(audio, samplerate=24000)
            sd.wait()
        except Exception as e:
            print(f"[sound] Ошибка воспроизведения '{text}': {e}")
        finally:
            _play_queue.task_done()


def _enqueue(text: str, lang: str):
    if VOICE_OFF:
        return
    # Если кассир кликнул много раз подряд и очередь уже полна —
    # оставляем только самые свежие вызовы, старые не актуальны.
    if _play_queue.qsize() >= _MAX_QUEUE_SIZE:
        try:
            while True:
                _play_queue.get_nowait()
                _play_queue.task_done()
        except queue.Empty:
            pass
    _play_queue.put((text, lang))


def announce(num: int):
    """Кладёт фразу озвучки заказа (RU) в очередь. Не блокирует вызывающего."""
    text = f"Заказ {num_to_text(num)}. Пройдите на кассу!"
    _enqueue(text, "ru")


def announce_en(num: int):
    """Кладёт фразу озвучки заказа (EN) в очередь. Не блокирует вызывающего."""
    text = f"Order {num_to_text_en(num)}, please proceed to the cashier"
    _enqueue(text, "en")


def _warmup_and_preload():
    if VOICE_OFF:          # голос выключен — ничего не греем и не синтезируем
        _ready_event.set()
        return
    try:
        # Прогрев аудио-драйвера — это не torch, нужно всегда и быстро.
        sd.play(np.zeros(2400), samplerate=24000)
        sd.wait()

        # Пытаемся поднять весь стандартный набор фраз из ДИСКОВОГО кэша.
        # Если он уже есть (второй и последующие запуски) — torch вообще
        # не импортируется и не грузится, старт занимает секунды.
        missing = []
        for n in range(0, 41):
            text_ru = f"Заказ {NUM_WORDS[n]}. Пройдите на кассу!"
            text_en = f"Order {NUM_WORDS_EN[n]}, please proceed to the cashier"

            audio_ru = _load_from_disk(text_ru)
            audio_en = _load_from_disk(text_en)

            if audio_ru is not None:
                with _cache_lock:
                    cache[text_ru] = audio_ru
            else:
                missing.append((text_ru, "ru"))

            if audio_en is not None:
                with _cache_lock:
                    cache[text_en] = audio_en
            else:
                missing.append((text_en, "en"))

        if missing:
            # Что-то ещё не считалось (самый первый запуск, либо кэш
            # почистили) — вот тут действительно грузим модели и считаем.
            print(f"[sound] В кэше не хватает {len(missing)} фраз, синтезирую через модель...")
            for text, lang in missing:
                _get_or_synth(text, lang)

        print("[sound] Кэш озвучки готов")
    except Exception as e:
        print(f"[sound] Ошибка прогрева/предзагрузки: {e}")
    finally:
        # Даже если что-то пошло не так — снимаем блокировку очереди,
        # чтобы сервер не завис намертво. Ошибки будут видны в логе.
        _ready_event.set()


# Поток-плеер живёт всё время работы процесса.
threading.Thread(target=_player_worker, daemon=True, name="tts-player").start()

# Прогрев и предзагрузка кэша — в фоне. Django стартует сразу,
# не дожидаясь ~2 минут загрузки torch/NeMo моделей.
threading.Thread(target=_warmup_and_preload, daemon=True, name="tts-warmup").start()