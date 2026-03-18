import torch
import sounddevice as sd
import threading

# Загружаем русскую модель
model_ru = torch.package.PackageImporter("models/v3_1_ru.pt").load_pickle("tts_models", "model")

# Загружаем англоязычную модель
model_en = torch.package.PackageImporter("models/v3_en.pt").load_pickle("tts_models", "model")

# Прогрев русской модели для уменьшения задержки при первом вызове
_ = model_ru.apply_tts(text="тест", sample_rate=24000)

# Кэш для повторяющихся фраз
cache = {}

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

def announce(num: int):
    def _play():
        num_text = num_to_text(num)
        text = f"Заказ {num_text}. Пройдите на кассу!"

        if text not in cache:
            audio = model_ru.apply_tts(text=text, sample_rate=24000)
            cache[text] = audio.numpy()

        sd.play(cache[text], samplerate=24000)

    threading.Thread(target=_play, daemon=True).start()

def announce_en(num: int):
    def _play():
        num_text = num_to_text_en(num)
        text = f"Order {num_text}, Please proceed to the cashier"

        if not text.strip():
            text = "Order number"

        if text not in cache:
            try:
                audio = model_en.apply_tts(
                    text=text,
                    speaker="en_0",   # ✅ правильный голос
                    sample_rate=24000
                )
                cache[text] = audio.numpy()
            except ValueError:
                audio = model_en.apply_tts(
                    text="Order",
                    speaker="en_0",
                    sample_rate=24000
                )
                cache[text] = audio.numpy()

        sd.play(cache[text], samplerate=24000)

    threading.Thread(target=_play, daemon=True).start()

