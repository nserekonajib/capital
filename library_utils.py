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

def delete_file_from_drive(file_id):
    """Delete a file from Google Drive by file_id."""
    try:
        creds = authenticate()
        service = build("drive", "v3", credentials=creds)

        service.files().delete(fileId=file_id).execute()
        print(f"File with ID {file_id} deleted from Google Drive.")
        return True
    except Exception as e:
        print(f"Error deleting file from Google Drive: {e}")
        return False


def upload_pdf(file_path, folder_id=None):
    """Upload a PDF to Google Drive, return shareable link."""
    print(f"Starting Google Drive upload for: {file_path}")
    
    creds = authenticate()
    service = build("drive", "v3", credentials=creds)

    file_metadata = {"name": os.path.basename(file_path)}
    if folder_id:  # Put inside specific folder
        file_metadata["parents"] = [folder_id]

    mime_type, _ = mimetypes.guess_type(file_path)
    media = MediaFileUpload(file_path, mimetype=mime_type)

    # Upload file
    print("Uploading file to Google Drive...")
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id,size"
    ).execute()

    file_id = file.get("id")
    file_size = file.get("size", 0)

    print(f"File uploaded successfully. ID: {file_id}")

    # Make file shareable (anyone with the link can view)
    print("Making file publicly accessible...")
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"}
    ).execute()

    # Build link
    link = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
    
    print(f"Google Drive upload completed. File ID: {file_id}")
    
    return {
        "file_id": file_id,
        "direct_link": link,
        "file_size": int(file_size) if file_size else 0,
        "file_name": os.path.basename(file_path)
    }
    
if __name__ == "__main__":
    result = upload_pdf("report.pdf")  # replace with your PDF path
    print("Upload Result:", result)