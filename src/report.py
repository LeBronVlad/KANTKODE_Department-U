
import json
import os
from pathlib import Path

def load_local_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        payload = json.load(f)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("results", {}).get("vacancies"), list):
            return payload["results"]["vacancies"]
        if isinstance(payload.get("vacancies"), list):
            return payload["vacancies"]
    raise ValueError("JSON должен быть списком вакансий или ответом API с results.vacancies")

def save_report(report, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
