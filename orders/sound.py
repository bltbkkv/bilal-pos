import pyttsx3

def list_voices():
    """Выводит список всех доступных голосов в системе"""
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    for idx, voice in enumerate(voices):
        print(f"{idx}: {voice.id} — {voice.name}")

def generate_voice(order_id, voice_index=0):
    """Озвучивает номер заказа приятным мужским голосом"""
    text = f" Заказ {order_id} Подойдите на кассу."

    engine = pyttsx3.init()
    engine.setProperty('rate', 220)     # скорость речи
    engine.setProperty('volume', 1.0)   # громкость

    voices = engine.getProperty('voices')
    if voices and 0 <= voice_index < len(voices):
        engine.setProperty('voice', voices[voice_index].id)

    engine.say(text)
    engine.runAndWait()
    engine.stop()

