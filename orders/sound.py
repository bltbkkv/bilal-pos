import pyttsx3

def list_voices():
    """Выводит список всех доступных голосов в системе"""
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    for idx, voice in enumerate(voices):
        print(f"{idx}: {voice.id} — {voice.name}")

def generate_voice(order_id, voice_index=0):
    """Озвучивает номер заказа приятным мужским голосом (RHVoice Aleksandr)"""
    text = f" Заказ {order_id}. Готов"

    engine = pyttsx3.init()
    engine.setProperty('rate', 160)     # скорость речи
    engine.setProperty('volume', 1.0)   # громкость

    voices = engine.getProperty('voices')
    # сначала пробуем найти голос Aleksandr
    for v in voices:
        if "Anna" in v.id or "Anna" in v.name:
            engine.setProperty('voice', v.id)
            break
    else:
        # если не нашли, используем индекс (старое поведение)
        if voices and 0 <= voice_index < len(voices):
            engine.setProperty('voice', voices[voice_index].id)

    engine.say(text)
    engine.runAndWait()
    engine.stop()
