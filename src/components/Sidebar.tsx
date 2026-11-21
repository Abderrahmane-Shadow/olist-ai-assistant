import React, { useState } from 'react';
import Link from 'next/link';
import {
  Plus,
  MessageSquare,
  Trash2,
  Edit2,
  Check,
  X,
  Settings,
  Search,
  BarChart2,
  LogOut,
  User as UserIcon,
  ShieldCheck,
} from 'lucide-react';
import { Conversation } from '@/types/chat';
import { useAuth } from '@/context/AuthContext';

interface SidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onDeleteConversation: (id: string) => void;
  onRenameConversation: (id: string, newTitle: string) => void;
  isOpen: boolean;
  onToggle: () => void;
  onOpenSettings: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  conversations,
  activeId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  onRenameConversation,
  isOpen,
  onToggle,
  onOpenSettings,
}) => {
  const { user, profile, signOut } = useAuth();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  const handleStartRename = (e: React.MouseEvent, conv: Conversation) => {
    // Stop both the click and prevent parent div from firing onSelectConversation
    e.preventDefault();
    e.stopPropagation();
    setEditingId(conv.id);
    setEditTitle(conv.title);
  };

  const handleSaveRename = (e: React.FormEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (editTitle.trim()) onRenameConversation(id, editTitle.trim());
    setEditingId(null);
  };

  const handleCancelRename = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setEditingId(null);
  };

  const now = Date.now();
  const oneDayMs = 86400000;
  const sevenDaysMs = 7 * oneDayMs;

  const filtered = conversations.filter((c) =>
    c.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const todayChats = filtered.filter((c) => now - c.updatedAt < oneDayMs);
  const weekChats = filtered.filter(
    (c) => now - c.updatedAt >= oneDayMs && now - c.updatedAt < sevenDaysMs
  );
  const olderChats = filtered.filter((c) => now - c.updatedAt >= sevenDaysMs);

  const renderGroup = (label: string, chats: Conversation[]) => {
    if (!chats.length) return null;
    return (
      <div className="mb-4" key={label}>
        <p className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
          {label}
        </p>
        <div className="mt-0.5 space-y-0.5">
          {chats.map((conv) => {
            const isActive = conv.id === activeId;
            const isEditing = editingId === conv.id;

            return (
              <div
                key={conv.id}
                onClick={() => {
                  if (!isEditing) onSelectConversation(conv.id);
                }}
                className={`group relative flex items-center gap-2 px-3 py-2 rounded-md cursor-pointer select-none transition-colors ${
                  isActive
                    ? 'bg-[#e8f7f3] text-[#111827]'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                }`}
              >
                <MessageSquare
                  className={`w-3.5 h-3.5 shrink-0 ${
                    isActive ? 'text-[#169b75]' : 'text-gray-400'
                  }`}
                />

                {isEditing ? (
                  /* Rename form — isolated from parent click via stopPropagation on form */
                  <form
                    onSubmit={(e) => handleSaveRename(e, conv.id)}
                    onClick={(e) => e.stopPropagation()}
                    className="flex-1 flex items-center gap-1 min-w-0"
                  >
                    <input
                      autoFocus
                      type="text"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Escape') {
                          e.stopPropagation();
                          setEditingId(null);
                        }
                      }}
                      className="flex-1 min-w-0 text-xs bg-white border border-[#169b75] rounded px-1.5 py-0.5 focus:outline-none"
                    />
                    <button
                      type="submit"
                      className="shrink-0 text-[#169b75] hover:text-[#0f7a5c] p-0.5"
                      title="Save"
                    >
                      <Check className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={handleCancelRename}
                      className="shrink-0 text-gray-400 hover:text-gray-600 p-0.5"
                      title="Cancel"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </form>
                ) : (
                  <span className="flex-1 text-xs truncate">{conv.title}</span>
                )}

                {/* Action buttons — only visible when not editing */}
                {!isEditing && (
                  <div
                    className={`flex items-center gap-0.5 shrink-0 ${
                      isActive ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                    } transition-opacity`}
                  >
                    <button
                      type="button"
                      onClick={(e) => handleStartRename(e, conv)}
                      className="p-0.5 rounded text-gray-400 hover:text-gray-700 transition-colors"
                      title="Rename"
                    >
                      <Edit2 className="w-3 h-3" />
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        onDeleteConversation(conv.id);
                      }}
                      className="p-0.5 rounded text-gray-400 hover:text-red-500 transition-colors"
                      title="Delete"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <>
      {/* Mobile backdrop — rendered outside <aside> so z-index works correctly */}
      {isOpen && (
        <div
          onClick={onToggle}
          aria-hidden="true"
          className="fixed inset-0 z-40 bg-black/20 lg:hidden"
        />
      )}

      {/* Sidebar panel */}
      <aside
        className={`
          fixed top-0 bottom-0 left-0 z-50 flex flex-col w-64 shrink-0
          bg-[#f8f9fa] border-r border-gray-200
          transition-transform duration-200 ease-in-out
          lg:static lg:translate-x-0 lg:z-auto
          ${isOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
      >
        {/* Brand header */}
        <div className="flex items-center gap-2.5 px-4 py-4 border-b border-gray-200 shrink-0">
          <div className="w-7 h-7 rounded-md bg-[#169b75] flex items-center justify-center shrink-0">
            <BarChart2 className="w-4 h-4 text-white" />
          </div>
          <div className="min-w-0">
            <h1 className="text-sm font-semibold text-gray-900 leading-tight">Olist AI</h1>
            <p className="text-[11px] text-gray-500">Analytics Assistant</p>
          </div>
          {/* Close button — mobile only */}
          <button
            onClick={onToggle}
            className="ml-auto p-1 rounded text-gray-400 hover:text-gray-600 lg:hidden shrink-0"
            title="Close sidebar"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* New Chat button */}
        <div className="p-3 shrink-0">
          <button
            onClick={onNewChat}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-md bg-[#169b75] hover:bg-[#0f7a5c] text-white text-sm font-medium transition-colors"
          >
            <Plus className="w-4 h-4 shrink-0" />
            <span>New Chat</span>
          </button>
        </div>

        {/* Search — only visible when there are more than 2 conversations */}
        {conversations.length > 2 && (
          <div className="px-3 pb-2 shrink-0">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="text"
                placeholder="Search..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-white border border-gray-200 rounded-md pl-8 pr-3 py-1.5 text-xs text-gray-700 placeholder:text-gray-400 focus:outline-none focus:border-[#169b75] transition-colors"
              />
            </div>
          </div>
        )}

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto px-2 py-1">
          {conversations.length === 0 ? (
            <p className="text-xs text-gray-400 text-center py-8">No conversations yet.</p>
          ) : filtered.length === 0 ? (
            <p className="text-xs text-gray-400 text-center py-6">No results found.</p>
          ) : (
            <>
              {renderGroup('Today', todayChats)}
              {renderGroup('Previous 7 Days', weekChats)}
              {renderGroup('Older', olderChats)}
            </>
          )}
        </div>

        {/* User profile & Settings footer */}
        <div className="p-3 border-t border-gray-200 shrink-0 space-y-1">
          {user ? (
            <div className="flex items-center justify-between p-2 rounded-md bg-gray-50 border border-gray-100">
              <div className="flex items-center gap-2 min-w-0">
                <div className="w-6 h-6 rounded-full bg-[#169b75] text-white flex items-center justify-center text-[10px] font-semibold shrink-0">
                  {(profile?.display_name || user.email || 'U')[0].toUpperCase()}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-1">
                    <p className="text-xs font-medium text-gray-900 truncate">
                      {profile?.display_name || user.email?.split('@')[0]}
                    </p>
                    {profile?.role === 'admin' && (
                      <ShieldCheck className="w-3 h-3 text-purple-600 shrink-0" />
                    )}
                  </div>
                  <p className="text-[10px] text-gray-400 truncate">{user.email}</p>
                </div>
              </div>
              <button
                onClick={() => signOut()}
                className="p-1 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                title="Sign out"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            </div>
          ) : (
            <Link
              href="/login"
              className="w-full flex items-center justify-center gap-2 px-3 py-1.5 rounded-md border border-[#169b75] text-[#169b75] hover:bg-[#169b75]/5 text-xs font-medium transition-colors"
            >
              <UserIcon className="w-3.5 h-3.5" />
              <span>Sign in to save chats</span>
            </Link>
          )}

          <button
            onClick={onOpenSettings}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-gray-600 hover:bg-gray-100 hover:text-gray-900 text-xs transition-colors"
          >
            <Settings className="w-3.5 h-3.5 shrink-0" />
            <span>Settings</span>
          </button>
        </div>
      </aside>
    </>
  );
};
