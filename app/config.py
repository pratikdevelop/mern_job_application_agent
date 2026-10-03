from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/jobs.db"
    resume_path: str = "data/resume.pdf"
    linkedin_profile_text: str = ""
    linkedin_profile_url: str = ""
    gmail_credentials_path: str = "credentials.json"
    gmail_token_path: str = "data/gmail_token.json"
    from_name: str = "Pratik Raut"
    from_email: str = "pratik.raut9115@gmail.com"
    phone: str = "+919111502449"
    github_url: str = "https://github.com/pratikdevelop"
    daily_limit: int = 15
    min_delay_seconds: int = 45
    max_delay_seconds: int = 90
    min_score: float = 60.0
    csv_files: str = "data/indore_it_jobs_mer_node_react_sept_2026.csv,data/indore_verified_mern_node_react_contacts_2026.csv"
    send_log_path: str = "data/send_log.csv"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"

    @property
    def csv_file_list(self) -> list[str]:
        return [x.strip() for x in self.csv_files.split(",") if x.strip()]


settings = Settings()
