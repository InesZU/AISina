from datetime import datetime, timedelta
import uuid
import json
import threading
import logging
import os
from typing import Dict, Any, Optional
from .chat_session import ChatSession
from flask import current_app
import sqlite3
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

logger = logging.getLogger(__name__)

def get_db():
    """Connect to the database."""
    db = sqlite3.connect('greenpill.db')
    db.row_factory = sqlite3.Row
    return db

class SessionManager:
    def __init__(self, app=None):
        self.app = app
        self.sessions = {}
        self.lock = threading.Lock()
        self.session_lifetime = timedelta(hours=24)
        if app:
            self._start_cleanup_thread()

    def create_session(self, user_id: int, title: str = "New Chat") -> str:
        """Create a new chat session."""
        try:
            session_id = str(uuid.uuid4())
            session = ChatSession(session_id, user_id, title)
            
            # Save session to database
            with self.lock:
                db = get_db()
                # Convert datetime to string for SQLite
                created_at_str = session.created_at.strftime('%Y-%m-%d %H:%M:%S')
                cursor = db.execute('''
                    INSERT INTO chat_sessions (user_id, title, created_at)
                    VALUES (?, ?, ?)
                ''', (user_id, title, created_at_str))
                # Get the auto-incremented ID
                session.db_id = cursor.lastrowid
                db.commit()
            
            # Save session to JSON file
            self._save_session_to_file(session)
            return session_id
            
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            if 'db' in locals():
                db.rollback()
            raise

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Retrieve a session by ID."""
        try:
            with open(f'conversations/{session_id}.json', 'r') as f:
                data = json.load(f)
                session = ChatSession(
                    data['session_id'],
                    data['user_id'],
                    data['title']
                )
                session.messages = data['messages']
                session.created_at = datetime.fromisoformat(data['created_at'])
                session.updated_at = datetime.fromisoformat(data['updated_at'])
                return session
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve session: {e}")
            return None

    def add_message(self, session_id: str, content: str, role: str) -> bool:
        """Add a message to a session and update title if needed."""
        try:
            session = self.get_session(session_id)
            if not session:
                return False
            
            message = {
                'content': content,
                'role': role,
                'timestamp': datetime.utcnow().isoformat()
            }
            session.messages.append(message)
            session.updated_at = datetime.utcnow()
            
            # Generate new title after first user message and bot response
            if len(session.messages) == 2:
                new_title = self.generate_title(session.messages)
                session.title = new_title
                
                # Get database ID for the session
                db = get_db()
                row = db.execute('SELECT id FROM chat_sessions WHERE created_at = ?', 
                               (session.created_at.strftime('%Y-%m-%d %H:%M:%S'),)).fetchone()
                if row:
                    db_id = row['id']
                    # Update title using database ID
                    db.execute('''
                        UPDATE chat_sessions 
                        SET title = ?, updated_at = ? 
                        WHERE id = ?
                    ''', (new_title, session.updated_at.strftime('%Y-%m-%d %H:%M:%S'), db_id))
                    db.commit()
                    
                    logger.info(f"Generated new title for session {session_id}: {new_title}")
            
            self._save_session_to_file(session)
            return True
                
        except Exception as e:
            logger.error(f"Failed to add message: {e}")
            return False

    def _save_session_to_file(self, session: ChatSession):
        """Save session data to JSON file."""
        os.makedirs('conversations', exist_ok=True)
        with open(f'conversations/{session.session_id}.json', 'w') as f:
            json.dump(session.to_dict(), f, indent=2)

    def get_user_sessions(self, user_id: int) -> list:
        """Get all sessions for a user."""
        try:
            db = get_db()
            cursor = db.execute('''
                SELECT id, user_id, title, created_at, updated_at 
                FROM chat_sessions 
                WHERE user_id = ? 
                ORDER BY created_at DESC
            ''', (user_id,))
            
            sessions = []
            for row in cursor.fetchall():
                session = {
                    'session_id': row['id'],
                    'title': row['title'] or 'Chat Session',  # Default title if None
                    'created_at': datetime.strptime(row['created_at'], '%Y-%m-%d %H:%M:%S') if row['created_at'] else datetime.utcnow(),
                    'updated_at': datetime.strptime(row['updated_at'], '%Y-%m-%d %H:%M:%S') if row['updated_at'] else datetime.utcnow()
                }
                sessions.append(session)
            
            return sessions
        except Exception as e:
            logger.error(f"Failed to retrieve user sessions: {e}")
            return []

    def delete_session(self, session_id: str, user_id: int) -> bool:
        """Delete a session and its messages."""
        try:
            with self.lock:
                db = get_db()
                # Verify the session belongs to the user
                session = db.execute('SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?', 
                                     (session_id, user_id)).fetchone()
                if session:
                    # Delete messages associated with the session
                    db.execute('DELETE FROM chat_messages WHERE session_id = ?', (session_id,))
                    # Delete the session itself
                    db.execute('DELETE FROM chat_sessions WHERE id = ?', (session_id,))
                    db.commit()
                    
                    # Remove the JSON file
                    json_file_path = f'conversations/{session_id}.json'
                    if os.path.exists(json_file_path):
                        os.remove(json_file_path)
                    
                    return True
                return False
        except Exception as e:
            logger.error(f"Failed to delete session: {e}")
            return False

    def cleanup_expired_sessions(self):
        """Remove sessions older than session_lifetime."""
        try:
            with self.app.app_context():
                expiry_date = datetime.utcnow() - self.session_lifetime
                db = get_db()
                expired_sessions = db.execute('''
                    SELECT id FROM chat_sessions 
                    WHERE updated_at < ?
                ''', (expiry_date,)).fetchall()
                
                for session in expired_sessions:
                    self.delete_session(session['id'], None)
                
                logger.info(f"Cleaned up sessions older than {expiry_date}")
        except Exception as e:
            logger.error(f"Failed to cleanup expired sessions: {e}")

    def _start_cleanup_thread(self):
        """Start a background thread for cleaning up expired sessions."""
        def cleanup_task():
            while True:
                try:
                    self.cleanup_expired_sessions()
                except Exception as e:
                    logger.error(f"Error in cleanup task: {e}")
                finally:
                    threading.Event().wait(3600)  # Run cleanup every hour
                    
        cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
        cleanup_thread.start()
        logger.info("Cleanup thread started")

    def generate_title(self, messages: list) -> str:
        """Generate a title for the chat session using AI."""
        try:
            # Format messages for better context
            formatted_messages = []
            for msg in messages[:2]:  # Only use first two messages
                formatted_messages.append({
                    "role": "user" if msg['role'] == 'user' else "assistant",
                    "content": msg['content']
                })
            
            # Add system message at the beginning
            formatted_messages.insert(0, {
                "role": "system",
                "content": "Generate a very brief, content-related title (3-6 words) for this conversation. Respond with ONLY the title, no quotes or extra text."
            })

            response = client.chat.completions.create(
                model="gpt-4-1106-preview",
                messages=formatted_messages,
                max_tokens=10,
                temperature=0.7
            )
            
            title = response.choices[0].message.content.strip()
            # Remove any quotes if present
            title = title.strip('"\'')
            return title[:50]  # Limit title length
            
        except Exception as e:
            logger.error(f"Failed to generate title: {e}")
            return "New Chat"