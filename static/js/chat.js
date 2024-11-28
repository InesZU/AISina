document.addEventListener('DOMContentLoaded', function() {
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const chatMessages = document.getElementById('chat-messages');
    const typingIndicator = document.getElementById('typing-indicator');

    console.log('Elements found:', {messageInput, sendButton, chatMessages});

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
                message: message
            })
        })
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        })
        .then(data => {
            if (typingIndicator) typingIndicator.style.display = 'none';
            
            appendMessage(data.response, 'bot-message');
        })
        .catch(error => {
            console.error('Error:', error);
            if (typingIndicator) typingIndicator.style.display = 'none';
            appendMessage('Sorry, I encountered an error. Please try again.', 'bot-message error');
        });
    }

    function appendMessage(content, className) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', className);
        messageDiv.innerHTML = `<div class="message-content">${content}</div>`;
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    sendButton.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendMessage(e);
        }
    });
});