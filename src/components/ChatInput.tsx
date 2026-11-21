import React, { useState, useRef, useEffect } from 'react';
import { ArrowUp, Square } from 'lucide-react';

interface ChatInputProps {
  onSendMessage: (text: string) => void;
  isLoading: boolean;
  onStop?: () => void;
  placeholder?: string;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  onSendMessage,
  isLoading,
  onStop,
  placeholder = 'Ask about Olist revenue, products, delays, or sellers...',
}) => {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [input]);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!input.trim() || isLoading) return;
    onSendMessage(input.trim());
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const canSubmit = input.trim().length > 0 && !isLoading;

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3">
      <div className="max-w-3xl mx-auto">
        <form onSubmit={handleSubmit}>
          <div className={`flex items-end gap-2 rounded-lg border bg-white px-3 py-2 transition-colors ${
            isLoading ? 'border-gray-200' : 'border-gray-300 focus-within:border-[#169b75]'
          }`}>
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              disabled={isLoading}
              className="flex-1 resize-none bg-transparent text-sm text-gray-800 placeholder:text-gray-400 focus:outline-none max-h-40 py-1 disabled:opacity-60"
            />
            {isLoading ? (
              <button
                type="button"
                onClick={onStop}
                className="shrink-0 w-7 h-7 rounded-md bg-gray-100 hover:bg-gray-200 flex items-center justify-center transition-colors mb-0.5"
                title="Stop"
              >
                <Square className="w-3 h-3 text-gray-600 fill-gray-600" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!canSubmit}
                className={`shrink-0 w-7 h-7 rounded-md flex items-center justify-center transition-colors mb-0.5 ${
                  canSubmit
                    ? 'bg-[#169b75] hover:bg-[#0f7a5c] text-white'
                    : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                }`}
                title="Send"
              >
                <ArrowUp className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </form>
        <p className="text-[11px] text-gray-400 text-center mt-2">
          Olist AI may make mistakes. Verify critical insights independently.
        </p>
      </div>
    </div>
  );
};
