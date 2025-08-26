// frontend/src/components/ChatWindow.jsx
import React from 'react';

function ChatWindow({ messages }) {
  const formatMessage = (text) => {
    if (!text) return [];
    
    // Split by lines and URLs
    const lines = text.split('\n');
    const formattedLines = [];
    
    lines.forEach((line, lineIndex) => {
      if (lineIndex > 0) {
        formattedLines.push(<br key={`br-${lineIndex}`} />);
      }
      
      // Simple URL detection without innerHTML
      const words = line.split(' ');
      formattedLines.push(
        ...words.map((word, wordIndex) => {
          if (word.match(/^https?:\/\/\S+$/)) {
            return (
              <a
                key={`link-${lineIndex}-${wordIndex}`}
                href={word}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-500 hover:underline"
              >
                {word}{' '}
              </a>
            );
          }
          return <span key={`word-${lineIndex}-${wordIndex}`}>{word} </span>;
        })
      );
    });
    
    return formattedLines;
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
          <div className="mt-1 text-gray-800">
            {formatMessage(message.text)}
          </div>
        </div>
      ))}
    </div>
  );
}

export default ChatWindow;