// frontend/src/components/ChatWindow.jsx
import React from 'react';

// If you prefer using dangerouslySetInnerHTML (more efficient for large texts)
function ChatWindow({ messages }) {
  const formatMessage = (text) => {
    if (!text) return '';
    
    // Convert URLs to links
    text = text.replace(
      /(https?:\/\/[^\s]+)/g, 
      '<a href="$1" target="_blank" rel="noopener noreferrer" class="text-blue-500 hover:underline">$1</a>'
    );
    
    // Convert line breaks to <br> tags
    text = text.replace(/\n/g, '<br>');
    
    return { __html: text };
  };

  return (
    <div className="flex-1 p-4 overflow-y-auto max-h-96 bg-gray-50">
      {messages.map((message, index) => (
        <div
          key={index}
          className={`mb-3 p-3 rounded-lg ${
            message.sender === 'user'
              ? 'bg-blue-100 ml-8 text-right'
              : message.sender === 'error'
              ? 'bg-red-100 border border-red-300 mr-8'
              : 'bg-gray-100 mr-8'
          }`}
        >
          <div className={`font-medium text-sm ${
            message.sender === 'user' ? 'text-blue-700' : 
            message.sender === 'error' ? 'text-red-700' : 'text-gray-700'
          }`}>
            {message.sender === 'user' ? 'You' : 
             message.sender === 'error' ? 'Error' : 'Assistant'}
          </div>
          <div 
            className="mt-1 text-gray-800"
            dangerouslySetInnerHTML={formatMessage(message.text)}
          />
        </div>
      ))}
    </div>
  );
}

export default ChatWindow;