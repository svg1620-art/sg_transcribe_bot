import os
import logging
import tempfile
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def transcribe_file(file_path: str) -> str:
    """Send audio file to Whisper API and return transcript."""
    with open(file_path, "rb") as audio_file:
        response = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text",
        )
    return response.strip() if isinstance(response, str) else response.text.strip()


async def download_and_transcribe(update: Update, tg_file) -> str:
    """Download a Telegram file, transcribe it, return text."""
    suffix = Path(tg_file.file_path).suffix or ".ogg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await tg_file.download_to_drive(tmp_path)
        return await transcribe_file(tmp_path)
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "👋 Привет! Я бот для расшифровки аудио.\n\n"
        "Отправь мне:\n"
        "🎤 <b>Голосовое сообщение</b> — расшифрую прямо здесь\n"
        "📎 <b>Аудиофайл</b> (mp3, ogg, wav, m4a, flac…) — тоже расшифрую\n\n"
        "Лимит файла: <b>25 MB</b> (~3–4 часа записи)."
    )
    await update.message.reply_html(text)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Telegram voice messages."""
    msg = await update.message.reply_text("🔄 Расшифровываю голосовое…")
    try:
        tg_file = await update.message.voice.get_file()
        transcript = await download_and_transcribe(update, tg_file)
        await msg.edit_text(f"📝 <b>Расшифровка:</b>\n\n{transcript}", parse_mode="HTML")
    except Exception as e:
        logger.exception("Voice transcription failed")
        await msg.edit_text(f"❌ Ошибка: {e}")


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle audio files sent as documents or audio attachments."""
    audio = update.message.audio or update.message.document

    if audio is None:
        return

    # Check extension for documents
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

    # Check file size (25 MB Whisper limit)
    if audio.file_size and audio.file_size > 25 * 1024 * 1024:
        await update.message.reply_text(
            "⚠️ Файл слишком большой. Максимум — <b>25 MB</b>.",
            parse_mode="HTML",
        )
        return

    msg = await update.message.reply_text("🔄 Скачиваю и расшифровываю файл…")
    try:
        tg_file = await audio.get_file()
        transcript = await download_and_transcribe(update, tg_file)
        await msg.edit_text(f"📝 <b>Расшифровка:</b>\n\n{transcript}", parse_mode="HTML")
    except Exception as e:
        logger.exception("Audio transcription failed")
        await msg.edit_text(f"❌ Ошибка: {e}")


async def handle_video_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle video notes (круглые видео)."""
    msg = await update.message.reply_text("🔄 Расшифровываю видео-кружок…")
    try:
        tg_file = await update.message.video_note.get_file()
        transcript = await download_and_transcribe(update, tg_file)
        await msg.edit_text(f"📝 <b>Расшифровка:</b>\n\n{transcript}", parse_mode="HTML")
    except Exception as e:
        logger.exception("Video note transcription failed")
        await msg.edit_text(f"❌ Ошибка: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.VIDEO_NOTE, handle_video_note))
    app.add_handler(
        MessageHandler(filters.Document.MimeType("audio/mpeg"), handle_audio)
    )
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
