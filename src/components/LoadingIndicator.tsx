import React from 'react';

interface LoadingIndicatorProps {
  onStop?: () => void;
}

export const LoadingIndicator: React.FC<LoadingIndicatorProps> = ({ onStop }) => {
  return (
    <div className="w-full px-4 sm:px-6 py-5 bg-gray-50 border-y border-gray-100 animate-fade-in">
      <div className="max-w-3xl mx-auto flex gap-3 items-start">
        {/* Avatar */}
        <div className="shrink-0 mt-0.5">
          <div className="w-7 h-7 rounded-md bg-[#169b75] flex items-center justify-center">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-semibold text-gray-800">Olist AI</span>
            <span className="text-[11px] text-gray-400">Thinking...</span>
          </div>

          <div className="flex items-center gap-3">
            {/* Dot pulse */}
            <div className="flex items-center gap-1.5 py-1">
              <span className="w-2 h-2 rounded-full bg-gray-300 animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-2 h-2 rounded-full bg-gray-300 animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-2 h-2 rounded-full bg-gray-300 animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>

            {onStop && (
              <button
                onClick={onStop}
                className="text-xs text-gray-500 hover:text-gray-800 px-2 py-1 rounded border border-gray-200 hover:border-gray-300 bg-white transition-colors"
              >
                Stop
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
