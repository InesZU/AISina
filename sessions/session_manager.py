from datetime import datetime, timedelta
import uuid
import json
import threading
import logging
import os
from .chat_session import ChatSession
import sqlite3
from openai import OpenAI
from database import get_db, init_db, close_db, parse_timestamp
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

logger = logging.getLogger(__name__)
conn = sqlite3.connect('greenpill.db')


class SessionManager:
    def __init__(self, app=None):
        self.sessions = {}
        self.app = app
        self.db_path = 'greenpill.db'
        self.lock = threading.Lock()
        self.session_lifetime = timedelta(days=365)
        self.title_generated = False
        self.conversations_dir = 'conversations'

    def get_db(self):
        """Use the Flask app's database connection."""
        from flask import current_app
        return current_app.get_db()

    def create_session(self, user_id: int, old_session_id: str = None) -> str:
        """Create a new session and return its unique ID.
            If old_session_id is provided, save that session's messages before creating a new one.
        """
        session_id = str(uuid.uuid4())  # Generate a unique session ID
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")  # Format timestamp as string

        try:
            user_id = int(user_id)  # Convert user_id to integer
            with self.lock:
                db = get_db()
                # Insert session into the database
                db.execute(
                    '''
                    INSERT INTO chat_sessions (id, user_id, created_at, updated_at) 
                    VALUES (?, ?, ?, ?)
                    ''',
                    (session_id, user_id, now, now)  # Ensure values match schema
                )
                db.commit()

            if old_session_id:
                self.save_session_messages(old_session_id, self.get_messages(old_session_id), None)

            # Initialize an empty JSON file for session messages
            self.save_session_messages(session_id, [], None)
            return session_id
        except sqlite3.IntegrityError as e:
            logger.error(f"Integrity error while creating session: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise

    def generate_title(self, messages: list) -> str:
        """Generate a concise and relevant title for a session using AI."""
        if not messages or len(messages) < 1:
            logger.info("No messages available for title generation.")
        try:
            # Use up to the first two messages for title generation
            context = "\n".join([msg["content"] for msg in messages])
            prompt = f"""
            Based on the following conversation context, generate a short, descriptive title (3-6 words):
            {context}
            Respond ONLY with the title.
            """

            # Call OpenAI API
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": prompt}],
                max_tokens=10,
                temperature=0.5,
            )
            title = response.choices[0].message.content.strip()

            # Validate the generated title
            if not (1 <= len(title.split()) <= 6):
                logger.warning("Generated title did not meet criteria. Falling back to 'New Chat'.")
                return "New Chat"

            logger.info(f"Generated title: {title}")
            return title
        except Exception as e:
            logger.error(f"Failed to generate title: {e}")
            return "New Chat"

    def update_session_title(self, session_id: str, title: str) -> bool:
        """Update the title of a session."""
        try:
            with self.lock:
                db = get_db()
                db.execute(
                    '''
                    UPDATE chat_sessions 
                    SET title = ? 
                    WHERE id = ?
                    ''',
                    (title, session_id)
                )
                db.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to update session title: {e}")
            return False

    def get_session(self, session_id: str) -> ChatSession:
        """Retrieve session details and its messages."""
        try:
            db = get_db()
            session = db.execute(
                '''
                SELECT id, user_id, title, created_at, updated_at 
                FROM chat_sessions 
                WHERE id = ?
                ''',
                (session_id,)
            ).fetchone()

            if not session:
                return None

            # Parse timestamps
            created_at = datetime.strptime(session["created_at"], "%Y-%m-%d %H:%M:%S")
            updated_at = datetime.strptime(session["updated_at"], "%Y-%m-%d %H:%M:%S")
            messages = self.get_messages(session_id)

            # Create and return a ChatSession object
            return ChatSession(
                session_id=session["id"],
                user_id=session["user_id"],
                title=session["title"],
                created_at=created_at,
                updated_at=updated_at,
                messages=messages
            )
        except Exception as e:
            logger.error(f"Failed to retrieve session {session_id}: {e}")
            return None

    def add_message(self, session_id: str, content: str, role: str) -> bool:
        """Add a message to a session and update the title if needed."""
        try:
            session = self.get_session(session_id)
            if not session:
                return False

            # Add the new message
            message = {
                "content": content,
                "role": role,
                "timestamp": datetime.utcnow().isoformat(),
            }
            session.messages.append(message)
            session.updated_at = datetime.utcnow()

            # Update the database and JSON file
            self.save_session_messages(session_id, session.messages)

            # Generate a new title if there are at least 2 messages
            if len(session.messages) >= 2 and not getattr(session, "title_generated", False):
                session.title = self.generate_title(session.messages[:2])
                session.title_generated = True

                db = get_db()
                db.execute(
                    '''
                    UPDATE chat_sessions 
                    SET title = ?, updated_at = ? 
                    WHERE id = ?
                    ''',
                    (session.title, session.updated_at.strftime("%Y-%m-%d %H:%M:%S"), session_id)
                )
                db.commit()

            return True
        except Exception as e:
            logger.error(f"Failed to add message: {e}")
            return False

    def get_messages(self, session_id: str) -> list:
        """Retrieve all messages for a specific session."""
        try:
            json_path = os.path.join(self.conversations_dir, f"{session_id}.json")
            if os.path.exists(json_path):
                with open(json_path, "r") as f:
                    data = json.load(f)
                    return data.get("messages", [])  # Return the messages list
            return []  # Return an empty list if no messages are found
        except Exception as e:
            logger.error(f"Failed to retrieve messages for session {session_id}: {e}")
            return []  # Gracefully return an empty list on error

    def save_session_messages(self, session_id: str, messages: list, title: str = None) -> None:
        """Save messages to a session's JSON file."""
        try:
            json_path = os.path.join(self.conversations_dir, f"{session_id}.json")
            os.makedirs(self.conversations_dir, exist_ok=True)  # Ensure directory exists
            with open(json_path, "w") as f:
                json.dump({"session_id": session_id, "messages": messages}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save messages for session {session_id}: {e}")

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

            rows = cursor.fetchall()
            sessions = []
            for row in rows:
                messages = self.get_messages(row[0])
                generated_title = self.generate_title(messages)
                session = {
                    'session_id': row[0],
                    'title': generated_title,
                    'created_at': datetime.strptime(row['created_at'], '%Y-%m-%d %H:%M:%S'),
                    'updated_at': datetime.strptime(row['updated_at'], '%Y-%m-%d %H:%M:%S'),
                    'messages': messages  # Fetch messages for this session
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

    # def cleanup_expired_sessions(self):
    #     """Remove sessions older than session_lifetime."""
    #     try:
    #         with self.app.app_context():
    #             expiry_date = datetime.utcnow() - self.session_lifetime
    #             db = get_db()
    #             expired_sessions = db.execute('''
    #                    SELECT id, updated_at, title FROM chat_sessions
    #                    WHERE updated_at < ?
    #                ''', (expiry_date,)).fetchall()
    #
    #             for session in expired_sessions:
    #                 logger.info(
    #                     f"Cleaning session: {session['id']} last updated at {session['updated_at']}, Title: {session['title']}")
    #                 self.delete_session(session['id'], None)
    #
    #             logger.info(f"Cleaned up {len(expired_sessions)} sessions older than {expiry_date}")
    #     except Exception as e:
    #         logger.error(f"Failed to cleanup expired sessions: {e}")
    #
    # def _start_cleanup_thread(self):
    #     """Start a background thread for cleaning up expired sessions."""
    #
    #     def cleanup_task():
    #         while True:
    #             try:
    #                 self.cleanup_expired_sessions()
    #             except Exception as e:
    #                 logger.error(f"Error in cleanup task: {e}")
    #             finally:
    #                 threading.Event().wait(3600)  # Run cleanup every hour
    #
    #     cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
    #     cleanup_thread.start()
