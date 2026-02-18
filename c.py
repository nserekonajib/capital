from __future__ import print_function
import os
import mimetypes
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

# Scope: read/write access to Drive files created by this app
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def authenticate():
    """Authenticate user and return credentials."""
    creds = None
    token_file = "token.json"

    # Load existing token if it exists
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    # If no (valid) creds, do OAuth login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the new token
        with open(token_file, "w") as token:
            token.write(creds.to_json())
    return creds

def upload_pdf(file_path, folder_id=None):
    """Upload a PDF to Google Drive, return shareable link."""
    creds = authenticate()
    service = build("drive", "v3", credentials=creds)

    file_metadata = {"name": os.path.basename(file_path)}
    if folder_id:  # Put inside specific folder
        file_metadata["parents"] = [folder_id]

    mime_type, _ = mimetypes.guess_type(file_path)
    media = MediaFileUpload(file_path, mimetype=mime_type)

    # Upload file
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()

    file_id = file.get("id")

    # Make file shareable (anyone with the link can view)
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"}
    ).execute()

    # Build link
    link = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
    print(file_id)
    return link

if __name__ == "__main__":
    pdf_path = "report.pdf"  # Change to your PDF path
    folder_id = None  # Replace with your Drive folder ID or None
    link = upload_pdf(pdf_path, folder_id)
    print("✅ Uploaded successfully!")
    print("🔗 Direct link:", link)
