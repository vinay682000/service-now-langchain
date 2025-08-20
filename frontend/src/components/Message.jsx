import React from 'react';
import PropTypes from 'prop-types'; // 1. Import PropTypes

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

// 2. Define propTypes
Message.propTypes = {
  sender: PropTypes.string.isRequired, // sender is a required string
  text: PropTypes.string.isRequired,   // text is a required string
};

export default Message;