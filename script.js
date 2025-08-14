/*
  File: script.js
  Description: This file handles the interactivity of our chat interface.
  It now includes file handling, a persistent session, and a typing indicator.
*/

// --- DOM Element References ---
const messageArea = document.getElementById('message-area');
const messageForm = document.getElementById('message-form');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');
const fileInput = document.getElementById('file-upload');

// The URL of our FastAPI backend
// This relative path works because FastAPI serves this file
const CHAT_URL = '/chat';

// Generate a unique session ID for the user
const sessionId = localStorage.getItem('sessionId') || `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
localStorage.setItem('sessionId', sessionId);

// --- Event Listeners ---

/**
 * Handles the submission of the message form.
 */
messageForm.addEventListener('submit', async (event) => {
    event.preventDefault();

    const messageText = messageInput.value.trim();
    const file = fileInput.files[0];

    // If both message and file are empty, do nothing
    if (messageText === '' && !file) {
        return;
    }

    let fileData = null;
    let fileMessage = '';

    // If a file is selected, process it
    if (file) {
        fileData = await readFileAsBase64(file);
        fileMessage = ` (with attachment: ${file.name})`;
    }

    // Add the user's message to the chat window
    addMessage(`${messageText}${fileMessage}`, 'user');

    // Clear the input and file field, then disable the form
    messageInput.value = '';
    fileInput.value = '';
    messageInput.focus();
    sendButton.disabled = true;

    try {
        const botResponse = await getBotResponse(messageText, fileData, file?.name);
        addMessage(botResponse, 'bot');
    } catch (error) {
        console.error("Error fetching bot response:", error);
        // addMessage("Sorry, I'm having trouble connecting to the server. Please try again later.", 'bot');
        addMessage(error.message, 'bot');
    } finally {
        sendButton.disabled = false;
    }
});


// --- Functions ---

/**
 * Creates and appends a new chat message to the message area.
 * @param {string} text - The text content of the message.
 * @param {string} sender - Who sent the message ('user' or 'bot').
 */
function addMessage(text, sender) {
    const messageContainer = document.createElement('div');
    messageContainer.classList.add('chat-message', `${sender}-message`, 'mb-4', 'flex');
    if (sender === 'user') {
        messageContainer.classList.add('justify-end');
    }

    const bubble = document.createElement('div');
    bubble.classList.add('rounded-xl', 'p-4', 'max-w-md', 'shadow-md');
    bubble.innerHTML = `<p class="text-sm">${text}</p>`;

    if (sender === 'user') {
        bubble.classList.add('bg-blue-600', 'text-white');
    } else {
        bubble.classList.add('bg-gray-100', 'text-gray-800');
        const avatarContainer = document.createElement('div');
        avatarContainer.classList.add('flex-shrink-0', 'h-10', 'w-10', 'rounded-full', 'bg-gray-300', 'flex', 'items-center', 'justify-center', 'mr-3');
        avatarContainer.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>`;
        messageContainer.appendChild(avatarContainer);
    }

    messageContainer.appendChild(bubble);
    messageArea.appendChild(messageContainer);

    messageArea.scrollTop = messageArea.scrollHeight;
}

/**
 * Sends the user's message and optional file data to the backend API.
 * @param {string} userMessage - The message the user sent.
 * @param {string|null} fileContent - Base64 encoded file content.
 * @param {string|null} fileName - The name of the file.
 * @returns {Promise<string>} The bot's reply.
 */
async function getBotResponse(userMessage, fileContent = null, fileName = null) {
    const typingIndicator = showTypingIndicator();

    try {
        const payload = {
            message: userMessage,
            session_id: sessionId,
        };

        if (fileContent && fileName) {
            payload.file_content = fileContent;
            payload.file_name = fileName;
        }

        const response = await fetch(CHAT_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
        });

        // The key change is here: check for a successful response.
        if (!response.ok) {
            const errorData = await response.json();
            // Throw a new error with the specific message from the backend.
            throw new Error(errorData.reply); 
        }

        const data = await response.json();
        return data.reply;

    } finally {
        hideTypingIndicator(typingIndicator);
    }
}

/**
 * Reads a file as a Base64 encoded string.
 * @param {File} file - The file object to read.
 * @returns {Promise<string>} A promise that resolves with the Base64 string.
 */
function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => {
            // Remove the 'data:mime/type;base64,' prefix
            const base64String = reader.result.split(',')[1];
            resolve(base64String);
        };
        reader.onerror = error => reject(error);
    });
}

/**
 * Displays a temporary "typing..." message from the bot.
 * @returns {HTMLElement} The typing indicator element.
 */
function showTypingIndicator() {
    const typingIndicator = document.createElement('div');
    typingIndicator.id = 'typing-indicator';
    typingIndicator.classList.add('chat-message', 'bot-message', 'mb-4', 'flex');
    typingIndicator.innerHTML = `
        <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300 flex items-center justify-center mr-3">
             <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>
        </div>
        <div class="bg-gray-100 rounded-xl p-4 max-w-xs shadow-md">
            <div class="typing-dots"><span></span><span></span><span></span></div>
        </div>
    `;
    messageArea.appendChild(typingIndicator);
    messageArea.scrollTop = messageArea.scrollHeight;
    return typingIndicator;
}

/**
 * Removes the typing indicator from the chat.
 * @param {HTMLElement} indicator - The typing indicator element to remove.
 */
function hideTypingIndicator(indicator) {
    if (indicator) {
        indicator.remove();
    }
}