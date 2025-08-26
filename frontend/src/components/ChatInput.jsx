// frontend/src/components/ChatInput.jsx
import React, { useState, useRef } from 'react';
import PropTypes from 'prop-types';

function ChatInput({ onSendMessage, disabled }) {
  const [inputText, setInputText] = useState('');
  const textareaRef = useRef(null);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (inputText.trim() && !disabled) {
      onSendMessage(inputText.trim());
      setInputText('');
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

// 2. Define propTypes outside the component
ChatInput.propTypes = {
  onSendMessage: PropTypes.func.isRequired, // function, required
  disabled: PropTypes.bool,                 // boolean, optional
};

  const handleKeyDown = (e) => {
    // Shift + Enter = New line
    if (e.key === 'Enter' && e.shiftKey) {
      e.preventDefault();
      const cursorPosition = e.target.selectionStart;
      const textBefore = inputText.substring(0, cursorPosition);
      const textAfter = inputText.substring(cursorPosition);
      
      setInputText(textBefore + '\n' + textAfter);
      
      // Move cursor to the new position
      setTimeout(() => {
        e.target.selectionStart = cursorPosition + 1;
        e.target.selectionEnd = cursorPosition + 1;
      }, 0);
    }
    // Enter (without Shift) = Send message
    else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleInputChange = (e) => {
    setInputText(e.target.value);
    
    // Auto-resize textarea
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
    }
  };

  return (
    <form onSubmit={handleSubmit} className="p-4 border-t border-gray-200 bg-white">
      <div className="flex space-x-2 items-end">
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            id="chat-input"
            name="chat-message"
            value={inputText}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder={disabled ? "Processing your request..." : "Type your message"}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed resize-none min-h-[44px] max-h-[120px] overflow-y-auto"
            aria-label="Chat message input"
            rows={1}
            style={{ height: 'auto' }}
          />
          <div className="absolute bottom-1 right-2 text-xs text-gray-400">
            {disabled ? '' : ''}
          </div>
        </div>
        <button
          type="submit"
          disabled={disabled || !inputText.trim()}
          className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors h-[44px] min-w-[80px] flex items-center justify-center"
          aria-label="Send message"
        >
          {disabled ? '⏳' : 'Send'}
        </button>
      </div>
    </form>
  );
}

export default ChatInput;