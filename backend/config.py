from pathlib import Path
from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).parent.parent


class Settings(BaseSettings):
    # LLM
    llm_api_key: str = ""
    llm_base_url: str = "https://api.minimax.chat/v1"
    llm_model: str = "MiniMax-M2.7"

    # Web search
    tavily_api_key: str = ""

    # App
    score_threshold: int = 80
    log_level: str = "INFO"
    # Comma-separated origins allowed for CORS, e.g. https://your-app.netlify.app
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Paths
    data_dir: Path = BASE_DIR / "data"
    logs_dir: Path = BASE_DIR / "logs"
    backups_dir: Path = BASE_DIR / "backups"
    opportunities_file: Path = BASE_DIR / "data" / "opportunities.json"
    user_settings_file: Path = BASE_DIR / "data" / "user_settings.json"

    model_config = {"env_file": str(BASE_DIR / ".env"), "extra": "ignore"}


settings = Settings()
