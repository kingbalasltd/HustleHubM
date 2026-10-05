import os

import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:4b")


def ai_status():
    """Check that Ollama is running and the model is downloaded.

    Returns (ready, message) so the dashboard can tell the user
    exactly what to fix.
    """
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        response.raise_for_status()
    except requests.RequestException:
        return False, "Ollama is not running - open the Ollama app."

    names = {
        model.get("name", "")
        for model in response.json().get("models", [])
    }

    if MODEL not in names and f"{MODEL}:latest" not in names:
        return False, f"AI model missing - run: ollama pull {MODEL}"

    return True, f"Local AI ready ({MODEL})"


def ask_ai(prompt, json_mode=False, max_tokens=350):
    print("Local AI is thinking... Please wait.")

    body = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": False,
        "think": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.3
        }
    }

    # Ollama forces the reply to be valid JSON, so a small model
    # can't break the parser with ```json fences or extra chatter.
    if json_mode:
        body["format"] = "json"

    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json=body,
        timeout=(10, 600)
    )

    response.raise_for_status()

    data = response.json()
    return data["message"]["content"]
