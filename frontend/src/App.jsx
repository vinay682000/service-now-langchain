// frontend/src/App.jsx
import React, { useState, useEffect, useRef } from 'react';
import ChatWindow from './components/ChatWindow';
import ChatInput from './components/ChatInput';
import { getBotResponse } from './api';

// Generate a unique session ID
const sessionId = localStorage.getItem('sessionId') || `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
localStorage.setItem('sessionId', sessionId);

function App() {
  const [messages, setMessages] = useState([
    { sender: 'bot', text: 'Hello! I am your ServiceNow Assistant. How can I help you today?' },
  ]);

  const chatEndRef = useRef(null);

  const handleSendMessage = async (text) => {
    const userMessage = { sender: 'user', text };
    const thinkingMessage = { sender: 'bot', text: 'Thinking...' };
    setMessages((prev) => [...prev, userMessage, thinkingMessage]);

    try {
      const botReply = await getBotResponse(text, sessionId);
      setMessages((prev) => prev.map((msg) => (msg === thinkingMessage ? { sender: 'bot', text: botReply } : msg)));
    } catch (error) {
      setMessages((prev) => prev.map((msg) => (msg === thinkingMessage ? { sender: 'bot', text: error.message } : msg)));
    }
  };

  // Scroll to the bottom when messages update
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gradient-to-b from-gray-100 to-gray-200 p-4">
      <div className="w-full max-w-md flex flex-col bg-white shadow-xl rounded-xl overflow-hidden">
        <header className="bg-gradient-to-r from-blue-500 to-indigo-500 p-4 text-center text-white font-bold text-xl shadow-md">
          ServiceNow Assistant
        </header>
        <ChatWindow messages={messages} />
        <ChatInput onSendMessage={handleSendMessage} />
        <div ref={chatEndRef} />
      </div>
    </div>
  );
}

export default App;
