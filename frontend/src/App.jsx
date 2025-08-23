// frontend/src/App.jsx
import React, { useState, useEffect, useRef } from 'react';
import ChatInput from './components/ChatInput';
import { getBotResponseSmart } from './api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './App.css';

console.log("🔄 App.jsx version: 2.2 - Streaming + Markdown + Typing Dots");

const getSessionId = () => {
  const sessionId = localStorage.getItem('sessionId') || `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  localStorage.setItem('sessionId', sessionId);
  return sessionId;
};

function App() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const chatEndRef = useRef(null);
  const longOpTimerRef = useRef(null);
  const streamingMessageIndexRef = useRef(-1);

  useEffect(() => {
    const timer = setTimeout(() => {
      setMessages([{ sender: 'bot', text: 'Hello! I am your ServiceNow Assistant. How can I help you today?' }]);
    }, 100);
    return () => clearTimeout(timer);
  }, []);

  const handleSendMessage = async (text) => {
    setIsLoading(true);

    const userMessage = { sender: 'user', text };
    const thinkingMessage = { sender: 'bot', text: '', isTyping: true, isStreaming: true };

    setMessages(prev => [...prev, userMessage, thinkingMessage]);
    streamingMessageIndexRef.current = messages.length + 1;

    longOpTimerRef.current = setTimeout(() => {
      setMessages(prev => prev.map((msg, idx) => idx === streamingMessageIndexRef.current && msg.text === '' ? { ...msg, text: "Connecting..." } : msg));
    }, 3000);

    const callbacks = {
      onToken: (token, fullMessageSoFar) => {
        clearTimeout(longOpTimerRef.current);
        setMessages(prev => prev.map((msg, idx) => idx === streamingMessageIndexRef.current ? { ...msg, text: fullMessageSoFar, isTyping: true } : msg));
      },
      onComplete: (fullMessage) => {
        clearTimeout(longOpTimerRef.current);
        setMessages(prev => prev.map((msg, idx) => idx === streamingMessageIndexRef.current ? { sender: 'bot', text: fullMessage, isTyping: false } : msg));
        setIsLoading(false);
      },
      onError: (error) => {
        clearTimeout(longOpTimerRef.current);
        setMessages(prev => prev.map((msg, idx) => idx === streamingMessageIndexRef.current ? { sender: 'error', text: error } : msg));
        setIsLoading(false);
      }
    };

    try {
      await getBotResponseSmart(text, callbacks);
    } catch (error) {
      callbacks.onError(error.message);
    }
  };

  useEffect(() => {
    return () => clearTimeout(longOpTimerRef.current);
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages]);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gradient-to-b from-gray-100 to-gray-200 p-4">
      <div className="w-full max-w-md flex flex-col bg-white shadow-xl rounded-xl overflow-hidden">
        <header className="bg-gradient-to-r from-blue-500 to-indigo-500 p-4 text-center text-white font-bold text-xl shadow-md">
          ServiceNow Assistant
        </header>

        {messages.length === 0 && (
          <div className="p-4 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-3/4 mb-2"></div>
            <div className="h-4 bg-gray-200 rounded w-1/2"></div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-4 flex flex-col space-y-4">
          {messages.map((msg, idx) => (
            <div key={idx} className={`message ${msg.sender}`}>
              {msg.sender === 'bot' ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
              ) : (
                <span>{msg.text}</span>
              )}
            </div>
          ))}
          <div ref={chatEndRef} aria-hidden="true" />
        </div>

        <ChatInput onSendMessage={handleSendMessage} disabled={isLoading} />
      </div>
    </div>
  );
}

export default App;
