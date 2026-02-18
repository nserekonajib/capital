import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey")
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://hfkvsqlnaipsxlmrvzvd.supabase.co")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imhma3ZzcWxuYWlwc3hsbXJ2enZkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MzYzMzcwNiwiZXhwIjoyMDY5MjA5NzA2fQ.gPchvg_jY_REbFVnKhBxrCDLqt9iqJZMgQ7BLmQCTQk")
    
    # Performance optimizations
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = True  # Use HTTPS in production
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour
    
    # Flask performance settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    JSONIFY_PRETTYPRINT_REGULAR = False  # Disable pretty JSON for performance
    
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', "dym6vdlhb")
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY', "257776185988175")
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', "pjjo4TR7bGBI2BNwreXpFQ_DoV0")
    
    # Email settings
    sender_email = os.environ.get('SENDER_EMAIL', 'nserekonajib3@gmail.com')
    sender_password = os.environ.get('SENDER_PASSWORD', 'bkri kfbo bwxj iyow')
