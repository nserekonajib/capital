from supabase import create_client, Client
from routes.config import Config
import time
import threading
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any
import json
from werkzeug.security import generate_password_hash

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------- Global Supabase Client with Performance Optimizations ----------------
_supabase_client = None
_client_lock = threading.Lock()
_db_executor = ThreadPoolExecutor(
    max_workers=50, 
    thread_name_prefix="supabase_live_"
)

def get_supabase_client() -> Client:
    """Singleton Supabase client optimized for live data queries."""
    global _supabase_client
    if _supabase_client is None:
        with _client_lock:
            if _supabase_client is None:
                _supabase_client = create_client(
                    Config.SUPABASE_URL,
                    Config.SUPABASE_KEY,
                    options={
                        "postgrest_client_timeout": 5,  # Faster timeouts for live data
                        "auto_refresh_token": True,
                        "persist_session": True,
                        "headers": {
                            "X-Client-Info": "flask-live-data",
                            "Prefer": "return=minimal"  # Reduce response size
                        }
                    }
                )
    return _supabase_client

supabase = get_supabase_client()

# ---------------- Live Data Operations (No Caching) ----------------
async def get_user_live(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Always fetch fresh user data from database - no caching.
    Uses async threading for concurrent operations.
    """
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            _db_executor, 
            _fetch_user_live, 
            user_id
        )
    except Exception as e:
        logger.error(f"[get_user_live] Error for user_id={user_id}: {e}")
        return None

def _fetch_user_live(user_id: str) -> Optional[Dict[str, Any]]:
    """Synchronous live user data fetch with performance optimizations."""
    try:
        client = get_supabase_client()
        start_time = time.time()
        
        # Minimal query - only essential fields for auth
        response = client.from_("students").select(
            "id,email,full_name,password_hash,status,cpa_level,updated_at"
        ).eq("id", user_id).limit(1).execute()
        
        query_time = (time.time() - start_time) * 1000
        if query_time > 100:  # Log slow queries
            logger.warning(f"Slow user query: {query_time:.2f}ms for user_id={user_id}")
            
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"[_fetch_user_live] Database error for user_id={user_id}: {e}")
        return None

async def get_user_by_email_live(email: str) -> Optional[Dict[str, Any]]:
    """Live user lookup by email for login operations."""
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            _db_executor,
            _fetch_user_by_email_live,
            email
        )
    except Exception as e:
        logger.error(f"[get_user_by_email_live] Error for email={email}: {e}")
        return None

def _fetch_user_by_email_live(email: str) -> Optional[Dict[str, Any]]:
    """Synchronous live user fetch by email."""
    try:
        client = get_supabase_client()
        response = client.from_("students").select(
            "id,email,full_name,password_hash,status,cpa_level"
        ).eq("email", email).limit(1).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"[_fetch_user_by_email_live] Database error for email={email}: {e}")
        return None

# ---------------- Concurrent Batch Operations ----------------
async def batch_get_users_live(user_ids: list) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Fetch multiple users concurrently with live data.
    Each user gets fresh database data.
    """
    tasks = [get_user_live(user_id) for user_id in user_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return {
        user_id: result if not isinstance(result, Exception) else None
        for user_id, result in zip(user_ids, results)
    }

# ---------------- Async User Management ----------------
async def create_user_live(email: str, password: str, full_name: str, phone_number: str, cpa_level: str) -> Optional[Dict[str, Any]]:
    """Create user with live data insertion."""
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            _db_executor,
            _create_user_sync,
            email, password, full_name, phone_number, cpa_level
        )
    except Exception as e:
        logger.error(f"[create_user_live] Error creating user {email}: {e}")
        return None

def _create_user_sync(email: str, password: str, full_name: str, phone_number: str, cpa_level: str) -> Optional[Dict[str, Any]]:
    """Synchronous user creation with live data."""
    try:
        client = get_supabase_client()
        hashed_pw = generate_password_hash(password)
        
        result = client.from_("students").insert({
            "full_name": full_name,
            "email": email,
            "password_hash": hashed_pw,
            "phone_number": phone_number,
            "cpa_level": cpa_level,
            "status": "active",
            "created_at": "now()"
        }).execute()

        logger.info(f"Created user with live data: {email}")
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"[_create_user_sync] Error creating user {email}: {e}")
        return None

# ---------------- Async Password Reset ----------------
async def send_reset_email_live(email: str) -> bool:
    """Send password reset email asynchronously."""
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            _db_executor,
            _send_reset_email_sync,
            email
        )
    except Exception as e:
        logger.error(f"[send_reset_email_live] Error for {email}: {e}")
        return False

def _send_reset_email_sync(email: str) -> bool:
    """Synchronous password reset email."""
    try:
        client = get_supabase_client()
        client.auth.reset_password_for_email(email)
        logger.info(f"Password reset email sent to {email}")
        return True
    except Exception as e:
        logger.error(f"[_send_reset_email_sync] Error for {email}: {e}")
        return False

# ---------------- Database Health Check ----------------
async def check_database_health() -> Dict[str, Any]:
    """Check database connectivity and performance."""
    loop = asyncio.get_event_loop()
    try:
        health_data = await loop.run_in_executor(_db_executor, _check_db_health_sync)
        return health_data
    except Exception as e:
        return {"status": "error", "error": str(e)}

def _check_db_health_sync() -> Dict[str, Any]:
    """Synchronous database health check."""
    try:
        client = get_supabase_client()
        start_time = time.time()
        
        # Simple query to check connectivity and speed
        response = client.from_("students").select("id", count="exact").limit(1).execute()
        
        query_time = (time.time() - start_time) * 1000
        
        return {
            "status": "healthy",
            "response_time_ms": round(query_time, 2),
            "database_connected": True,
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "status": "unhealthy", 
            "error": str(e),
            "database_connected": False,
            "timestamp": time.time()
        }

# ---------------- Resource Cleanup ----------------
def shutdown_db_executor():
    """Clean shutdown of database thread pool."""
    _db_executor.shutdown(wait=True, timeout=5.0)
    logger.info("Database executor shutdown completed")