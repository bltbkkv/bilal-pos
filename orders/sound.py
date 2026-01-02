import pyttsx3

def list_voices():
    """Выводит список всех доступных голосов в системе"""
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    for idx, voice in enumerate(voices):
        langs = getattr(voice, "languages", [])
        print(f"{idx}: {voice.id} — {voice.name} — langs={langs}")


def generate_voice(order):
    num = order.receipt_number or order.id
    text = f"Заказ {num}. Готов."

    engine = pyttsx3.init()
    engine.setProperty('rate', 160)
    engine.setProperty('volume', 1.0)

    # жёстко выбираем Анну
    engine.setProperty(
        'voice',
        r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\TokenEnums\RHVoice\Anna"
    )

    engine.say(text)
    engine.runAndWait()
    engine.stop()
