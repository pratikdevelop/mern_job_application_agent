from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from email.message import EmailMessage
from ..config import settings

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

def get_gmail_service():
    token = Path(settings.gmail_token_path)
    creds = None
    if token.exists():
        creds = Credentials.from_authorized_user_file(str(token), SCOPES)

    if not creds or not creds.valid:
        if not Path(settings.gmail_credentials_path).exists():
            raise FileNotFoundError("credentials.json is required for Gmail OAuth.")
        flow = InstalledAppFlow.from_client_secrets_file(
            settings.gmail_credentials_path, SCOPES
        )
        creds = flow.run_local_server(port=0)
        token.parent.mkdir(exist_ok=True)
        token.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)

def send_email(to: str, subject: str, body: str, attachment_path: str | None = None):
    service = get_gmail_service()

    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg["From"] = settings.from_name
    msg.set_content(body)

    if attachment_path:
        p = Path(attachment_path)
        data = p.read_bytes()
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=p.name)

    encoded = __import__("base64").urlsafe_b64encode(msg.as_bytes()).decode()
    result = service.users().messages().send(
        userId="me", body={"raw": encoded}
    ).execute()
    return result.get("id")
