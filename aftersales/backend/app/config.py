"""全局配置：从 .env 读取，判定运行模式"""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    def __init__(self):
        self.api_key: str = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
        self.openai_base_url: str = os.getenv("OPENAI_BASE_URL", "").strip() or None
        self.model: str = os.getenv("MODEL", "").strip()
        self.mock_mode: str = os.getenv("MOCK_MODE", "auto").strip().lower()
        self.db_path: Path = PROJECT_ROOT / os.getenv("DB_PATH", "data/app.db")
        self.port: int = int(os.getenv("PORT", "8000"))
        self.frontend_dir: Path = PROJECT_ROOT / "frontend"
        self.uploads_dir: Path = PROJECT_ROOT / "data" / "uploads"
        self.vision_model: str = os.getenv("VISION_MODEL", "qwen-vl-max").strip()
        # 注：qwen-vl-ocr 系列走特定任务模式会输出坐标框，通用视觉模型按指令输出纯文本更可靠
        self.ocr_model: str = os.getenv("OCR_MODEL", "qwen-vl-max").strip()
        self.auto_analyze_hours: float = float(os.getenv("AUTO_ANALYZE_HOURS", "6"))
        self.channel_api_key: str = os.getenv("CHANNEL_API_KEY", "").strip()
        if not self.model:
            self.model = "claude-opus-4-8" if self.api_key else "qwen3-max"

    @property
    def provider(self) -> str:
        """anthropic | openai | mock"""
        if self.mock_mode == "true":
            return "mock"
        if self.api_key:
            return "anthropic"
        if self.openai_api_key:
            return "openai"
        return "mock" if self.mock_mode == "auto" else "anthropic"

    @property
    def is_mock(self) -> bool:
        return self.provider == "mock"


settings = Settings()
