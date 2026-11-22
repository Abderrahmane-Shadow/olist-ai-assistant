'use client';

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { User, Session } from '@supabase/supabase-js';
import { createClient } from '@/lib/supabase/client';

export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  role: 'user' | 'admin';
  daily_question_limit: number;
}

export interface DailyUsage {
  used: number;
  limit: number;
  remaining: number;
}

interface AuthContextType {
  user: User | null;
  profile: UserProfile | null;
  session: Session | null;
  token: string | null;
  dailyUsage: DailyUsage | null;
  isLoading: boolean;
  signIn: (email: string, password: string) => Promise<{ error?: string }>;
  signUp: (email: string, password: string, displayName?: string) => Promise<{ error?: string }>;
  signInWithGoogle: () => Promise<{ error?: string }>;
  signOut: () => Promise<void>;
  resetPassword: (email: string) => Promise<{ error?: string }>;
  updatePassword: (newPassword: string) => Promise<{ error?: string }>;
  setDailyUsage: React.Dispatch<React.SetStateAction<DailyUsage | null>>;
  refreshUsage: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [supabase] = useState(() => createClient());
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [dailyUsage, setDailyUsage] = useState<DailyUsage | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchProfileAndUsage = useCallback(async (accessToken: string) => {
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const res = await fetch(`${apiBase}/api/auth/me`, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });
      if (res.ok) {
        const data = await res.json();
        setProfile(data.profile);
        setDailyUsage(data.daily_usage);
      }
    } catch (err) {
      console.warn('Could not fetch backend profile/usage:', err);
    }
  }, []);

  const refreshUsage = useCallback(async () => {
    if (token) {
      await fetchProfileAndUsage(token);
    }
  }, [token, fetchProfileAndUsage]);

  useEffect(() => {
    const initAuth = async () => {
      try {
        // 1. Check if arriving with an authorization code in URL query params
        if (typeof window !== 'undefined') {
          const urlParams = new URLSearchParams(window.location.search);
          const code = urlParams.get('code');
          if (code) {
            try {
              const { data, error } = await supabase.auth.exchangeCodeForSession(code);
              if (!error && data?.session) {
                setSession(data.session);
                setUser(data.session.user);
                setToken(data.session.access_token);

                // Clean the ?code= query param from the browser URL without reload
                urlParams.delete('code');
                const remainingQuery = urlParams.toString();
                const cleanUrl =
                  window.location.pathname +
                  (remainingQuery ? `?${remainingQuery}` : '') +
                  window.location.hash;
                window.history.replaceState({}, document.title, cleanUrl);

                if (data.session.access_token) {
                  await fetchProfileAndUsage(data.session.access_token);
                }
                setIsLoading(false);
                return;
              }
            } catch (exchangeErr) {
              console.warn('Client-side code exchange exception:', exchangeErr);
            }
          }
        }

        // 2. Load existing session from cookies
        const { data: { session } } = await supabase.auth.getSession();
        setSession(session);
        setUser(session?.user ?? null);
        const accessToken = session?.access_token ?? null;
        setToken(accessToken);

        if (accessToken) {
          await fetchProfileAndUsage(accessToken);
        }
      } catch (err) {
        console.error('Supabase getSession error:', err);
      } finally {
        setIsLoading(false);
      }
    };

    initAuth();

    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (_event, newSession) => {
      setSession(newSession);
      setUser(newSession?.user ?? null);
      const accessToken = newSession?.access_token ?? null;
      setToken(accessToken);

      if (accessToken) {
        await fetchProfileAndUsage(accessToken);
      } else {
        setProfile(null);
        setDailyUsage(null);
      }
      setIsLoading(false);
    });

    return () => {
      subscription.unsubscribe();
    };
  }, [supabase, fetchProfileAndUsage]);

  const signIn = async (email: string, password: string) => {
    try {
      const { data, error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) return { error: error.message };

      if (data?.session) {
        setSession(data.session);
        setUser(data.session.user);
        setToken(data.session.access_token);
        if (data.session.access_token) {
          await fetchProfileAndUsage(data.session.access_token);
        }
      }
      return {};
    } catch (err: any) {
      return { error: err.message || 'An unexpected error occurred during sign in.' };
    }
  };

  const signUp = async (email: string, password: string, displayName?: string) => {
    try {
      const redirectUrl =
        typeof window !== 'undefined' ? `${window.location.origin}/auth/callback` : undefined;
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: redirectUrl,
          data: {
            display_name: displayName || email.split('@')[0],
          },
        },
      });
      if (error) return { error: error.message };

      if (data?.session) {
        setSession(data.session);
        setUser(data.session.user);
        setToken(data.session.access_token);
        if (data.session.access_token) {
          await fetchProfileAndUsage(data.session.access_token);
        }
      }
      return {};
    } catch (err: any) {
      return { error: err.message || 'An unexpected error occurred during sign up.' };
    }
  };

  const signInWithGoogle = async () => {
    try {
      const redirectUrl =
        typeof window !== 'undefined' ? `${window.location.origin}/auth/callback` : undefined;
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: redirectUrl,
          queryParams: {
            access_type: 'offline',
            prompt: 'consent',
          },
        },
      });
      if (error) return { error: error.message };
      return {};
    } catch (err: any) {
      return { error: err.message || 'An unexpected error occurred during Google sign in.' };
    }
  };

  const signOut = async () => {
    try {
      await supabase.auth.signOut();
    } catch (err) {
      console.warn('Error during signOut:', err);
    }
    setUser(null);
    setSession(null);
    setToken(null);
    setProfile(null);
    setDailyUsage(null);
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
  };

  const resetPassword = async (email: string) => {
    try {
      const redirectUrl = typeof window !== 'undefined' ? `${window.location.origin}/reset-password` : undefined;
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: redirectUrl,
      });
      if (error) {
        const lower = error.message.toLowerCase();
        if (lower.includes('rate limit') || lower.includes('rate_limit') || lower.includes('too many')) {
          return {
            error:
              'For security reasons, password reset requests are temporarily rate-limited by Supabase. Please wait a few minutes before requesting another reset link.',
          };
        }
        return { error: error.message };
      }
      return {};
    } catch (err: any) {
      const msg = err?.message || '';
      const lower = msg.toLowerCase();
      if (lower.includes('rate limit') || lower.includes('rate_limit') || lower.includes('too many')) {
        return {
          error:
            'For security reasons, password reset requests are temporarily rate-limited by Supabase. Please wait a few minutes before requesting another reset link.',
        };
      }
      return { error: msg || 'Failed to send password reset email.' };
    }
  };

  const updatePassword = async (newPassword: string) => {
    try {
      const { error } = await supabase.auth.updateUser({ password: newPassword });
      if (error) return { error: error.message };
      return {};
    } catch (err: any) {
      return { error: err.message || 'Failed to update password.' };
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        profile,
        session,
        token,
        dailyUsage,
        isLoading,
        signIn,
        signUp,
        signInWithGoogle,
        signOut,
        resetPassword,
        updatePassword,
        setDailyUsage,
        refreshUsage,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
