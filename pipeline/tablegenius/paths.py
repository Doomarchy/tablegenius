from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
LEAGUES_DIR = CONFIG_DIR / "leagues"
DATA_DIR = ROOT / "site" / "public" / "data"
CACHE_DIR = ROOT / "pipeline" / ".cache"
HISTORY_DIR = ROOT / "pipeline" / "history"
ENV_FILE = ROOT / ".env"
