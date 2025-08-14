// frontend/src/App.jsx
import React, { useState, useEffect } from 'react';
import ChatWindow from './components/ChatWindow';
import ChatInput from './components/ChatInput';
import { getBotResponse } from './api';

// Generate a unique session ID for the user
const sessionId =
  localStorage.getItem('sessionId') ||
  `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
localStorage.setItem('sessionId', sessionId);

function App() {
  const [messages, setMessages] = useState([
    { sender: 'bot', text: 'Hello! I am your ServiceNow Assistant. How can I help you today?' },
  ]);

  const handleSendMessage = async (text) => {
    const userMessage = { sender: 'user', text };
    const thinkingMessage = { sender: 'bot', text: 'Thinking...' };

    // Merge user message and thinking message
    setMessages((prev) => [...prev, userMessage, thinkingMessage]);

    try {
      const botReply = await getBotResponse(text, sessionId);

      // Replace 'Thinking...' with bot reply
      setMessages((prev) =>
        prev.map((msg) => (msg === thinkingMessage ? { sender: 'bot', text: botReply } : msg))
      );
    } catch (error) {
      setMessages((prev) =>
        prev.map((msg) => (msg === thinkingMessage ? { sender: 'bot', text: error.message } : msg))
      );
    }
  };

  // Auto-scroll to the latest message
  useEffect(() => {
    const chatWindow = document.getElementById('chat-window');
    if (chatWindow) chatWindow.scrollTop = chatWindow.scrollHeight;
  }, [messages]);

  return (
    <div className="flex flex-col h-screen bg-gray-100">
      <h1 className="text-3xl font-bold text-center py-4 bg-white shadow-md">
        ServiceNow Assistant
      </h1>
      <ChatWindow messages={messages} />
      <ChatInput onSendMessage={handleSendMessage} />
    </div>
  );
}

export default App;
