document.addEventListener('DOMContentLoaded', () => {
    const chatMessages = document.getElementById('chat-messages');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const typingIndicator = document.getElementById('typing-indicator');
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

    let currentSessionId = document.getElementById('current-session-id')?.value || null;

    const appendMessage = (content, role) => {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${role}`;
            messageDiv.innerHTML = `<span>${content}</span>`;
            chatMessages.appendChild(messageDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        };

    const updateSessionTitle = (sessionId) => {
        if (!sessionId) {
            console.error('Session ID is required to update the title.');
            return;
        }

        if (sessionStorage.getItem('titleGenerated') !== 'true') {
            fetch(`/get_session_title?session_id=${sessionId}`)
                .then((response) => response.json())
                .then((data) => {
                    if (data.status === 'ready') {
                        const titleElement = document.querySelector('h1'); // Update with your title element selector
                        if (titleElement) {
                            titleElement.textContent = data.title;
                            sessionStorage.setItem('titleGenerated', 'true');
                        }
                    }
                })
                .catch((error) => {
                    console.error('Error fetching session title:', error);
                });
        }
    };

    // Load existing messages on page load
    const messages = window.initialMessages || [];
    messages.forEach((msg) => {
        appendMessage(msg.content, msg.role === 'user' ? 'user-message' : 'bot-message');
    });

    // Fetch and update the session title on page load
    const sessionIdElement = document.getElementById('current-session-id');
    if (sessionIdElement) {
        const sessionId = sessionIdElement.value;
        updateSessionTitle(sessionId);
    }

    const sendMessage = async () => {
        const message = messageInput.value.trim();
        if (!message) return;

        appendMessage(message, 'user-message');
        messageInput.value = '';

        typingIndicator.style.display = 'flex';

        const sessionId = document.getElementById('current-session-id').value || null;
        try {
            const response = await fetch('/chat_message', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
                body: JSON.stringify({
                    message,
                    session_id: document.getElementById('current-session-id').value,
                }),
            });
            const data = await response.json();
            if (data.response) {
                appendMessage(data.response, 'bot-message');
                if (!sessionId && data.session_id) {
                    document.getElementById('current-session-id').value = data.session_id;
                }
                typingIndicator.style.display = 'none';
            }
            if (data.is_empty_session) return; // Prevent saving empty sessions
        } catch (error) {
            appendMessage('Error: Unable to send message.', 'bot-message');
            console.error(error);
            typingIndicator.style.display = 'none';
        }
    };
    sendButton.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    const deleteSession = async (sessionId) => {
        console.log(`Deleting session: ${sessionId}`); // Debugging line
        try {
            const response = await fetch('/delete_session', {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ session_id: sessionId }),
            });
            if (response.ok) {
                alert('Session deleted successfully');
                console.log('Session deleted successfully');
                location.reload();
            } else {
                alert('Failed to delete session');
                console.error(`Failed to delete session: ${response.statusText}`);
            }
        } catch (error) {
            console.error('Error deleting session:', error);
        }
    };

    const reopenSession = (sessionId) => {
        window.location.href = `/chat?session_id=${sessionId}`;
    };

    sendButton.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    window.deleteSession = deleteSession;
    window.reopenSession = reopenSession;
});