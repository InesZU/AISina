document.addEventListener('DOMContentLoaded', function() {
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const chatMessages = document.getElementById('chat-messages');
    const typingIndicator = document.getElementById('typing-indicator');
    let currentSessionId = document.getElementById('current-session-id')?.value || null;

    function sendMessage(e) {
        e.preventDefault();
        const message = messageInput.value.trim();
        
        if (!message) return;

        appendMessage(message, 'user-message');
        messageInput.value = '';

        if (typingIndicator) typingIndicator.style.display = 'flex';

        fetch('/chat_message', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            },
            body: JSON.stringify({
                message: message,
                session_id: currentSessionId
            })
        })
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        })
        .then(data => {
            if (typingIndicator) typingIndicator.style.display = 'none';
            
            if (data.error) {
                appendMessage('Sorry, an error occurred: ' + data.error, 'bot-message error');
            } else {
                appendMessage(data.response, 'bot-message');
                if (data.session_id && !currentSessionId) {
                    currentSessionId = data.session_id;
                }
            }
        })
        .catch(error => {
            console.error('Error:', error);
            if (typingIndicator) typingIndicator.style.display = 'none';
            appendMessage('Sorry, I encountered an error. Please try again.', 'bot-message error');
        });
    }

    function appendMessage(content, className) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${className}`;
        messageDiv.innerHTML = `
            <div class="message-content">
                ${content}
            </div>
        `;
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function deleteSession(sessionId) {
        fetch(`/delete_session/${sessionId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const sessionElement = document.querySelector(`.session-item[data-session-id="${sessionId}"]`);
                if (sessionElement) {
                    sessionElement.remove();
                }
            } else {
                alert('Failed to delete session');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while deleting the session');
        });
    }

    if (sendButton) sendButton.addEventListener('click', sendMessage);
    if (messageInput) {
        messageInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage(e);
            }
        });
    }
});