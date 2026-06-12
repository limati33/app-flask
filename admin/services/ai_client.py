import os
import requests
from dotenv import load_dotenv
from flask import current_app

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
AI_MODEL = os.getenv("AI_MODEL", "phi3:latest")
AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() == "true"
AI_CHUNK_SIZE = int(os.getenv("AI_CHUNK_SIZE", "1"))
AI_CALL_DELAY = float(os.getenv("AI_CALL_DELAY", "0"))
AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "120"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")


def is_ollama_running() -> bool:
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def preload_model(model: str | None = None) -> bool:
    """
    Прогревает модель и оставляет её в памяти.
    Ollama поддерживает keep_alive и пустой запрос к /api/chat для preload. :contentReference[oaicite:1]{index=1}
    """
    if not AI_ENABLED or not is_ollama_running():
        return False

    payload = {
        "model": model or AI_MODEL,
        "messages": [],
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": 0,
            "num_predict": 1,
        },
    }

    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=(5, 60))
        r.raise_for_status()
        return True
    except Exception:
        return False


def chat(messages, model: str | None = None):
    if not AI_ENABLED:
        return None

    if not is_ollama_running():
        return None

    payload = {
        "model": model or AI_MODEL,
        "messages": messages,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": 0,
            "num_predict": 96,
        },
    }

    try:
        r = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=(5, AI_TIMEOUT),
        )
        r.raise_for_status()
        data = r.json()
        return data.get("message", {}).get("content")
    except requests.exceptions.ReadTimeout:
        current_app.logger.warning("Ollama timeout")
        return None
    except Exception as e:
        current_app.logger.exception("Ollama error: %s", e)
        return None