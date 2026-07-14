import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# Future: for real competitor data sourcing
RAINFOREST_API_KEY = os.getenv("RAINFOREST_API_KEY", "")

# LangGraph SQLite checkpoint persistence
SQLITE_CHECKPOINT_PATH = os.getenv(
    "SQLITE_CHECKPOINT_PATH",
    str(Path(__file__).parent / "data" / "checkpoints.db"),
)
