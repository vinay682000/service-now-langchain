import React from 'react';
import PropTypes from 'prop-types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

function Message({ sender, text, isTyping }) {
  const isUser = sender === 'user';

  const bubbleClasses = isUser
    ? 'bg-blue-600 text-white self-end rounded-br-none'
    : 'bg-gray-200 text-gray-800 self-start rounded-bl-none';

  return (
    <div className={`flex w-full mb-2 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[70%] p-3 rounded-2xl shadow-md break-words whitespace-pre-wrap ${bubbleClasses}`}
      >
        {isTyping && !isUser ? (
          <span className="typing-dots">● ● ●</span>
        ) : isUser ? (
          <span>{text}</span>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        )}
      </div>
    </div>
  );
}

Message.propTypes = {
  sender: PropTypes.string.isRequired,
  text: PropTypes.string.isRequired,
  isTyping: PropTypes.bool,
};

Message.defaultProps = {
  isTyping: false,
};

export default Message;
