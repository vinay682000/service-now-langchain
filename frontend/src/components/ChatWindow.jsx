// frontend/src/components/ChatWindow.jsx
import React from 'react';

function ChatWindow({ messages }) {
  return (
    <div
      id="chat-window"
      className="flex-1 overflow-y-auto p-4 space-y-2 bg-gray-50"
    >
      {messages.map((msg, idx) => (
        <div
          key={idx}
          className={`max-w-xs p-2 rounded-md ${
            msg.sender === 'user' ? 'bg-blue-500 text-white self-end' : 'bg-gray-200 text-black self-start'
          }`}
        >
          {msg.text}
        </div>
      ))}
    </div>
  );
}

export default ChatWindow;
