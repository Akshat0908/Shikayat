from pathlib import Path
from functools import lru_cache
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    openai_api_key: SecretStr = SecretStr("")
    transcribe_model: str = "gpt-transcribe"
    model_smart: str = ""
    model_fast: str = ""
    model_rates_json: str = "{}"
    budget_usd: float = 100
    user_email: str = ""
    user_email_app_password: SecretStr = SecretStr("")
    demo_company_email: str = ""
    demo_company_app_password: SecretStr = SecretStr("")
    admin_passcode: SecretStr = SecretStr("")
    public_demo: bool = False
    grievance_followup_limit: int = 3
    nodal_followup_limit: int = 2
    min_outbound_interval_hours: float = 72
    demo_outbound_interval_seconds: float = 10
    max_outbound_per_case: int = 8
    replay_mode: bool = False
    demo_mode: bool = True
    demo_reply_delay_seconds: int = 5
    send_enabled: bool = True
    autopilot_allowlist: str = ""
    database_url: str = f"sqlite:///{ROOT / 'var' / 'shikayat.db'}"
    frontend_dist: Path = ROOT / "frontend" / "out"

@lru_cache
def get_settings() -> Settings:
    return Settings()
