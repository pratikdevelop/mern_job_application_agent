from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"

    database_url: str = "sqlite:///./data/jobs.db"
    resume_path: str = "data/resume.pdf"
    linkedin_profile_text: str = ""
    linkedin_profile_url: str = ""

    gmail_credentials_path: str = "credentials.json"
    gmail_token_path: str = "data/gmail_token.json"
    from_name: str = "Pratik Raut"
    from_email: str = ""
    phone: str = ""
    github_url: str = "https://github.com/pratikdevelop"

    daily_limit: int = 15
    min_delay_seconds: int = 45
    max_delay_seconds: int = 90
    min_score: float = 70.0
    csv_files: str = (
        "data/indore_it_jobs_mer_node_react_sept_2026.csv,"
        "data/indore_verified_mern_node_react_contacts_2026.csv"
    )
    send_log_path: str = "data/send_log.csv"

    master_jobs_path: str = "data/jobs/master_jobs.csv"
    research_search_url: str = "https://html.duckduckgo.com/html/?q={query}"
    research_timeout_seconds: float = 15.0
    research_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0 Safari/537.36"
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def csv_file_list(self) -> list[str]:
        return [x.strip() for x in self.csv_files.split(",") if x.strip()]


settings = Settings()
