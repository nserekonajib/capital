from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, session
from functools import wraps
from routes.admin_utils import get_admin_client
from routes.admin_config import AdminConfig
import requests
from datetime import datetime, timedelta
import json


# -------------------- Zoom API Functions --------------------
def get_zoom_access_token():
    """Get Zoom OAuth access token"""
    try:
        url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={AdminConfig.ACCOUNT_ID}"
        auth = (AdminConfig.CLIENT_ID, AdminConfig.CLIENT_SECRET)

        response = requests.post(url, auth=auth)
        if response.status_code != 200:
            print("❌ Zoom Token Error:", response.text)
            return None

        return response.json().get("access_token")
    except Exception as e:
        print(f"❌ Zoom Token Error: {e}")
        return None

def create_zoom_meeting(access_token, topic, duration, waiting_room=True):
    """Create a Zoom meeting"""
    try:
        url = "https://api.zoom.us/v2/users/me/meetings"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # Schedule meeting 5 minutes from now
        start_time = (datetime.utcnow() + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

        meeting_details = {
            "topic": topic,
            "type": 2,  # Scheduled meeting
            "start_time": start_time,
            "duration": duration,
            "settings": {
                "host_video": True,
                "participant_video": True,
                "join_before_host": False,
                "mute_upon_entry": True,
                "waiting_room": waiting_room
            }
        }

        response = requests.post(url, headers=headers, json=meeting_details)
        if response.status_code not in [200, 201]:
            print("❌ Zoom Meeting Error:", response.text)
            return None

        return response.json()
    except Exception as e:
        print(f"❌ Zoom Meeting Creation Error: {e}")
        return None
    
def update_elapsed_classes_status():
    """Update status of classes that have elapsed to inactive"""
    try:
        client = get_admin_client()
        current_datetime = datetime.now()
        
        # Get all active classes
        res = client.from_("live_classes")\
            .select("id, scheduled_date, scheduled_time")\
            .eq("is_active", True)\
            .execute()
        
        if not res.data:
            return
        
        for class_data in res.data:
            # Combine date and time to create datetime object
            class_datetime_str = f"{class_data['scheduled_date']} {class_data['scheduled_time']}"
            class_datetime = datetime.strptime(class_datetime_str, "%Y-%m-%d %H:%M:%S")
            
            # If class time has passed, set to inactive
            if class_datetime < current_datetime:
                client.from_("live_classes")\
                    .update({"is_active": False})\
                    .eq("id", class_data['id'])\
                    .execute()
                print(f"Updated class {class_data['id']} to inactive")
                
    except Exception as e:
        print(f"Error updating elapsed classes: {e}")