@echo off
cd /d C:\Users\user\PycharmProjects\Mediar_fried_chiken
call .venv\Scripts\activate

:: Запускаем Chrome в режиме киоска
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk http://127.0.0.1:8000/menu/

:: Запускаем Django сервер в отдельном окне (с окружением)
start "" cmd /k "cd /d C:\Users\user\PycharmProjects\Mediar_fried_chiken && call .venv\Scripts\activate && python manage.py runserver 0.0.0.0:8000"

:: Запускаем Telegram-бота в отдельном окне (с окружением)
start "" cmd /k "cd /d C:\Users\user\PycharmProjects\Mediar_fried_chiken && call .venv\Scripts\activate && python biznesbot.py"

pause
