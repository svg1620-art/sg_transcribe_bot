import os
import logging
import tempfile
import subprocess
import math
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

SUPPORTED_EXTENSIONS = {".ogg", ".mp3", ".wav", ".m4a", ".mp4", ".webm", ".flac"}
CHUNK_MB = 20
TG_MAX_MB = 50

def get_duration(path):
    r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",path], capture_output=True, text=True)
    return float(r.stdout.strip())

def split_audio(path, chunk_sec):
    total = get_duration(path)
    chunks = []
    for i in range(math.ceil(total / chunk_sec)):
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        subprocess.run(["ffmpeg","-y","-ss",str(i*chunk_sec),"-t",str(chunk_sec),"-i",path,"-ar","16000","-ac","1","-b:a","32k",tmp.name], capture_output=True)
        chunks.append(tmp.name)
    return chunks

def transcribe_single(path):
    with open(path, "rb") as f:
        r = openai_client.audio.transcriptions.create(model="whisper-1", file=f, response_format="text")
    return r.strip() if isinstance(r, str) else r.text.strip()

def transcribe(path):
    if os.path.getsize(path) <= CHUNK_MB * 1024 * 1024:
        return transcribe_single(path), 1
    chunk_sec = (CHUNK_MB * 1024 * 1024 * 8) / (32 * 1000)
    chunks = split_audio(path, chunk_sec)
    try:
        return " ".join(transcribe_single(c) for c in chunks), len(chunks)
    finally:
        for c in chunks:
            try: os.unlink(c)
            except: pass

async def process(update, tg_file, msg):
    suffix = Path(tg_file.file_path).suffix or ".ogg"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.close()
    try:
        await tg_file.download_to_drive(tmp.name)
        size_mb = os.path.getsize(tmp.name) / (1024*1024)
        if size_mb > CHUNK_MB and msg:
            await msg.edit_text(f"✂️ Файл {size_mb:.1f} MB — нарезаю на части…")
        text, n = transcribe(tmp.name)
        if n > 1:
            text = f"[Расшифровано {n} частей]\n\n{text}"
        return text
    finally:
        os.unlink(tmp.name)

async def send_as_file(update, msg, transcript):
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as tf:
        tf.write(transcript)
        tf_path = tf.name
    try:
        await msg.delete()
        await update.message.reply_document(
            document=open(tf_path, "rb"),
            filename="transcription.txt",
            caption="📝 Расшифровка готова"
        )
    finally:
        os.unlink(tf_path)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html("👋 Привет! Отправь голосовое или аудиофайл (mp3, ogg, wav, m4a…) — расшифрую и пришлю текстовым файлом.\n\n⚡ Большие файлы нарезаются автоматически. Лимит Telegram: <b>50 MB</b>.")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Расшифровываю…")
    try:
        f = await update.message.voice.get_file()
        transcript = await process(update, f, msg)
        await send_as_file(update, msg, transcript)
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    audio = update.message.audio or update.message.document
    if not audio: return
    if update.message.document:
        ext = Path(audio.file_name or "").suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            await update.message.reply_text(f"⚠️ Формат {ext} не поддерживается.")
            return
    if audio.file_size and audio.file_size > TG_MAX_MB * 1024 * 1024:
        await update.message.reply_text(f"⚠️ Файл больше {TG_MAX_MB} MB — Telegram не пропустит.")
        return
    msg = await update.message.reply_text("🔄 Скачиваю…")
    try:
        f = await audio.get_file()
        transcript = await process(update, f, msg)
        await send_as_file(update, msg, transcript)
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

async def handle_video_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Расшифровываю кружок…")
    try:
        f = await update.message.video_note.get_file()
        transcript = await process(update, f, msg)
        await send_as_file(update, msg, transcript)
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

def main():
    logger.info("Starting polling...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.VIDEO_NOTE, handle_video_note))
    app.add_handler(MessageHandler(
        filters.Document.FileExtension("mp3")|filters.Document.FileExtension("ogg")|
        filters.Document.FileExtension("wav")|filters.Document.FileExtension("m4a")|
        filters.Document.FileExtension("flac")|filters.Document.FileExtension("mp4")|
        filters.Document.FileExtension("webm"), handle_audio))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
