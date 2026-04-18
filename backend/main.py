from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel
import tempfile
from pathlib import Path
from uuid import uuid4
from starlette.background import BackgroundTask

try:
    from .tts_core import get_default_engine
except ImportError:
    from tts_core import get_default_engine

app = FastAPI(title="Multilang TTS API", version="0.1.0")

tts_engine = get_default_engine()


class SynthesizeRequest(BaseModel):
    text: str
    language: str = "ru"
    speaker: str | None = None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/synthesize")
async def synthesize(req: SynthesizeRequest):
    """
    Вызов ядра TTS для генерации аудио.
    Пока вместо нейросети используется простая синусоида (заглушка),
    но интерфейс уже такой, как будет у реальной модели.
    """
    tmp_dir = Path(tempfile.gettempdir())
    out_path = tmp_dir / f"tts_output_{uuid4().hex}.wav"

    await run_in_threadpool(
        tts_engine.synthesize_to_file,
        req.text,
        req.language,
        req.speaker,
        out_path,
    )

    def _cleanup_file() -> None:
        try:
            out_path.unlink(missing_ok=True)
        except Exception:
            pass

    return FileResponse(
        path=out_path,
        media_type="audio/wav",
        filename="speech.wav",
        background=BackgroundTask(_cleanup_file),
    )


if __name__ == "__main__":
    import uvicorn

    print("🚀 Запуск сервера TTS API...")
    print("📖 Документация: http://127.0.0.1:8000/docs")
    print("❤️  Health check: http://127.0.0.1:8000/health")
    print("=" * 50)

    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
