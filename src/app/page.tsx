'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Sidebar } from '@/components/Sidebar';
import { ChatHeader } from '@/components/ChatHeader';
import { WelcomeScreen } from '@/components/WelcomeScreen';
import { ChatMessage } from '@/components/ChatMessage';
import { ChatInput } from '@/components/ChatInput';
import { LoadingIndicator } from '@/components/LoadingIndicator';
import { SettingsModal } from '@/components/SettingsModal';
import { Conversation, Message, MetricCard, ChartConfig, ReviewCitation, SentimentSummary } from '@/types/chat';
import { getMockResponse } from '@/data/mockResponses';
import { useAuth } from '@/context/AuthContext';

const STORAGE_KEY = 'olist_ai_conversations_v1';
const ACTIVE_CONV_KEY = 'olist_ai_active_id_v1';
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface BackendChatResponse {
  text: string;
  source: 'postgresql' | 'gemini' | 'clarification' | 'unsupported';
  intent?: string | null;
  metrics?: MetricCard[];
  breakdown?: {
    title: string;
    items: { label: string; value: string; percentage?: number }[];
  };
  chart?: ChartConfig;
  columns?: string[];
  rows?: Record<string, any>[];
  review_citations?: ReviewCitation[];
  sentiment_summary?: SentimentSummary;
  sql_query?: string;
  timestamp?: string;
  language?: string;
  conversation_id?: string;
  daily_usage?: {
    used: number;
    limit: number;
    remaining: number;
  };
  metadata?: Record<string, any>;
}

const generateUUID = () => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'conv-' + Date.now() + '-' + Math.random().toString(36).substring(2, 9);
};

const createDefaultConversation = (): Conversation => {
  return {
    id: generateUUID(),
    title: 'New Conversation',
    createdAt: Date.now(),
    updatedAt: Date.now(),
    messages: [],
  };
};

export default function Home() {
  const { user, token, setDailyUsage } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [isClient, setIsClient] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Sync conversations from backend when logged in, or localStorage for guests
  useEffect(() => {
    setIsClient(true);

    if (token) {
      // Fetch authenticated conversations from PostgreSQL backend
      fetch(`${API_BASE_URL}/api/conversations`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (data && Array.isArray(data) && data.length > 0) {
            const mapped: Conversation[] = data.map((item: any) => ({
              id: item.id,
              title: item.title,
              createdAt: new Date(item.created_at).getTime(),
              updatedAt: new Date(item.updated_at).getTime(),
              messages: [], // Will load on selection if needed
            }));
            setConversations(mapped);
            setActiveId(mapped[0].id);
            // Load messages for the active conversation
            loadConversationMessages(mapped[0].id, token);
          } else {
            const initial = createDefaultConversation();
            setConversations([initial]);
            setActiveId(initial.id);
          }
        })
        .catch((err) => {
          console.warn('Could not fetch server conversations, using local state:', err);
          loadFromLocalStorage();
        });
    } else {
      loadFromLocalStorage();
    }
  }, [token]);

  const loadFromLocalStorage = () => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      const savedActiveId = localStorage.getItem(ACTIVE_CONV_KEY);

      if (saved) {
        const parsed: Conversation[] = JSON.parse(saved);
        if (parsed.length > 0) {
          setConversations(parsed);
          setActiveId(
            parsed.some((c) => c.id === savedActiveId) ? savedActiveId : parsed[0].id
          );
          return;
        }
      }
    } catch (err) {
      console.error('Failed to load conversations from localStorage:', err);
    }

    const initial = createDefaultConversation();
    setConversations([initial]);
    setActiveId(initial.id);
  };

  const loadConversationMessages = useCallback(
    async (convId: string, authToken: string) => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/conversations/${convId}`, {
          headers: {
            Authorization: `Bearer ${authToken}`,
          },
        });
        if (res.ok) {
          const detail = await res.json();
          if (detail && detail.messages) {
            const parsedMsgs: Message[] = detail.messages.map((m: any) => {
              const meta = m.metadata || {};
              return {
                id: m.id,
                sender: m.role === 'user' ? 'user' : 'assistant',
                text: m.content,
                timestamp: new Date(m.created_at).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                }),
                metrics: meta.metrics,
                breakdown: meta.breakdown,
                chart: meta.chart,
                columns: meta.columns,
                rows: meta.rows,
                review_citations: meta.review_citations,
                sentiment_summary: meta.sentiment_summary,
                sql_query: meta.sql_query,
                metadata: meta,
              };
            });

            setConversations((prev) =>
              prev.map((c) => (c.id === convId ? { ...c, messages: parsedMsgs } : c))
            );
          }
        }
      } catch (err) {
        console.warn(`Could not load messages for conversation ${convId}:`, err);
      }
    },
    []
  );

  // Save to localStorage when unauthenticated
  useEffect(() => {
    if (!isClient || conversations.length === 0 || token) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
      if (activeId) {
        localStorage.setItem(ACTIVE_CONV_KEY, activeId);
      }
    } catch (err) {
      console.error('Failed to save conversations to localStorage:', err);
    }
  }, [conversations, activeId, isClient, token]);

  const activeConversation = conversations.find((c) => c.id === activeId) || null;

  const scrollToBottom = (behavior: ScrollBehavior = 'smooth') => {
    messagesEndRef.current?.scrollIntoView({ behavior });
  };

  useEffect(() => {
    scrollToBottom();
  }, [activeConversation?.messages.length, isLoading]);

  // Handler: Select conversation & load messages if needed
  const handleSelectConversation = (id: string) => {
    setActiveId(id);
    const conv = conversations.find((c) => c.id === id);
    if (token && conv && conv.messages.length === 0) {
      loadConversationMessages(id, token);
    }
  };

  // Handler: Create New Chat
  const handleNewChat = () => {
    const newConv = createDefaultConversation();
    setConversations((prev) => [newConv, ...prev]);
    setActiveId(newConv.id);
    setSidebarOpen(false);
  };

  // Handler: Delete Conversation
  const handleDeleteConversation = async (id: string) => {
    setConversations((prev) => {
      const remaining = prev.filter((c) => c.id !== id);
      if (remaining.length === 0) {
        const fresh = createDefaultConversation();
        setActiveId(fresh.id);
        return [fresh];
      }
      if (activeId === id) {
        setActiveId(remaining[0].id);
      }
      return remaining;
    });

    if (token) {
      try {
        await fetch(`${API_BASE_URL}/api/conversations/${id}`, {
          method: 'DELETE',
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
      } catch (err) {
        console.warn(`Could not delete conversation ${id} from server:`, err);
      }
    }
  };

  // Handler: Rename Conversation
  const handleRenameConversation = async (id: string, newTitle: string) => {
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, title: newTitle, updatedAt: Date.now() } : c))
    );

    if (token) {
      try {
        await fetch(`${API_BASE_URL}/api/conversations/${id}`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ title: newTitle }),
        });
      } catch (err) {
        console.warn(`Could not rename conversation ${id} on server:`, err);
      }
    }
  };

  // Handler: Clear current active chat messages
  const handleClearActiveChat = () => {
    if (!activeId) return;
    setConversations((prev) =>
      prev.map((c) =>
        c.id === activeId ? { ...c, messages: [], updatedAt: Date.now() } : c
      )
    );
  };

  // Handler: Clear all chats
  const handleClearAllChats = () => {
    const fresh = createDefaultConversation();
    setConversations([fresh]);
    setActiveId(fresh.id);
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(ACTIVE_CONV_KEY);
  };

  // Handler: Stop generation
  const handleStopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    if (abortTimeoutRef.current) {
      clearTimeout(abortTimeoutRef.current);
      abortTimeoutRef.current = null;
    }
    setIsLoading(false);
  };

  // Helper: Request AI/Analytics answer
  const fetchAssistantReply = async (
    promptText: string,
    targetConvId: string,
    controller: AbortController
  ): Promise<Message> => {
    try {
      const conv = conversations.find((c) => c.id === targetConvId);
      const historyPayload = conv
        ? conv.messages.slice(-6).map((m) => ({
            role: m.sender,
            text: m.text,
            sql_query: m.sql_query,
          }))
        : [];

      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch(`${API_BASE_URL}/api/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          message: promptText.trim(),
          conversation_id: targetConvId,
          history: historyPayload,
        }),
        signal: controller.signal,
      });

      // Handle Quota Limit Exceeded (HTTP 429)
      if (res.status === 429) {
        const errData = await res.json().catch(() => ({}));
        setDailyUsage((prev) => (prev ? { ...prev, remaining: 0, used: prev.limit } : null));

        return {
          id: 'msg-' + Date.now(),
          sender: 'assistant',
          text: `⚠️ **Daily Question Quota Reached**\n\n${
            errData.detail ||
            'You have reached your daily quota of 15 questions. Your quota will automatically reset tomorrow at midnight UTC.'
          }\n\n*If you are an evaluator or team member requiring higher limits, please contact the administrator.*`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        };
      }

      if (res.ok) {
        const data: BackendChatResponse = await res.json();

        // Update daily usage state if returned by backend
        if (data.daily_usage) {
          setDailyUsage(data.daily_usage);
        }

        // Return real analytical response
        return {
          id: 'msg-' + Date.now(),
          sender: 'assistant',
          text: data.text,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          metrics: data.metrics,
          breakdown: data.breakdown,
          chart: data.chart,
          review_citations: data.review_citations,
          sentiment_summary: data.sentiment_summary,
          sql_query: data.sql_query,
          columns: data.columns,
          rows: data.rows,
          metadata: data.metadata,
        };
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        throw err;
      }
      console.warn('Backend API unavailable or error, falling back to mock response:', err);
    }

    // Fall back to mock response only if backend is completely offline
    const mockResult = getMockResponse(promptText);
    return {
      id: 'msg-' + Date.now(),
      sender: 'assistant',
      text: mockResult.text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      metrics: mockResult.metrics,
      breakdown: mockResult.breakdown,
    };
  };

  // Handler: Send Message
  const handleSendMessage = async (text: string) => {
    if (!text.trim() || isLoading) return;

    let targetConvId = activeId;

    if (!targetConvId || !conversations.some((c) => c.id === targetConvId)) {
      const newConv = createDefaultConversation();
      setConversations((prev) => [newConv, ...prev]);
      targetConvId = newConv.id;
      setActiveId(targetConvId);
    }

    const userMessage: Message = {
      id: 'msg-' + Date.now(),
      sender: 'user',
      text: text.trim(),
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setConversations((prev) =>
      prev.map((c) => {
        if (c.id === targetConvId) {
          const isInitial = c.messages.length === 0 || c.title === 'New Conversation';
          const newTitle = isInitial
            ? text.length > 32
              ? text.substring(0, 32) + '...'
              : text
            : c.title;

          return {
            ...c,
            title: newTitle,
            updatedAt: Date.now(),
            messages: [...c.messages, userMessage],
          };
        }
        return c;
      })
    );

    setIsLoading(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const aiMessage = await fetchAssistantReply(text, targetConvId, controller);

      setConversations((prev) =>
        prev.map((c) => {
          if (c.id === targetConvId) {
            return {
              ...c,
              updatedAt: Date.now(),
              messages: [...c.messages, aiMessage],
            };
          }
          return c;
        })
      );
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        console.error('Error getting response:', err);
      }
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  };

  // Handler: Regenerate last AI response
  const handleRegenerate = async () => {
    if (!activeConversation || activeConversation.messages.length < 2 || isLoading) return;

    const lastUserMsg = [...activeConversation.messages]
      .reverse()
      .find((m) => m.sender === 'user');

    if (!lastUserMsg) return;

    setConversations((prev) =>
      prev.map((c) => {
        if (c.id === activeId) {
          return {
            ...c,
            messages: c.messages.filter((_, idx) => idx !== c.messages.length - 1),
          };
        }
        return c;
      })
    );

    setIsLoading(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const aiMessage = await fetchAssistantReply(lastUserMsg.text, activeId || '', controller);

      setConversations((prev) =>
        prev.map((c) => {
          if (c.id === activeId) {
            return {
              ...c,
              updatedAt: Date.now(),
              messages: [...c.messages, aiMessage],
            };
          }
          return c;
        })
      );
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        console.error('Error regenerating response:', err);
      }
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  };

  const hasMessages = Boolean(activeConversation && activeConversation.messages.length > 0);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-white min-w-0">
      {/* Sidebar */}
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
        onDeleteConversation={handleDeleteConversation}
        onRenameConversation={handleRenameConversation}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen((prev) => !prev)}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      {/* Main Chat Work Area */}
      <div className="flex flex-col flex-1 h-full min-w-0 bg-white relative">
        {/* Top Header */}
        <ChatHeader
          onToggleSidebar={() => setSidebarOpen(true)}
          onNewChat={handleNewChat}
          onClearActiveChat={handleClearActiveChat}
          title={activeConversation?.title || 'Olist AI Assistant'}
          hasMessages={hasMessages}
        />

        {/* Scrollable Chat Area */}
        <div className="flex-1 overflow-y-auto flex flex-col">
          {!hasMessages ? (
            <WelcomeScreen onSelectQuestion={handleSendMessage} />
          ) : (
            <div className="py-4 space-y-1">
              {activeConversation?.messages.map((message, index) => {
                const isLastAssistant =
                  message.sender === 'assistant' &&
                  index === (activeConversation?.messages.length ?? 0) - 1;

                return (
                  <ChatMessage
                    key={message.id}
                    message={message}
                    isLastAssistant={isLastAssistant}
                    onRegenerate={handleRegenerate}
                  />
                );
              })}

              {isLoading && <LoadingIndicator onStop={handleStopGeneration} />}

              <div ref={messagesEndRef} className="h-4" />
            </div>
          )}
        </div>

        {/* Bottom Sticky Chat Input */}
        <ChatInput
          onSendMessage={handleSendMessage}
          isLoading={isLoading}
          onStop={handleStopGeneration}
        />
      </div>

      {/* Settings Modal */}
      <SettingsModal
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onClearAllChats={handleClearAllChats}
      />
    </div>
  );
}
