import json
from dataclasses import dataclass, asdict
from pathlib import Path

CONFIG_DIR = Path.home() / '.alertas_calendario'
CONFIG_FILE = CONFIG_DIR / 'config.json'

_FIELDS = {'server_url', 'api_token', 'user_id', 'minutes_before_warning'}


@dataclass
class Config:
    server_url: str = ''
    api_token: str = ''
    user_id: str = ''
    minutes_before_warning: int = 5

    def is_configured(self) -> bool:
        return bool(self.server_url and self.api_token and self.user_id)

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls) -> 'Config':
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, encoding='utf-8') as f:
                    data = json.load(f)
                return cls(**{k: v for k, v in data.items() if k in _FIELDS})
            except Exception:
                pass
        return cls()
