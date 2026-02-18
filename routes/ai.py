

from flask import Blueprint, render_template, request, jsonify, session
import requests
import json
import threading
import time
import uuid
from datetime import datetime
import logging
import os
import speech_recognition as sr
from pydub import AudioSegment
import tempfile
import re
from routes.auth import login_required

ai_bp = Blueprint('ai_assistant', __name__)

# Configuration
OPENROUTER_API_KEY = "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"
YOUR_SITE_URL = "https://capitalcollege.ug"
YOUR_SITE_NAME = "Capital College Discussion Helper"

# Set up logging
logger = logging.getLogger(__name__)

class VoiceConversationManager:
    def __init__(self):
        self.active_conversations = {}
        self.lock = threading.Lock()
    
    def start_conversation(self, session_id):
        with self.lock:
            self.active_conversations[session_id] = {
                'start_time': datetime.now(),
                'connected': True,
                'messages': [],
                'call_duration': 0,
                'last_activity': datetime.now(),
                'is_processing': False,
                'pending_response': None
            }
        logger.info(f"🎯 CONVERSATION STARTED: {session_id}")
    
    def add_message(self, session_id, role, content):
        with self.lock:
            if session_id in self.active_conversations:
                self.active_conversations[session_id]['messages'].append({
                    'role': role,
                    'content': content,
                    'timestamp': datetime.now()
                })
                self.active_conversations[session_id]['last_activity'] = datetime.now()
                logger.info(f"💬 MESSAGE ADDED - {role.upper()}: {content}")
    
    def set_processing(self, session_id, processing):
        with self.lock:
            if session_id in self.active_conversations:
                self.active_conversations[session_id]['is_processing'] = processing
                status = "PROCESSING" if processing else "READY"
                logger.info(f"⚡ PROCESSING STATUS: {session_id} -> {status}")
    
    def set_pending_response(self, session_id, response):
        with self.lock:
            if session_id in self.active_conversations:
                self.active_conversations[session_id]['pending_response'] = response
                if response:
                    logger.info(f"📦 RESPONSE PENDING: {session_id} - {response[:100]}...")
    
    def get_pending_response(self, session_id):
        with self.lock:
            if session_id in self.active_conversations:
                return self.active_conversations[session_id]['pending_response']
            return None
    
    def update_duration(self, session_id, duration):
        with self.lock:
            if session_id in self.active_conversations:
                self.active_conversations[session_id]['call_duration'] = duration
    
    def end_conversation(self, session_id):
        with self.lock:
            if session_id in self.active_conversations:
                duration = self.active_conversations[session_id]['call_duration']
                logger.info(f"🛑 CONVERSATION ENDED: {session_id}, Duration: {duration}s")
                del self.active_conversations[session_id]
    
    def cleanup_inactive(self, timeout_minutes=30):
        with self.lock:
            now = datetime.now()
            inactive_sessions = []
            for session_id, data in self.active_conversations.items():
                if (now - data['last_activity']).total_seconds() > timeout_minutes * 60:
                    inactive_sessions.append(session_id)
            
            for session_id in inactive_sessions:
                del self.active_conversations[session_id]
                logger.info(f"🧹 CLEANED UP INACTIVE SESSION: {session_id}")

conversation_manager = VoiceConversationManager()

def clean_ai_response(response):
    """Clean AI response by removing markdown formatting and special characters"""
    if not response:
        return response
    
    # Remove markdown headers (###, **, etc.)
    response = re.sub(r'#+\s*', '', response)  # Remove headers
    response = re.sub(r'\*\*(.*?)\*\*', r'\1', response)  # Remove bold
    response = re.sub(r'\*(.*?)\*', r'\1', response)  # Remove italics
    response = re.sub(r'`(.*?)`', r'\1', response)  # Remove code formatting
    response = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', response)  # Remove links but keep text
    
    # Remove any remaining special formatting characters
    response = re.sub(r'[#*_~`<>]', '', response)
    
    # Clean up extra whitespace
    response = re.sub(r'\n\s*\n', '\n\n', response)  # Multiple newlines to double
    response = re.sub(r' +', ' ', response)  # Multiple spaces to single
    response = response.strip()
    
    return response

def recognize_speech_from_audio(file_path):
    """Convert speech to text using Google Speech Recognition"""
    logger.info(f"🎤 STARTING SPEECH-TO-TEXT CONVERSION: {file_path}")
    
    try:
        # Convert to proper WAV format
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
            wav_path = temp_wav.name
        
        try:
            audio = AudioSegment.from_file(file_path)
            audio = audio.set_frame_rate(16000).set_channels(1)
            audio.export(wav_path, format="wav")
            logger.info("✅ Audio converted to WAV format")
        except Exception as e:
            logger.error(f"❌ Audio conversion error: {e}")
            return f"Error converting audio: {e}"

        # Recognize speech
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            logger.info("📖 Reading audio file for recognition...")
            audio_data = recognizer.record(source)
            try:
                logger.info("🚀 Sending to Google Speech Recognition...")
                start_time = time.time()
                text = recognizer.recognize_google(audio_data)
                recognition_time = time.time() - start_time
                logger.info(f"✅ SPEECH-TO-TEXT SUCCESS: '{text}' (took {recognition_time:.2f}s)")
                return text.lower()
            except sr.UnknownValueError:
                logger.warning("❓ Google Speech Recognition could not understand audio")
                return "Could not understand audio"
            except sr.RequestError as e:
                logger.error(f"🌐 Google Speech Recognition error: {e}")
                return f"Error with speech recognition service: {e}"
                
    except Exception as e:
        logger.error(f"💥 Speech recognition failed: {e}")
        return f"Recognition error: {e}"
    finally:
        # Clean up temporary files
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"🗑️ Original audio file deleted: {file_path}")
            if os.path.exists(wav_path):
                os.remove(wav_path)
                logger.info(f"🗑️ Temporary WAV file deleted: {wav_path}")
        except Exception as e:
            logger.error(f"⚠️ Error deleting temp files: {e}")

def call_ai_assistant(session_id, user_message):
    """Threaded function to call OpenRouter API"""
    logger.info(f"🚀 AI REQUEST INITIATED: '{user_message}'")
    
    try:
        # Prepare system message with college context and response guidelines
        system_message = """You are the Capital College of Accountancy and Management Discussion Helper. 
You provide clear, professional, and helpful responses to students' questions about accounting and management.

IMPORTANT RESPONSE GUIDELINES:
1. Use plain text only - NO markdown formatting (no **bold**, *italics*, # headers, etc.)
2. Use natural, conversational language
3. Keep responses clear and concise (under 400 characters)
4. Use proper punctuation and spacing
5. Avoid special characters and symbols
6. Structure your response with clear paragraphs using line breaks
7. Speak directly to the student in a helpful tone
8. Focus on accounting, management, finance, and business topics

You help students understand accounting principles, management concepts, financial reporting, and related business topics."""

        messages = [{"role": "system", "content": system_message}]
        
        # Add conversation history
        if session_id in conversation_manager.active_conversations:
            history = conversation_manager.active_conversations[session_id]['messages']
            for msg in history[-6:]:
                messages.append({"role": msg['role'], "content": msg['content']})
        
        messages.append({"role": "user", "content": user_message})
        
        logger.info(f"📡 SENDING TO OPENROUTER: {len(messages)} messages")
        
        start_time = time.time()
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": YOUR_SITE_URL,
                "X-Title": YOUR_SITE_NAME,
            },
            data=json.dumps({
                "model": "mistralai/mistral-7b-instruct:free",
                "messages": messages,
                "stream": False,
                "max_tokens": 400,
                "temperature": 0.7
            }),
            timeout=20
        )
        
        api_time = time.time() - start_time
        logger.info(f"✅ OPENROUTER RESPONSE TIME: {api_time:.2f}s")
        
        if response.status_code == 200:
            result = response.json()
            ai_response = result['choices'][0]['message']['content'].strip()
            
            # Clean the AI response before using it
            cleaned_response = clean_ai_response(ai_response)
            logger.info(f"🤖 AI RESPONSE RECEIVED (CLEANED): {cleaned_response}")
            
            conversation_manager.add_message(session_id, 'assistant', cleaned_response)
            conversation_manager.set_pending_response(session_id, cleaned_response)
            return cleaned_response
        else:
            error_msg = "I apologize, but I'm having some technical difficulties. Please try again in a moment."
            logger.error(f"❌ OPENROUTER ERROR: Status {response.status_code}")
            conversation_manager.add_message(session_id, 'assistant', error_msg)
            conversation_manager.set_pending_response(session_id, error_msg)
            return error_msg
            
    except requests.exceptions.Timeout:
        error_msg = "I'm taking a bit longer than usual to process your request. Please bear with me for a moment."
        logger.error("⏰ OPENROUTER TIMEOUT")
        conversation_manager.add_message(session_id, 'assistant', error_msg)
        conversation_manager.set_pending_response(session_id, error_msg)
        return error_msg
    except Exception as e:
        logger.error(f"💥 AI CALL ERROR: {str(e)}")
        error_msg = "I'm experiencing some technical difficulties. Please try again shortly."
        conversation_manager.add_message(session_id, 'assistant', error_msg)
        conversation_manager.set_pending_response(session_id, error_msg)
        return error_msg

@ai_bp.route('/my-ai-assistant')
@login_required
def ai():
    session['call_id'] = str(uuid.uuid4())
    logger.info(f"🏠 AI ASSISTANT ACCESSED: {session['call_id']}")
    return render_template('ai_assistant.html')

@ai_bp.route('/start_call', methods=['POST'])
def start_call():
    call_id = session.get('call_id')
    if not call_id:
        call_id = str(uuid.uuid4())
        session['call_id'] = call_id
    
    conversation_manager.start_conversation(call_id)
    welcome_message = "Welcome to Capital College of Accountancy and Management. I'm your study assistant. Please click the record button and ask me any question about accountancy or management."
    conversation_manager.add_message(call_id, 'assistant', welcome_message)
    
    logger.info(f"📞 CALL STARTED: {call_id}")
    
    return jsonify({
        'status': 'connected',
        'call_id': call_id,
        'assistant_message': welcome_message
    })

@ai_bp.route('/upload_audio', methods=['POST'])
@login_required
def upload_audio():
    """Handle audio upload and speech recognition"""
    if 'audio_data' not in request.files:
        logger.warning("⚠️ No audio file provided in upload")
        return jsonify({"error": "No audio file provided"}), 400
    
    call_id = session.get('call_id')
    if not call_id:
        logger.warning("⚠️ No active call session")
        return jsonify({"error": "No active call session"}), 400
    
    audio_file = request.files['audio_data']
    
    # Save audio to temporary file
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
        file_path = temp_file.name
        audio_file.save(file_path)
    
    logger.info(f"🎵 Audio file received and saved: {file_path}")
    
    # Convert speech to text
    recognized_text = recognize_speech_from_audio(file_path)
    
    if recognized_text and recognized_text not in ["Could not understand audio", "Error converting audio"]:
        logger.info(f"🎤 SPEECH RECOGNIZED: '{recognized_text}'")
        
        # Add user message to conversation
        conversation_manager.add_message(call_id, 'user', recognized_text)
        conversation_manager.set_processing(call_id, True)
        conversation_manager.set_pending_response(call_id, None)
        
        # Start AI response in separate thread
        ai_thread = threading.Thread(target=call_ai_assistant, args=(call_id, recognized_text))
        ai_thread.daemon = True
        ai_thread.start()
        
        return jsonify({
            'status': 'processing',
            'recognized_text': recognized_text,
            'message': "Speech recognized successfully! Processing your question..."
        })
    else:
        logger.warning(f"❌ Speech recognition failed: {recognized_text}")
        return jsonify({
            'status': 'error',
            'recognized_text': recognized_text,
            'message': "Sorry, I couldn't understand that. Please try speaking again."
        })

@ai_bp.route('/send_message', methods=['POST'])
@login_required
def send_message():
    """Handle direct text messages"""
    call_id = session.get('call_id')
    if not call_id:
        return jsonify({"error": "No active call session"}), 400
    
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({"error": "No message provided"}), 400
    
    user_message = data['message']
    logger.info(f"💬 TEXT MESSAGE RECEIVED: '{user_message}'")
    
    # Add user message to conversation
    conversation_manager.add_message(call_id, 'user', user_message)
    conversation_manager.set_processing(call_id, True)
    conversation_manager.set_pending_response(call_id, None)
    
    # Start AI response in separate thread
    ai_thread = threading.Thread(target=call_ai_assistant, args=(call_id, user_message))
    ai_thread.daemon = True
    ai_thread.start()
    
    return jsonify({
        'status': 'processing',
        'message': "Your message is being processed..."
    })

@ai_bp.route('/get_response', methods=['POST'])
@login_required
def get_response():
    call_id = session.get('call_id')
    if not call_id:
        return jsonify({'error': 'No active call'}), 400
    
    # Check for pending response
    pending_response = conversation_manager.get_pending_response(call_id)
    if pending_response is not None:
        conversation_manager.set_pending_response(call_id, None)
        conversation_manager.set_processing(call_id, False)
        logger.info(f"📤 SENDING AI RESPONSE TO CLIENT: {pending_response}")
        return jsonify({
            'status': 'response_ready',
            'assistant_message': pending_response
        })
    
    # Check if still processing
    if call_id in conversation_manager.active_conversations:
        if conversation_manager.active_conversations[call_id]['is_processing']:
            return jsonify({'status': 'still_processing'})
    
    return jsonify({'status': 'no_new_response'})

@ai_bp.route('/end_call', methods=['POST'])
@login_required
def end_call():
    call_id = session.get('call_id')
    if call_id:
        conversation_manager.end_conversation(call_id)
        session.pop('call_id', None)
        logger.info(f"📞 CALL ENDED BY USER: {call_id}")
    
    return jsonify({'status': 'call_ended'})

@ai_bp.route('/call_status', methods=['POST'])
@login_required
def call_status():
    call_id = session.get('call_id')
    if call_id and call_id in conversation_manager.active_conversations:
        call_data = conversation_manager.active_conversations[call_id]
        duration = (datetime.now() - call_data['start_time']).total_seconds()
        conversation_manager.update_duration(call_id, duration)
        
        return jsonify({
            'connected': True,
            'duration': int(duration),
            'message_count': len(call_data['messages']),
            'is_processing': call_data['is_processing']
        })
    
    return jsonify({'connected': False})

# Cleanup thread for inactive sessions
def cleanup_worker():
    while True:
        time.sleep(300)
        try:
            conversation_manager.cleanup_inactive()
            logger.info("🧹 Cleanup cycle completed")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

cleanup_thread = threading.Thread(target=cleanup_worker)
cleanup_thread.daemon = True
cleanup_thread.start()