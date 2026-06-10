@echo off
cd /d C:\Users\user\PycharmProjects\Mediar_fried_chiken
call .venv\Scripts\activate

:: Запускаем Django сервер
python manage.py runserver 0.0.0.0:8000

