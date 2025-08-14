// frontend/src/components/Message.jsx
import React from 'react';

function Message({ sender, text }) {
  const isUser = sender === 'user';
  const messageClasses = isUser
    ? 'bg-blue-500 text-white self-end'
    : 'bg-gray-300 text-gray-800 self-start';

  return (
    <div className={`flex flex-col max-w-md p-3 rounded-lg ${messageClasses}`}>
      <p>{text}</p>
    </div>
  );
}

export default Message;