import React from 'react';
import { X, Database, Settings, Trash2, Cpu } from 'lucide-react';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onClearAllChats: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose, onClearAllChats }) => {
  if (!isOpen) return null;

  return (
    /* Backdrop — clicking outside the card closes the modal */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/30 animate-fade-in"
      onClick={onClose}
    >
      {/* Modal card — stop propagation so clicks inside don't close the modal */}
      <div
        className="w-full max-w-md bg-white rounded-xl border border-gray-200 shadow-xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <Settings className="w-4 h-4 text-gray-600" />
            <h2 className="text-sm font-semibold text-gray-900">Settings</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
            title="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-5">
          {/* Model */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2 flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5" /> Model
            </p>
            <div className="p-3 rounded-lg border border-gray-200 bg-gray-50 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-800">Olist Analytics Engine</p>
                <p className="text-xs text-gray-500 mt-0.5">Pre-trained on Brazilian e-commerce data</p>
              </div>
              <span className="shrink-0 text-[11px] font-medium px-2 py-0.5 rounded-full bg-[#e8f7f3] text-[#169b75] border border-[#c3ebe0]">
                Active
              </span>
            </div>
          </div>

          {/* Dataset */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2 flex items-center gap-1.5">
              <Database className="w-3.5 h-3.5" /> Dataset
            </p>
            <div className="p-3 rounded-lg border border-gray-200 bg-gray-50 space-y-1.5 text-xs">
              {[
                ['Database', 'olist_ecommerce_db'],
                ['Total Orders', '99,441'],
                ['Period', 'Sep 2016 – Oct 2018'],
                ['Sellers', '3,095'],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4">
                  <span className="text-gray-500">{k}</span>
                  <span className="font-medium text-gray-800">{v}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Danger zone */}
          <div className="pt-1 border-t border-gray-200">
            <p className="text-xs font-semibold uppercase tracking-wider text-red-500 mb-2">
              Data Management
            </p>
            <div className="flex items-center justify-between gap-3 p-3 rounded-lg border border-red-100 bg-red-50">
              <div className="min-w-0">
                <p className="text-xs font-medium text-gray-800">Clear all conversations</p>
                <p className="text-[11px] text-gray-500">Permanently removes all local history</p>
              </div>
              <button
                onClick={() => {
                  if (confirm('Clear all conversations? This cannot be undone.')) {
                    onClearAllChats();
                    onClose();
                  }
                }}
                className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-red-200 text-red-600 hover:bg-red-100 text-xs font-medium transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Clear
              </button>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-gray-200 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-md border border-gray-200 text-gray-700 hover:bg-gray-50 text-xs font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
