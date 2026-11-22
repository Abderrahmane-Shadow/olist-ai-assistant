'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { BarChart2, Mail, ArrowRight, AlertCircle, CheckCircle, Loader2 } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

export default function ForgotPasswordPage() {
  const { resetPassword } = useAuth();
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  // 60-second cooldown timer
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => {
      setCooldown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting || cooldown > 0 || !email.trim()) return;

    setError(null);
    setSuccess(null);
    setIsSubmitting(true);

    try {
      const res = await resetPassword(email.trim());
      if (res.error) {
        const isRateLimit =
          res.error.toLowerCase().includes('rate') ||
          res.error.toLowerCase().includes('limit') ||
          res.error.toLowerCase().includes('wait') ||
          res.error.toLowerCase().includes('seconds');

        if (isRateLimit) {
          setError(
            'For security, password reset requests are temporarily rate-limited. Please wait 60 seconds before requesting another recovery email.'
          );
          setCooldown(60);
        } else {
          setError(res.error);
        }
      } else {
        setSuccess('Password reset link sent! Check your email inbox for recovery instructions.');
        setCooldown(60);
      }
    } catch (err: any) {
      const msg = err?.message || 'Failed to send reset link.';
      if (
        msg.toLowerCase().includes('rate') ||
        msg.toLowerCase().includes('limit') ||
        msg.toLowerCase().includes('wait')
      ) {
        setError(
          'For security, password reset requests are temporarily rate-limited. Please wait 60 seconds before requesting another recovery email.'
        );
        setCooldown(60);
      } else {
        setError(msg);
      }
    } finally {
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
          Reset your password
        </h2>
        <p className="mt-1.5 text-xs text-gray-500">
          Enter your email and we will send you a recovery link
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

          {success && (
            <div className="mb-5 p-3 rounded-lg bg-green-50 border border-green-200 flex items-start gap-2.5 text-xs text-[#0f7a5c]">
              <CheckCircle className="w-4 h-4 text-[#169b75] shrink-0 mt-0.5" />
              <span>{success}</span>
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

            <button
              type="submit"
              disabled={isSubmitting || cooldown > 0 || !email.trim()}
              className="w-full mt-2 flex items-center justify-center gap-2 py-2.5 px-4 border border-transparent rounded-lg text-sm font-medium text-white bg-[#169b75] hover:bg-[#0f7a5c] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#169b75] disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Sending reset link...</span>
                </>
              ) : cooldown > 0 ? (
                <span>Resend available in {cooldown}s</span>
              ) : (
                <>
                  <span>Send Reset Link</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          <div className="mt-6 pt-5 border-t border-gray-100 text-center text-xs text-gray-600">
            Remembered your password?{' '}
            <Link href="/login" className="font-semibold text-[#169b75] hover:underline">
              Sign in
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
