'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { BarChart2, Mail, Lock, ArrowRight, AlertCircle, CheckCircle, Loader2, Eye, EyeOff } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

export default function LoginPage() {
  const router = useRouter();
  const { user, signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // If already authenticated, redirect to chat home
  useEffect(() => {
    if (user) {
      router.replace('/');
    }
  }, [user, router]);

  // Display error or success message from URL parameters if redirected
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const urlError = params.get('error');
      if (urlError) {
        setError(decodeURIComponent(urlError));
      }
      const urlMsg = params.get('message');
      if (urlMsg) {
        setSuccessMessage(decodeURIComponent(urlMsg));
      }
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;

    setError(null);
    setIsSubmitting(true);

    try {
      const res = await signIn(email.trim(), password);
      if (res.error) {
        setError(res.error);
        setIsSubmitting(false);
        // Do NOT reset email and password fields on error
        return;
      }

      // Successful login: navigate to chat home and update server state
      router.push('/');
      router.refresh();
    } catch (err: any) {
      setError(err?.message || 'Failed to sign in. Please check your credentials.');
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f8fafc] flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        <Link href="/" className="inline-flex items-center gap-2.5">
          <div className="w-10 h-10 rounded-lg bg-[#169b75] flex items-center justify-center shadow-sm">
            <BarChart2 className="w-6 h-6 text-white" />
          </div>
          <span className="text-xl font-bold text-gray-900 tracking-tight">Olist AI Assistant</span>
        </Link>
        <h2 className="mt-4 text-2xl font-bold tracking-tight text-gray-900">
          Sign in to your account
        </h2>
        <p className="mt-1.5 text-xs text-gray-500">
          Access real-time Brazilian e-commerce analytics, reviews, and insights
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-6 shadow-sm border border-gray-200 sm:rounded-xl sm:px-10">
          {error && (
            <div className="mb-5 p-3 rounded-lg bg-red-50 border border-red-200 flex items-start gap-2.5 text-xs text-red-700">
              <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {successMessage && (
            <div className="mb-5 p-3 rounded-lg bg-green-50 border border-green-200 flex items-start gap-2.5 text-xs text-[#0f7a5c]">
              <CheckCircle className="w-4 h-4 text-[#169b75] shrink-0 mt-0.5" />
              <span>{successMessage}</span>
            </div>
          )}

          <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Email address
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="analyst@olist.com"
                  className="w-full bg-white border border-gray-300 rounded-lg pl-9 pr-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-[#169b75] focus:ring-1 focus:ring-[#169b75] transition-colors"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-medium text-gray-700">
                  Password
                </label>
                <Link
                  href="/forgot-password"
                  className="text-xs text-[#169b75] hover:underline font-medium"
                >
                  Forgot password?
                </Link>
              </div>
              <div className="relative">
                <Lock className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-white border border-gray-300 rounded-lg pl-9 pr-10 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-[#169b75] focus:ring-1 focus:ring-[#169b75] transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 focus:outline-none cursor-pointer"
                  title={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full mt-2 flex items-center justify-center gap-2 py-2.5 px-4 border border-transparent rounded-lg text-sm font-medium text-white bg-[#169b75] hover:bg-[#0f7a5c] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#169b75] disabled:opacity-50 transition-colors shadow-sm cursor-pointer"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Signing in...</span>
                </>
              ) : (
                <>
                  <span>Sign in</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          <div className="mt-6 pt-5 border-t border-gray-100 text-center text-xs text-gray-600">
            Don&apos;t have an account?{' '}
            <Link href="/register" className="font-semibold text-[#169b75] hover:underline">
              Register now
            </Link>
          </div>
        </div>

        <div className="mt-6 text-center text-xs text-gray-400">
          Olist Analytics AI &copy; {new Date().getFullYear()} &middot; Powered by PostgreSQL & Gemini
        </div>
      </div>
    </div>
  );
}
