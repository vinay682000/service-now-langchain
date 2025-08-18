// frontend/src/components/ChatWindow.jsx
import React from 'react';

function ChatWindow({ messages }) {
  return (
    <div className="flex-1 p-4 overflow-y-auto h-96 space-y-2 bg-gray-50">
      {messages.map((msg, idx) => (
        <div
          key={idx}
          className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
        >
          <div
            className={`px-4 py-2 rounded-lg max-w-xs break-words ${
              msg.sender === 'user'
                ? 'bg-blue-500 text-white'
                : 'bg-gray-200 text-gray-800'
            }`}
          >
            {msg.text}
          </div>
        </div>
      ))}
    </div>
  );
}

export default ChatWindow;
