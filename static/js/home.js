const response = await fetch('/chat_message', {  // Use the new endpoint name
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': document.querySelector('[name=csrf_token]').value
    },
    body: JSON.stringify({
        message: message,
        session_id: currentSession
    })
});

document.querySelector('.btn-primary').addEventListener('click', function(e) {
    e.preventDefault();
    document.getElementById('chat-app').style.display = 'block';
    // Initialize React chat component
    ReactDOM.render(<App />, document.getElementById('chat-app'));
});

function App() {
    const [activeTab, setActiveTab] = React.useState('chat');
    const [sessions, setSessions] = React.useState([]);
    const [currentSessionId, setCurrentSessionId] = React.useState(null);

    React.useEffect(() => {
        // Fetch previous chat sessions
        fetchSessions();
    }, []);

    const fetchSessions = async () => {
        try {
            const response = await fetch('/get_sessions');
            const data = await response.json();
            setSessions(data.sessions);
        } catch (error) {
            console.error('Error fetching sessions:', error);
        }
    };

    return (
        <div className="app-container">
            <nav className="sidebar">
                <div className="user-profile">
                    <img src="/static/images/default-avatar.png" alt="Profile" />
                    <h3>{{ username }}</h3>
                </div>
                <div className="sessions-list">
                    <h4>Previous Consultations</h4>
                    {sessions.map(session => (
                        <div 
                            key={session.id} 
                            className={`session-item ${currentSessionId === session.id ? 'active' : ''}`}
                            onClick={() => setCurrentSessionId(session.id)}
                        >
                            <div className="session-icon">🌿</div>
                            <div className="session-info">
                                <span className="session-date">{new Date(session.created_at).toLocaleDateString()}</span>
                                <span className="session-preview">{session.title || 'Consultation'}</span>
                            </div>
                        </div>
                    ))}
                </div>
                <div className="nav-links">
                    <button 
                        className={`nav-btn ${activeTab === 'chat' ? 'active' : ''}`}
                        onClick={() => setActiveTab('chat')}
                    >
                        New Consultation
                    </button>
                </div>
                <a href="{{ url_for('chat') }}" className="logout-btn">Logout</a>
            </nav>
            
            <main className="content">
                <TransitionGroup>
                    <CSSTransition
                        key={activeTab}
                        timeout={300}
                        classNames="page"
                    >
                        {activeTab === 'chat' ? (
                            <ChatComponent 
                                sessionId={currentSessionId} 
                                onNewSession={fetchSessions} 
                            />
                        ) : (
                            <OtherComponent />
                        )}
                    </CSSTransition>
                </TransitionGroup>
            </main>
        </div>
    );
}

function ChatComponent({ sessionId, onNewSession }) {
    const [messages, setMessages] = React.useState([]);
    const [newMessage, setNewMessage] = React.useState('');
    const messagesEndRef = React.useRef(null);

    React.useEffect(() => {
        if (sessionId) {
            loadSessionMessages(sessionId);
        } else {
            setMessages([]);
        }
    }, [sessionId]);

    const loadSessionMessages = async (sid) => {
        try {
            const response = await fetch(`/get_session_messages/${sid}`);
            const data = await response.json();
            setMessages(data.messages);
        } catch (error) {
            console.error('Error loading session:', error);
        }
    };

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    React.useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const sendMessage = async (e) => {
        e.preventDefault();
        if (!newMessage.trim()) return;

        const userMessage = { text: newMessage, isBot: false };
        setMessages([...messages, userMessage]);
        setNewMessage('');

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: newMessage,
                    session_id: sessionId
                }),
            });
            const data = await response.json();
            setSessionId(data.session_id);
            setMessages(msgs => [...msgs, { text: data.response, isBot: true }]);
        } catch (error) {
            console.error('Error:', error);
        }
    };

    return (
        <div className="chat-container">
            <div className="chat-messages">
                <TransitionGroup>
                    {messages.map((msg, index) => (
                        <CSSTransition
                            key={index}
                            timeout={300}
                            classNames="message"
                        >
                            <div className={`message ${msg.isBot ? 'bot' : 'user'}`}>
                                {msg.text}
                            </div>
                        </CSSTransition>
                    ))}
                </TransitionGroup>
                <div ref={messagesEndRef} />
            </div>
            <form onSubmit={sendMessage} className="chat-input">
                <input
                    type="text"
                    value={newMessage}
                    onChange={(e) => setNewMessage(e.target.value)}
                    placeholder="Type your message..."
                />
                <button type="submit">Send</button>
            </form>
        </div>
    );
}

// Add styling
const styles = document.createElement('style');
styles.textContent = `
    .app-container {
        display: flex;
        height: 100vh;
        background: #f8fff8;
    }

    .sidebar {
        width: 300px;
        background: linear-gradient(135deg, #2c5a3f 0%, #3a7555 100%);
        color: white;
        padding: 20px;
        display: flex;
        flex-direction: column;
    }

    .sessions-list {
        flex: 1;
        overflow-y: auto;
        margin: 20px 0;
    }

    .session-item {
        display: flex;
        align-items: center;
        padding: 12px;
        margin: 8px 0;
        background: rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.3s ease;
    }

    .session-item:hover {
        background: rgba(255, 255, 255, 0.2);
    }

    .session-item.active {
        background: rgba(255, 255, 255, 0.3);
        border-left: 4px solid #8bc34a;
    }

    .session-icon {
        font-size: 1.5em;
        margin-right: 12px;
    }

    .session-info {
        display: flex;
        flex-direction: column;
    }

    .session-date {
        font-size: 0.8em;
        opacity: 0.8;
    }

    .session-preview {
        font-size: 0.9em;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .chat-container {
        background: white;
        border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin: 20px;
        height: calc(100vh - 40px);
    }

    .message {
        margin: 10px;
        padding: 15px;
        border-radius: 15px;
        max-width: 80%;
        position: relative;
    }

    .message.user {
        background: #e8f5e9;
        margin-left: auto;
        color: #2c5a3f;
    }

    .message.bot {
        background: #f1f8e9;
        color: #33691e;
    }

    .message::before {
        content: '🌿';
        position: absolute;
        top: -15px;
        font-size: 12px;
    }

    .chat-input {
        background: #f8fff8;
        border-top: 2px solid #e8f5e9;
    }

    .chat-input input {
        background: white;
        border: 2px solid #a5d6a7;
    }

    .chat-input button {
        background: #2c5a3f;
        transition: all 0.3s ease;
    }

    .chat-input button:hover {
        background: #3a7555;
    }

    .nav-btn {
        width: 100%;
        padding: 12px;
        background: #8bc34a;
        border: none;
        border-radius: 8px;
        color: white;
        cursor: pointer;
        transition: all 0.3s ease;
    }

    .nav-btn:hover {
        background: #9ccc65;
    }

    .nav-btn.active {
        background: #689f38;
    }
`;

document.head.appendChild(styles);

ReactDOM.render(<App />, document.getElementById('app')); 