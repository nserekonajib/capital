# routes/admin_config.py
import os

class AdminConfig:
    # Secret key for Flask sessions (different from regular user config)
    SECRET_KEY = os.environ.get("ADMIN_SECRET_KEY", "supersecretadminkey")

    # Supabase settings (separate keys for admin, ideally service role key)
    SUPABASE_URL = os.environ.get(
        "ADMIN_SUPABASE_URL",
        "https://hfkvsqlnaipsxlmrvzvd.supabase.co"
    )

    SUPABASE_KEY = os.environ.get(
        "ADMIN_SUPABASE_KEY",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imhma3ZzcWxuYWlwc3hsbXJ2enZkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MzYzMzcwNiwiZXhwIjoyMDY5MjA5NzA2fQ.gPchvg_jY_REbFVnKhBxrCDLqt9iqJZMgQ7BLmQCTQk"
    )
    
    ACCOUNT_ID = os.environ.get("ZOOM_API_KEY", "VbWxVpddQmGoqZ8Q4oQeyQ")
    CLIENT_ID = os.environ.get("ZOOM_API_SECRET", "xw1wxLQuQRqdyZFEMOTjhg")
    CLIENT_SECRET = os.environ.get("ZOOM_ACCOUNT_ID", "uymudB54zSKgUPXZP1EG9dj5gXgw0f7J")
    
    
    