"""
trusted_time.py

Источник "настоящего" времени, не зависящий от того, что вручную
накрутили в системных часах Windows на моноблоке.

Идея:
1. При старте (и затем периодически) спрашиваем реальное время у
   внешнего источника (NTP-сервер, а если недоступен — заголовок
   Date из обычного HTTPS-ответа).
2. Запоминаем это время вместе со значением time.monotonic() —
   монотонного счётчика, который отсчитывает физически прошедшее
   время и НЕ зависит от того, что кто-то передвинул системную дату.
3. "Сейчас" всегда считаем как: время_на_момент_синхронизации +
   (текущий_monotonic - monotonic_на_момент_синхронизации).

Если между синхронизациями кто-то вручную сдвинет системные часы —
это никак не повлияет на результат get_true_now_utc(), потому что
после первой успешной синхронизации мы больше не спрашиваем
wall-clock ОС для расчёта "сейчас".
"""

import time
import datetime
import threading

import pytz

BISHKEK_TZ = pytz.timezone("Asia/Bishkek")

# Насколько часто пытаемся пересинхронизироваться с внешним источником
RESYNC_INTERVAL_SECONDS = 10 * 60  # 10 минут

# Если системные часы отличаются от настоящего времени больше чем на
# столько секунд — считаем это подозрительным (для баннера-предупреждения)
DRIFT_WARNING_THRESHOLD_SECONDS = 120

_lock = threading.Lock()
_true_time_anchor_utc = None   # datetime (UTC) на момент последней успешной синхронизации
_monotonic_anchor = None       # time.monotonic() в тот же момент
_last_known_drift_seconds = None  # системные_часы - настоящее_время на момент синхронизации
_last_sync_ok = False


def _fetch_true_utc_via_ntp():
    import ntplib
    client = ntplib.NTPClient()
    # несколько серверов на выбор — если один недоступен/заблокирован, пробуем следующий
    for server in ("pool.ntp.org", "time.google.com", "time.cloudflare.com"):
        try:
            resp = client.request(server, version=3, timeout=3)
            return datetime.datetime.fromtimestamp(resp.tx_time, tz=datetime.timezone.utc)
        except Exception:
            continue
    raise RuntimeError("Ни один NTP-сервер не ответил")


def _fetch_true_utc_via_https():
    # Фолбэк на случай, если исходящий UDP/123 (NTP) заблокирован файрволом,
    # а обычный HTTPS (443) — открыт. Точность ~1 секунда, для POS достаточно.
    import urllib.request
    import email.utils

    req = urllib.request.Request("https://www.google.com", method="HEAD")
    with urllib.request.urlopen(req, timeout=3) as resp:
        date_header = resp.headers.get("Date")
    if not date_header:
        raise RuntimeError("HTTPS-ответ не содержит заголовок Date")
    dt = email.utils.parsedate_to_datetime(date_header)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def _sync_once() -> bool:
    global _true_time_anchor_utc, _monotonic_anchor, _last_known_drift_seconds, _last_sync_ok

    true_utc = None
    try:
        true_utc = _fetch_true_utc_via_ntp()
    except Exception as e_ntp:
        try:
            true_utc = _fetch_true_utc_via_https()
        except Exception as e_https:
            print(f"[trusted_time] Не удалось синхронизировать время "
                  f"(NTP: {e_ntp}; HTTPS: {e_https}). Использую системные часы.")
            with _lock:
                _last_sync_ok = False
            return False

    system_utc = datetime.datetime.now(datetime.timezone.utc)
    drift = (system_utc - true_utc).total_seconds()

    with _lock:
        _true_time_anchor_utc = true_utc
        _monotonic_anchor = time.monotonic()
        _last_known_drift_seconds = drift
        _last_sync_ok = True

    if abs(drift) > DRIFT_WARNING_THRESHOLD_SECONDS:
        print(f"[trusted_time] ВНИМАНИЕ: системные часы устройства расходятся "
              f"с настоящим временем на {drift:+.0f} сек.")
    return True


def _resync_loop():
    while True:
        _sync_once()
        time.sleep(RESYNC_INTERVAL_SECONDS)


def get_true_now_utc() -> datetime.datetime:
    """Настоящее текущее время (UTC), устойчивое к ручному изменению
    системных часов после последней успешной синхронизации.
    Если синхронизация ни разу не удавалась (нет интернета вообще) —
    честно откатывается на системные часы, чтобы касса продолжала работать."""
    with _lock:
        anchor_utc = _true_time_anchor_utc
        anchor_mono = _monotonic_anchor

    if anchor_utc is None:
        return datetime.datetime.now(datetime.timezone.utc)

    elapsed = time.monotonic() - anchor_mono
    return anchor_utc + datetime.timedelta(seconds=elapsed)


def get_bishkek_now() -> datetime.datetime:
    """То же самое, но сразу в часовом поясе Бишкека."""
    return get_true_now_utc().astimezone(BISHKEK_TZ)


def is_time_trusted() -> bool:
    """True, если хотя бы раз удалось сверить время с внешним источником."""
    with _lock:
        return _last_sync_ok


def clock_drift_seconds():
    """Разница (системные_часы - настоящее_время) на момент последней
    успешной синхронизации. None, если синхронизации ещё не было."""
    with _lock:
        return _last_known_drift_seconds


def clock_drift_warning_message():
    """Готовая строка для баннера в интерфейсе, либо None, если всё в порядке."""
    drift = clock_drift_seconds()
    if drift is None:
        return None
    if abs(drift) <= DRIFT_WARNING_THRESHOLD_SECONDS:
        return None
    direction = "вперёд" if drift > 0 else "назад"
    minutes = abs(drift) / 60
    return (f"⚠️ Системные часы этого устройства переведены {direction} "
            f"примерно на {minutes:.0f} мин. относительно настоящего времени. "
            f"Даты в новых заказах и отчётах могут быть неверными.")


# Синхронизация — сразу при импорте модуля (в фоне, чтобы не задерживать
# старт Django, как и с моделями озвучки в sound.py), и дальше периодически,
# чтобы ловить снос часов уже в процессе работы, а не только на старте.
threading.Thread(target=_resync_loop, daemon=True, name="trusted-time-sync").start()