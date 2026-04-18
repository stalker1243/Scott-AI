### Установка Whisper (ASR) на Windows

Важный момент: **`openai-whisper` требует `torch`**, а для **Python 3.13** в большинстве случаев нет готовых колёс `torch` → установка падает.

Поэтому самый надёжный путь:

## Вариант A (рекомендуется): Python 3.11 + виртуальное окружение

- **Шаг 1. Установи Python 3.11 (x64)**
  - Скачай Python **3.11.x** для Windows x64 с сайта python.org
  - Во время установки поставь галочку **“Add Python to PATH”**

- **Шаг 2. Создай venv в `backend/`**

```powershell
cd "C:\Users\SKYNET\OneDrive\Рабочий стол\neyro\backend"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

- **Шаг 3. Проверка**

```powershell
python -c "import whisper; print('Whisper OK')"
```

Если Whisper импортируется — ASR будет работать в проекте.

## Вариант B: попытка установить на Python 3.13 (обычно не работает)

```powershell
python -m pip install openai-whisper
```

Если увидишь ошибку про `torch` — переходи на Вариант A.


