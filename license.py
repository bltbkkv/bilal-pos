import json
import hashlib
import sys
from datetime import datetime, timedelta

PASSWORD_HASH = "6ee7d0a459fa3ed741b94033e9f6cb923bc570d63cbf3781aff8b0d1ed93e8e5"  # пример для "password"
LICENSE_FILE = "license.json"

def load_license():
    try:
        with open(LICENSE_FILE, "r") as f:
            data = json.load(f)
            return datetime.strptime(data["expiry_date"], "%Y-%m-%d")
    except (FileNotFoundError, KeyError, ValueError):
        expiry = datetime.now() + timedelta(days=365)
        save_license(expiry)
        return expiry

def save_license(expiry_date):
    with open(LICENSE_FILE, "w") as f:
        json.dump({"expiry_date": expiry_date.strftime("%Y-%m-%d")}, f)

def check_password(password: str) -> bool:
    return hashlib.sha256(password.encode()).hexdigest() == PASSWORD_HASH

def extend_license(days=365):
    new_date = datetime.now() + timedelta(days=days)
    save_license(new_date)
    print(f"✅ Лицензия продлена до {new_date.strftime('%Y-%m-%d')}")

def main():
    expiry_date = load_license()
    today = datetime.now()

    if today <= expiry_date:
        print(f"✅ Лицензия активна до {expiry_date.strftime('%Y-%m-%d')}")
    else:
        print("⛔ Срок действия программы истёк.")
        password = input("Введите пароль для продления: ")
        if check_password(password):
            extend_license(365)
            print("✅ Лицензия успешно продлена.")
        else:
            print("❌ Неверный пароль. Сервер не будет запущен.")
            sys.exit(1)  # 🔴 Жёсткая блокировка запуска

