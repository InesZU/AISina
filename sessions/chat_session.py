from datetime import datetime
from typing import List, Dict, Any

class ChatSession:
    def __init__(self, session_id: str, user_id: int, title: str, created_at: datetime, updated_at: datetime, messages: List[Dict[str, Any]] = None):
        self.session_id = session_id
        self.db_id = None
        self.user_id = user_id
        self.title = title
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.messages = messages or []  # Default to an empty list if no messages are provided

    def to_dict(self) -> Dict[str, Any]:
        return {
            'session_id': self.session_id,
            'user_id': self.user_id,
            'title': self.title,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'messages': self.messages
        }

    def add_message(self, content: str, role: str) -> None:
        message = {
            'content': content,
            'role': role,
            'timestamp': datetime.utcnow().isoformat()
        }
        self.messages.append(message)
        self.updated_at = datetime.utcnow()