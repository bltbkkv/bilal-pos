import pyttsx3

def list_voices():
    """Выводит список всех доступных голосов в системе"""
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    for idx, voice in enumerate(voices):
        langs = getattr(voice, "languages", [])
        print(f"{idx}: {voice.id} — {voice.name} — langs={langs}")

if __name__ == "__main__":
    list_voices()
