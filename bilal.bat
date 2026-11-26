@echo off
cd /d C:\Users\user\PycharmProjects\Mediar_fried_chiken
call .venv\Scripts\activate

:: --noreload  — один процесс вместо двух (вдвое меньше памяти, без слежки за файлами)
:: --insecure  — отдавать статику (CSS/картинки) при DEBUG=False на локальной кассе
python manage.py runserver 0.0.0.0:8000 --noreload --insecure
