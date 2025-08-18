// frontend/src/components/ChatInput.jsx
import React, { useState } from 'react';

function ChatInput({ onSendMessage }) {
  const [text, setText] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    onSendMessage(text);
    setText('');
  };

  return (
    <form onSubmit={handleSubmit} className="flex p-4 border-t border-gray-300 bg-gray-100">
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Type your message..."
        className="flex-1 px-4 py-2 rounded-l-full border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-400"
      />
      <button
        type="submit"
        className="px-4 py-2 bg-blue-500 text-white font-semibold rounded-r-full hover:bg-blue-600 transition-colors"
      >
        Send
      </button>
    </form>
  );
}

export default ChatInput;
