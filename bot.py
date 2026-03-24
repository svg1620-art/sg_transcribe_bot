import os
import logging
import tempfile
import subprocess
import math
logger.info("Bot script started")
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from openai import OpenAI

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Clients ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

SUPPORTED_EXTENSIONS = {".ogg", ".mp3", ".wav", ".m4a", ".mp4", ".webm", ".flac"}
CHUNK_SIZE_MB = 20
TELEGRAM_MAX_MB = 50


def get_audio_duration(file_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", file_path],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def split_audio(file_path: str, chunk_duration: float) -> list:
    total_duration = get_audio_duration(file_path)
    num_chunks = math.ceil(total_duration / chunk_duration)
    chunks = []
    for i in range(num_chunks):
        start = i * chunk_duration
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(start), "-t", str(chunk_duration),
             "-i", file_path, "-ar", "16000", "-ac", "1", "-b:a", "32k", tmp.name],
            capture_output=True,
        )
        chunks.append(tmp.name)
    return chunks


def needs_splitting(file_path: str) -> bool:
    return os.path.getsize(file_path) > CHUNK_SIZE_MB * 1024 * 1024


def transcribe_single(file_path: str) -> str:
    with open(file_path, "rb") as f:
        response = openai_client.audio.transcriptions.create(
            model="whisper-1", file=f, response_format="text",
        )
    return response.strip() if isinstance(response, str) else response.text.strip()


def transcribe_with_splitting(file_path: str):
    if not needs_splitting(file_path):
        return transcribe_single(file_path), 1
    chunk_duration = (CHUNK_SIZE_MB * 1024 * 1024 * 8) / (32 * 1000)
    chunks = split_audio(file_path, chunk_duration)
    try:
        parts = [transcribe_single(c) for c in chunks]
        return " ".join(parts), len(chunks)
    finally:
        for c in chunks:
            try:
                os.unlink(c)
            except Exception:
                pass


async def download_and_transcribe(update, tg_file, status_msg=None) -> str:
    suffix = Path(tg_file.file_path).suffix or ".ogg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
    try:
        await tg_file.download_to_drive(tmp_path)
        file_size_mb = os.path.getsize(tmp_path) / (1024 * 1024)
        if needs_splitting(tmp_path) and status_msg:
            await status_msg.edit_text(
                f"✂️ Файл большой ({file_size_mb:.1f} MB) — нарезаю на части и расшифровываю…\n"
                "Это займёт чуть больше времени."
            )
        transcript, num_chunks = transcribe_with_splitting(tmp_path)
        if num_chunks > 1:
            transcript = f"[Расшифровано {num_chunks} частей]\n\n{transcript}"
        return transcript
    finally:
        os.unlink(tmp_path)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "👋 Привет! Я бот для расшифровки аудио.\n\n"
        "Отправь мне:\n"
        "🎤 <b>Голосовое сообщение</b> — расшифрую прямо здесь\n"
        "📎 <b>Аудиофайл</b> (mp3, ogg, wav, m4a, flac…) — тоже расшифрую\n"
        "🎥 <b>Видео-кружок</b> — тоже работает\n\n"
        "⚡ Большие файлы автоматически нарезаются на части — <b>лимита по длине нет</b>.\n"
        "Лимит Telegram на загрузку файла: <b>50 MB</b>."
    )
    await update.message.reply_html(text)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.message.reply_text("🔄 Расшифровываю голосовое…")
    try:
        tg_file = await update.message.voice.get_file()
        transcript = await download_and_transcribe(update, tg_file, msg)
        await msg.edit_text(f"📝 <b>Расшифровка:</b>\n\n{transcript}", parse_mode="HTML")
    except Exception as e:
        logger.exception("Voice transcription failed")
        await msg.edit_text(f"❌ Ошибка: {e}")


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    audio = update.message.audio or update.message.document
    if audio is None:
        return
    if update.message.document:
        file_name = audio.file_name or ""
        ext = Path(file_name).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            await update.message.reply_text(
                f"⚠️ Формат <b>{ext}</b> не поддерживается.\n"
                f"Поддерживаю: {', '.join(SUPPORTED_EXTENSIONS)}",
                parse_mode="HTML",
            )
            return
    if audio.file_size and audio.file_size > TELEGRAM_MAX_MB * 1024 * 1024:
        await update.message.reply_text(
            f"⚠️ Файл слишком большой ({audio.file_size // (1024*1024)} MB).\n"
            f"Максимум через Telegram: <b>{TELEGRAM_MAX_MB} MB</b>.",
            parse_mode="HTML",
        )
        return
    msg = await update.message.reply_text("🔄 Скачиваю файл…")
    try:
        tg_file = await audio.get_file()
        transcript = await download_and_transcribe(update, tg_file, msg)
        await msg.edit_text(f"📝 <b>Расшифровка:</b>\n\n{transcript}", parse_mode="HTML")
    except Exception as e:
        logger.exception("Audio transcription failed")
        await msg.edit_text(f"❌ Ошибка: {e}")


async def handle_video_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.message.reply_text("🔄 Расшифровываю видео-кружок…")
    try:
        tg_file = await update.message.video_note.get_file()
        transcript = await download_and_transcribe(update, tg_file, msg)
        await msg.edit_text(f"📝 <b>Расшифровка:</b>\n\n{transcript}", parse_mode="HTML")
    except Exception as e:
        logger.exception("Video note transcription failed")
        await msg.edit_text(f"❌ Ошибка: {e}")


def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.VIDEO_NOTE, handle_video_note))
    app.add_handler(MessageHandler(filters.Document.MimeType("audio/mpeg"), handle_audio))
    app.add_handler(
        MessageHandler(
            filters.Document.FileExtension("ogg")
            | filters.Document.FileExtension("wav")
            | filters.Document.FileExtension("m4a")
            | filters.Document.FileExtension("flac")
            | filters.Document.FileExtension("mp3")
            | filters.Document.FileExtension("mp4")
            | filters.Document.FileExtension("webm"),
            handle_audio,
        )
    )
    logger.info("Bot started. Polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
