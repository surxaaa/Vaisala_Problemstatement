"""Local LLM client (Ollama). No data leaves the machine."""
import json, os, urllib.request

HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
TIMEOUT = 20

def call_ollama(prompt: str, system: str) -> str:
    body = json.dumps({
        "model": MODEL, "stream": False, "format": "json",
        "options": {"temperature": 0, "seed": 0},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(f"{HOST}/api/chat", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())["message"]["content"]
