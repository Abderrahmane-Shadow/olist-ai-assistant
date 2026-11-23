import React, { useState } from 'react';
import { X, Database, Settings, Trash2, Cpu, User, AlertTriangle, Loader2 } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { getApiBaseUrl } from '@/lib/api';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onClearAllChats: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose, onClearAllChats }) => {
  const { user, profile, token, signOut } = useAuth();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteConfirmationInput, setDeleteConfirmationInput] = useState('');
  const [isDeletingAccount, setIsDeletingAccount] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleDeleteAccount = async () => {
    if (deleteConfirmationInput.trim() !== 'DELETE') return;
    setIsDeletingAccount(true);
    setDeleteError(null);

    try {
      const baseUrl = getApiBaseUrl();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch(`${baseUrl}/api/auth/account`, {
        method: 'DELETE',
        headers,
        body: JSON.stringify({ confirmation: 'DELETE' }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to delete account.');
      }

      // Successfully deleted from database: clear local storage & sign out
      try {
        localStorage.removeItem('olist_ai_conversations_v1');
        localStorage.removeItem('olist_active_conversation_id');
      } catch (e) {
        console.warn('Could not clear local storage keys:', e);
      }

      await signOut();
      setShowDeleteConfirm(false);
      onClose();
      if (typeof window !== 'undefined') {
        window.location.href = '/login';
      }
    } catch (err: any) {
      setDeleteError(err?.message || 'Failed to delete account. Please try again.');
      setIsDeletingAccount(false);
    }
  };

  return (
    /* Backdrop — clicking outside the card closes the modal */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-fade-in"
      onClick={() => {
        if (!isDeletingAccount) {
          setShowDeleteConfirm(false);
          onClose();
        }
      }}
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
            onClick={() => {
              if (!isDeletingAccount) {
                setShowDeleteConfirm(false);
                onClose();
              }
            }}
            disabled={isDeletingAccount}
            className="p-1 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors cursor-pointer"
            title="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-5 max-h-[80vh] overflow-y-auto">
          {/* Account Profile */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2 flex items-center gap-1.5">
              <User className="w-3.5 h-3.5" /> Account Profile
            </p>
            <div className="p-3 rounded-lg border border-gray-200 bg-gray-50 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">
                  {profile?.display_name || user?.email?.split('@')[0] || 'Authenticated User'}
                </p>
                <p className="text-xs text-gray-500 truncate mt-0.5">
                  {user?.email || profile?.email || 'user@olist.com'}
                </p>
              </div>
              <span className="shrink-0 text-[11px] font-medium px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 capitalize">
                {profile?.role || 'user'}
              </span>
            </div>
          </div>

          {/* Model */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2 flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5" /> Model
            </p>
            <div className="p-3 rounded-lg border border-gray-200 bg-gray-50 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-800">Dynamic Text-to-SQL Engine</p>
                <p className="text-xs text-gray-500 mt-0.5">Powered by Gemini & PostgreSQL Semantic Layer</p>
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
          <div className="pt-2 border-t border-gray-200 space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-red-500">
              Danger Zone
            </p>

            {/* Clear conversations */}
            <div className="flex items-center justify-between gap-3 p-3 rounded-lg border border-gray-200 bg-gray-50">
              <div className="min-w-0">
                <p className="text-xs font-medium text-gray-800">Clear chat history</p>
                <p className="text-[11px] text-gray-500">Removes local chat conversations</p>
              </div>
              <button
                onClick={() => {
                  if (confirm('Clear all conversation history? This cannot be undone.')) {
                    onClearAllChats();
                    onClose();
                  }
                }}
                className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-gray-300 text-gray-700 hover:bg-gray-100 text-xs font-medium transition-colors cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Clear
              </button>
            </div>

            {/* Delete Account */}
            {!showDeleteConfirm ? (
              <div className="flex items-center justify-between gap-3 p-3 rounded-lg border border-red-200 bg-red-50/70">
                <div className="min-w-0">
                  <p className="text-xs font-medium text-red-900">Delete Account</p>
                  <p className="text-[11px] text-red-700">Permanently delete your profile and all messages</p>
                </div>
                <button
                  onClick={() => setShowDeleteConfirm(true)}
                  className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-red-600 hover:bg-red-700 text-white text-xs font-medium transition-colors cursor-pointer shadow-xs"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  Delete Account
                </button>
              </div>
            ) : (
              <div className="p-3.5 rounded-lg border border-red-300 bg-red-50 space-y-3 animate-fade-in">
                <div className="flex items-start gap-2 text-xs text-red-800">
                  <AlertTriangle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
                  <div>
                    <p className="font-semibold text-red-900">Are you absolutely sure?</p>
                    <p className="mt-0.5 text-[11px] text-red-700 leading-normal">
                      This action is irreversible. It will permanently delete your user account, profile, all saved conversations, and usage records.
                    </p>
                  </div>
                </div>

                {deleteError && (
                  <p className="text-xs text-red-700 bg-red-100 p-2 rounded border border-red-200">
                    {deleteError}
                  </p>
                )}

                <div>
                  <label className="block text-[11px] font-medium text-red-900 mb-1">
                    To confirm, please type <span className="font-mono font-bold">DELETE</span> below:
                  </label>
                  <input
                    type="text"
                    value={deleteConfirmationInput}
                    onChange={(e) => setDeleteConfirmationInput(e.target.value)}
                    placeholder="DELETE"
                    disabled={isDeletingAccount}
                    className="w-full bg-white border border-red-300 rounded px-2.5 py-1.5 text-xs text-gray-900 font-mono placeholder:text-gray-400 focus:outline-none focus:border-red-500 focus:ring-1 focus:ring-red-500"
                  />
                </div>

                <div className="flex items-center justify-end gap-2 pt-1">
                  <button
                    type="button"
                    disabled={isDeletingAccount}
                    onClick={() => {
                      setShowDeleteConfirm(false);
                      setDeleteConfirmationInput('');
                      setDeleteError(null);
                    }}
                    className="px-3 py-1.5 rounded text-xs font-medium text-gray-600 hover:bg-gray-100 transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={deleteConfirmationInput.trim() !== 'DELETE' || isDeletingAccount}
                    onClick={handleDeleteAccount}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-semibold text-white bg-red-600 hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer shadow-xs"
                  >
                    {isDeletingAccount ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>Deleting...</span>
                      </>
                    ) : (
                      <>
                        <Trash2 className="w-3.5 h-3.5" />
                        <span>Permanently Delete</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-gray-200 flex justify-end">
          <button
            onClick={() => {
              if (!isDeletingAccount) {
                setShowDeleteConfirm(false);
                onClose();
              }
            }}
            disabled={isDeletingAccount}
            className="px-4 py-1.5 rounded-md border border-gray-200 text-gray-700 hover:bg-gray-50 text-xs font-medium transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

