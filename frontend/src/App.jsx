// frontend/src/App.jsx
import React, { useState, useEffect, useRef } from 'react';
import ChatWindow from './components/ChatWindow';
import ChatInput from './components/ChatInput';
import { getBotResponse } from './api';

// Generate a unique session ID
const getSessionId = () => {
  const sessionId = localStorage.getItem('sessionId') || `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  localStorage.setItem('sessionId', sessionId);
  return sessionId;
};

function App() {
  const [messages, setMessages] = useState([]); // Start empty for better LCP
  const [isLoading, setIsLoading] = useState(false);
  const [setIsLongOperation] = useState(false);
  const sessionIdRef = useRef(getSessionId());
  const chatEndRef = useRef(null);
  const longOpTimerRef = useRef(null);

  // Load initial message after component mounts (LCP optimization)
  useEffect(() => {
    const timer = setTimeout(() => {
      setMessages([
        { sender: 'bot', text: 'Hello! I am your ServiceNow Assistant. How can I help you today?' },
      ]);
    }, 100); // Small delay to improve LCP

    return () => clearTimeout(timer);
  }, []);

  const handleSendMessage = async (text) => {
    setIsLoading(true);
    setIsLongOperation(false);
    
    const userMessage = { sender: 'user', text };
    const thinkingMessage = { sender: 'bot', text: 'Thinking...', isThinking: true };
    
    setMessages((prev) => [...prev, userMessage, thinkingMessage]);

    // Show "taking longer" message after 15 seconds
    longOpTimerRef.current = setTimeout(() => {
      setIsLongOperation(true);
      setMessages(prev => prev.map(msg => 
        msg.isThinking ? { ...msg, text: "This is taking a bit longer than usual..." } : msg
      ));
    }, 15000);

    try {
      const botReply = await getBotResponse(text, sessionIdRef.current);
      
      // Replace thinking message with actual reply
      setMessages((prev) => 
        prev.map((msg) => 
          msg.isThinking ? { sender: 'bot', text: botReply } : msg
        )
      );
    } catch (error) {
      // Replace thinking message with error
      setMessages((prev) => 
        prev.map((msg) => 
          msg.isThinking ? { sender: 'error', text: error.message } : msg
        )
      );
    } finally {
      // Clean up timers and loading states
      clearTimeout(longOpTimerRef.current);
      setIsLoading(false);
      setIsLongOperation(false);
    }
  };

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (longOpTimerRef.current) {
        clearTimeout(longOpTimerRef.current);
      }
    };
  }, []);

  // Scroll to the bottom when messages update
  useEffect(() => {
    if (messages.length > 0) {
      chatEndRef.current?.scrollIntoView({ 
        behavior: 'smooth',
        block: 'nearest'
      });
    }
  }, [messages]);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gradient-to-b from-gray-100 to-gray-200 p-4">
      <div className="w-full max-w-md flex flex-col bg-white shadow-xl rounded-xl overflow-hidden">
        <header className="bg-gradient-to-r from-blue-500 to-indigo-500 p-4 text-center text-white font-bold text-xl shadow-md">
          ServiceNow Assistant
        </header>
        
        {/* Loading skeleton for better LCP */}
        {messages.length === 0 && (
          <div className="p-4 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-3/4 mb-2"></div>
            <div className="h-4 bg-gray-200 rounded w-1/2"></div>
          </div>
        )}
        
        <ChatWindow messages={messages} />
        <ChatInput onSendMessage={handleSendMessage} disabled={isLoading} />
        <div ref={chatEndRef} aria-hidden="true" />
      </div>
    </div>
  );
}

export default App;