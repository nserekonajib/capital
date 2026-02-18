# routes/admin_utils.py

from supabase import create_client, Client
from routes.admin_config import AdminConfig
from werkzeug.security import generate_password_hash, check_password_hash
import time
from functools import lru_cache
import threading

# Global Supabase client with connection pooling
_admin_client = None
_client_lock = threading.Lock()

def get_admin_client() -> Client:
    """Get or initialize Supabase client for admin operations"""
    global _admin_client
    if _admin_client is None:
        with _client_lock:
            if _admin_client is None:
                _admin_client = create_client(
                    AdminConfig.SUPABASE_URL,
                    AdminConfig.SUPABASE_KEY
                )
    return _admin_client

# Expose supabase globally
admin_supabase = get_admin_client()

# ------------------- Admin Functions -------------------

@lru_cache(maxsize=500)
def cached_admin_lookup(email: str):
    """Cache admin lookups by email"""
    try:
        client = get_admin_client()
        res = client.from_("adminusers").select("*").eq("email", email).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None
    except Exception as e:
        print(f"Cache admin lookup error: {e}")
        return None

def create_admin(email: str, password: str, role: str = "viewer"):
    """Create a new admin with hashed password"""
    try:
        client = get_admin_client()
        hashed_pw = generate_password_hash(password)
        return client.from_("adminusers").insert({
            "email": email,
            "password_hash": hashed_pw,
            "role": role
        }).execute()
    except Exception as e:
        print(f"Error creating admin: {e}")
        return None

def get_admin_by_email(email: str):
    """Fetch an admin by email"""
    try:
        client = get_admin_client()
        res = client.from_("adminusers").select("*").eq("email", email).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None
    except Exception as e:
        print(f"Error fetching admin: {e}")
        return None

def validate_admin_login(email: str, password: str):
    """Validate admin login with hashed password check"""
    try:
        admin = get_admin_by_email(email)
        if admin and check_password_hash(admin["password_hash"], password):
            return admin
        return None
    except Exception as e:
        print(f"Error validating admin login: {e}")
        return None
