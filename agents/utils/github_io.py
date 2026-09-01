import os
import json
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
ROOT = Path(__file__).parent.parent.parent
def load_yaml(path: str) -> Dict:
    full = ROOT / path
    with open(full, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)
def load_json(path: str) -> Any:
    full = ROOT / path
    with open(full, 'r', encoding='utf-8') as f:
        return json.load(f)
def save_json(path: str, data: Any) -> None:
    full = ROOT / path
    full.parent.mkdir(parents=True, exist_ok=True)
    with open(full, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
def load_policy() -> Dict:
    return load_yaml('config/autonomy_policy.yaml')
def load_books() -> List[Dict]:
    return load_json('config/books.json').get('books', [])
def load_heroes() -> List[Dict]:
    return load_json('config/heroes.json').get('heroes', [])
def load_course() -> Dict:
    with open(ROOT / 'config/course.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)
def get_env(key: str) -> Optional[str]:
    return os.getenv(key)
def today_str() -> str:
    from datetime import datetime, timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).strftime('%Y-%m-%d')
def daily_path(subdir: str, filename: str) -> Path:
    date = today_str()
    p = ROOT / 'content' / 'daily' / date / subdir
    p.mkdir(parents=True, exist_ok=True)
    return p / filename
