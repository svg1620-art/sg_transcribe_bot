# 🎙️ Telegram Transcription Bot

Бот для расшифровки аудио через OpenAI Whisper API.

## Поддерживаемые форматы
- 🎤 Голосовые сообщения Telegram
- 🎵 Аудиофайлы: mp3, ogg, wav, m4a, flac, webm
- 🎥 Видео-кружки (video note)
- Лимит: **25 MB** на файл (~3–4 часа записи)

---

## Установка и запуск

### 1. Получи токены

**Telegram Bot Token** — создай бота через [@BotFather](https://t.me/BotFather):
```
/newbot → придумай имя → получи токен
```

**OpenAI API Key** — на [platform.openai.com/api-keys](https://platform.openai.com/api-keys)

---

### 2. Установи зависимости

```bash
pip install -r requirements.txt
```

---

### 3. Задай переменные окружения

**Linux / macOS:**
```bash
export TELEGRAM_TOKEN="ваш_токен_от_botfather"
export OPENAI_API_KEY="sk-..."
```

**Windows (PowerShell):**
```powershell
$env:TELEGRAM_TOKEN="ваш_токен_от_botfather"
$env:OPENAI_API_KEY="sk-..."
```

Или создай файл `.env` и используй `python-dotenv` (опционально).

---

### 4. Запусти

```bash
python bot.py
```

---

## Деплой (чтобы работал постоянно)

### Вариант A: Railway.app (бесплатно, проще всего)
1. Залей папку в GitHub
2. Создай проект на [railway.app](https://railway.app)
3. Добавь переменные окружения `TELEGRAM_TOKEN` и `OPENAI_API_KEY` в настройках
4. Railway сам запустит `python bot.py`

### Вариант B: VPS (любой сервер)
```bash
# Установи зависимости
pip install -r requirements.txt

# Запусти через screen или systemd
screen -S transcribe_bot
python bot.py
# Ctrl+A, D — отсоединиться от screen
```

### Вариант C: systemd-сервис на VPS
Создай файл `/etc/systemd/system/transcribe_bot.service`:
```ini
[Unit]
Description=Telegram Transcribe Bot
After=network.target

[Service]
WorkingDirectory=/path/to/transcribe_bot
ExecStart=/usr/bin/python3 bot.py
Restart=always
Environment=TELEGRAM_TOKEN=ваш_токен
Environment=OPENAI_API_KEY=sk-...

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable transcribe_bot
systemctl start transcribe_bot
```

---

## Стоимость Whisper API

| Длительность | Цена (примерно) |
|---|---|
| 1 минута | ~$0.006 |
| 1 час | ~$0.36 |
| 10 часов | ~$3.60 |

Тарификация: $0.006 / минута аудио.
