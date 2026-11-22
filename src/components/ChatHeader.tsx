'use client';

import React, { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import { Menu, Plus, Trash2, User, LogOut } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

interface ChatHeaderProps {
  onToggleSidebar: () => void;
  onNewChat: () => void;
  onClearActiveChat?: () => void;
  title: string;
  hasMessages: boolean;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({
  onToggleSidebar,
  onNewChat,
  onClearActiveChat,
  title,
  hasMessages,
}) => {
  const { user, profile, signOut } = useAuth();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <header
      className="border-b border-gray-200 bg-white px-4 flex items-center justify-between shrink-0 sticky top-0 z-30"
      style={{ height: '52px' }}
    >
      {/* Left */}
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={onToggleSidebar}
          className="p-1.5 rounded-md text-gray-500 hover:text-gray-900 hover:bg-gray-100 lg:hidden transition-colors"
          title="Toggle sidebar"
        >
          <Menu className="w-4.5 h-4.5" style={{ width: '18px', height: '18px' }} />
        </button>
        <span className="text-sm font-medium text-gray-700 truncate max-w-[180px] sm:max-w-xs md:max-w-md">
          {title}
        </span>
      </div>

      {/* Right */}
      <div className="flex items-center gap-2">
        {hasMessages && onClearActiveChat && (
          <button
            onClick={onClearActiveChat}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-md text-gray-500 hover:text-gray-900 hover:bg-gray-100 text-xs transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span className="hidden md:inline">Clear</span>
          </button>
        )}

        <button
          onClick={onNewChat}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-gray-200 text-gray-700 hover:bg-gray-50 text-xs font-medium transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">New Chat</span>
        </button>

        {/* User Account Menu */}
        {user ? (
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-1.5 p-1 rounded-full hover:ring-2 hover:ring-gray-200 transition-all focus:outline-none"
              title={profile?.display_name || user.email || 'Account'}
            >
              <div className="w-7 h-7 rounded-full bg-[#169b75] text-white flex items-center justify-center text-xs font-semibold shadow-xs">
                {(profile?.display_name || user.email || 'U')[0].toUpperCase()}
              </div>
            </button>

            {dropdownOpen && (
              <div className="absolute right-0 mt-2 w-56 bg-white rounded-lg shadow-lg border border-gray-200 py-1.5 z-50 text-xs animate-in fade-in zoom-in-95 duration-100">
                <div className="px-3.5 py-2 border-b border-gray-100">
                  <p className="font-semibold text-gray-900 truncate">
                    {profile?.display_name || 'Analytics User'}
                  </p>
                  <p className="text-gray-500 truncate text-[11px] mt-0.5">{user.email}</p>
                </div>

                <button
                  onClick={() => {
                    setDropdownOpen(false);
                    signOut();
                  }}
                  className="w-full text-left px-3.5 py-2 text-red-600 hover:bg-red-50 flex items-center gap-2 transition-colors"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span>Sign out</span>
                </button>
              </div>
            )}
          </div>
        ) : (
          <Link
            href="/login"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-[#169b75] text-white hover:bg-[#0f7a5c] text-xs font-medium transition-colors shadow-xs"
          >
            <User className="w-3.5 h-3.5" />
            <span>Sign in</span>
          </Link>
        )}
      </div>
    </header>
  );
};
