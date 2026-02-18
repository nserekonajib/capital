from supabase import create_client, Client
from routes.config import Config
import time
from functools import lru_cache
import threading
import logging

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------- Global Supabase Client with Thread Safety ----------------
_supabase_client = None
_client_lock = threading.Lock()

def get_supabase_client() -> Client:
    """Singleton Supabase client with thread-safe initialization."""
    global _supabase_client
    if _supabase_client is None:
        with _client_lock:
            if _supabase_client is None:
                _supabase_client = create_client(
                    Config.SUPABASE_URL,
                    Config.SUPABASE_KEY
                )
    return _supabase_client

supabase = get_supabase_client()



# ---------------- User Management ----------------
def create_user(email: str, password: str, full_name: str) -> dict | None:
    """Create a new user securely with Supabase Auth."""
    try:
        client = get_supabase_client()
        result = client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {"full_name": full_name}
            }
        })
        logger.info(f"Created user: {email}")
        return result
    except Exception as e:
        logger.error(f"[create_user] Error creating user {email}: {e}")
        return None

def login_user(email: str, password: str) -> dict | None:
    """Login user with optimized timing logging."""
    try:
        client = get_supabase_client()
        start_time = time.time()
        result = client.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"Login attempt for {email} took {elapsed_ms:.2f}ms")
        return result
    except Exception as e:
        logger.error(f"[login_user] Error logging in {email}: {e}")
        return None

# ---------------- Password Reset ----------------
def send_reset_email(email: str) -> bool:
    """Send a password reset email. Returns True if successful."""
    try:
        client = get_supabase_client()
        client.auth.reset_password_for_email(email)
        logger.info(f"Password reset email sent to {email}")
        return True
    except Exception as e:
        logger.error(f"[send_reset_email] Error sending reset email to {email}: {e}")
        return False



