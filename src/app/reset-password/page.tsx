'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  BarChart2,
  Lock,
  ArrowRight,
  AlertCircle,
  CheckCircle,
  Loader2,
  Eye,
  EyeOff,
  Check,
  X as XIcon,
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { createClient } from '@/lib/supabase/client';

export default function ResetPasswordPage() {
  const router = useRouter();
  const { session, user, isLoading: isAuthLoading, updatePassword, signOut } = useAuth();

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const [isVerifying, setIsVerifying] = useState(true);
  const [verificationError, setVerificationError] = useState<string | null>(null);
  const [hasValidSession, setHasValidSession] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Check URL parameters (query and hash) for recovery tokens or errors
  useEffect(() => {
    let mounted = true;

    const verifyRecoveryState = async () => {
      try {
        if (typeof window === 'undefined') return;

        const urlParams = new URLSearchParams(window.location.search);
        const hash = window.location.hash;

        // Check for error parameters in search or hash
        const urlError = urlParams.get('error') || urlParams.get('error_code');
        const urlErrorDesc = urlParams.get('error_description');

        let hashErrorDesc: string | null = null;
        if (hash) {
          const hashParams = new URLSearchParams(hash.replace(/^#/, ''));
          hashErrorDesc = hashParams.get('error_description') || hashParams.get('error');
        }

        const rawErrorDesc = urlErrorDesc || hashErrorDesc || urlError;
        if (rawErrorDesc) {
          const decoded = decodeURIComponent(rawErrorDesc.replace(/\+/g, ' '));
          if (mounted) {
            setVerificationError(
              decoded.includes('expired') || decoded.includes('invalid')
                ? 'This password reset link is invalid, expired, or has already been used. Please request a new recovery link.'
                : decoded
            );
            setIsVerifying(false);
          }
          return;
        }

        const supabase = createClient();

        // 1. If authorization code is present in query, exchange it client-side
        const code = urlParams.get('code');
        if (code) {
          try {
            const { data, error: exchangeErr } = await supabase.auth.exchangeCodeForSession(code);
            if (exchangeErr) {
              if (mounted) {
                setVerificationError(
                  'The password recovery code is invalid or has expired. Please request a new reset link.'
                );
                setIsVerifying(false);
              }
              return;
            }
            if (data?.session && mounted) {
              setHasValidSession(true);
              setIsVerifying(false);
              // Clean the code from URL without refreshing
              urlParams.delete('code');
              const remaining = urlParams.toString();
              const cleanUrl =
                window.location.pathname + (remaining ? `?${remaining}` : '') + window.location.hash;
              window.history.replaceState({}, document.title, cleanUrl);
              return;
            }
          } catch (codeErr: any) {
            console.warn('Code exchange error on reset-password:', codeErr);
          }
        }

        // 2. Check if a session already exists
        const { data: sessionData } = await supabase.auth.getSession();
        if (sessionData?.session) {
          if (mounted) {
            setHasValidSession(true);
            setIsVerifying(false);
          }
          return;
        }

        // 3. Listen to auth state change (e.g. hash token exchange)
        const { data: authListener } = supabase.auth.onAuthStateChange((event, newSession) => {
          if (mounted) {
            if (event === 'PASSWORD_RECOVERY' || newSession) {
              setHasValidSession(true);
              setIsVerifying(false);
            }
          }
        });

        // Give hash parsing a brief window to complete
        const timer = setTimeout(() => {
          if (mounted) {
            if (!sessionData?.session && !user && !session) {
              setVerificationError(
                'No active password reset session found. Please click the recovery link sent to your email or request a new one.'
              );
            } else {
              setHasValidSession(true);
            }
            setIsVerifying(false);
          }
        }, 1200);

        return () => {
          clearTimeout(timer);
          authListener?.subscription?.unsubscribe();
        };
      } catch (err: any) {
        if (mounted) {
          setVerificationError(err?.message || 'Could not verify recovery session.');
          setIsVerifying(false);
        }
      }
    };

    verifyRecoveryState();

    return () => {
      mounted = false;
    };
  }, [user, session]);

  // Sync session state from AuthContext when available
  useEffect(() => {
    if (session || user) {
      setHasValidSession(true);
      setVerificationError(null);
      setIsVerifying(false);
    }
  }, [session, user]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (password.length < 6) {
      setError('Password must be at least 6 characters long.');
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setIsSubmitting(true);

    try {
      const res = await updatePassword(password);
      if (res.error) {
        setError(res.error);
        setIsSubmitting(false);
      } else {
        setSuccess('Password updated successfully! Redirecting to sign in...');
        setTimeout(async () => {
          try {
            await signOut();
          } catch (e) {
            console.warn('Sign out post-reset error:', e);
          }
          router.push(
            '/login?message=Password%20updated%20successfully.%20Please%20sign%20in%20with%20your%20new%20password.'
          );
        }, 1800);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to update password.');
      setIsSubmitting(false);
    }
  };

  const isLengthValid = password.length >= 6;
  const isMatch = password.length > 0 && password === confirmPassword;

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
          Set new password
        </h2>
        <p className="mt-1.5 text-xs text-gray-500">
          Choose a secure password for your account
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-6 shadow-sm border border-gray-200 sm:rounded-xl sm:px-10">
          {/* Loading verification state */}
          {isVerifying && (
            <div className="py-8 flex flex-col items-center justify-center text-center space-y-3">
              <Loader2 className="w-7 h-7 text-[#169b75] animate-spin" />
              <p className="text-xs text-gray-600 font-medium">
                Verifying password recovery session...
              </p>
            </div>
          )}

          {/* Verification error (e.g. expired link) */}
          {!isVerifying && verificationError && (
            <div className="space-y-4">
              <div className="p-3.5 rounded-lg bg-red-50 border border-red-200 flex items-start gap-2.5 text-xs text-red-700">
                <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
                <span>{verificationError}</span>
              </div>
              <Link
                href="/forgot-password"
                className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg text-sm font-medium text-white bg-[#169b75] hover:bg-[#0f7a5c] transition-colors shadow-sm"
              >
                <span>Request New Reset Link</span>
                <ArrowRight className="w-4 h-4" />
              </Link>
              <div className="text-center pt-2">
                <Link href="/login" className="text-xs text-gray-500 hover:text-gray-700 hover:underline">
                  Back to Sign In
                </Link>
              </div>
            </div>
          )}

          {/* Form when session is valid */}
          {!isVerifying && !verificationError && (
            <>
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
                {/* New Password */}
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">
                    New Password
                  </label>
                  <div className="relative">
                    <Lock className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="At least 6 characters"
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

                {/* Confirm New Password */}
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">
                    Confirm New Password
                  </label>
                  <div className="relative">
                    <Lock className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                    <input
                      type={showConfirmPassword ? 'text' : 'password'}
                      required
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="Repeat new password"
                      className="w-full bg-white border border-gray-300 rounded-lg pl-9 pr-10 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-[#169b75] focus:ring-1 focus:ring-[#169b75] transition-colors"
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 focus:outline-none cursor-pointer"
                      title={showConfirmPassword ? 'Hide password' : 'Show password'}
                    >
                      {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {/* Password Strength Guidance */}
                <div className="p-3 bg-gray-50 rounded-lg border border-gray-100 space-y-1.5 text-xs">
                  <div className="flex items-center gap-2">
                    {isLengthValid ? (
                      <Check className="w-3.5 h-3.5 text-[#169b75]" />
                    ) : (
                      <XIcon className="w-3.5 h-3.5 text-gray-300" />
                    )}
                    <span className={isLengthValid ? 'text-gray-800 font-medium' : 'text-gray-500'}>
                      At least 6 characters
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    {isMatch ? (
                      <Check className="w-3.5 h-3.5 text-[#169b75]" />
                    ) : (
                      <XIcon className="w-3.5 h-3.5 text-gray-300" />
                    )}
                    <span className={isMatch ? 'text-gray-800 font-medium' : 'text-gray-500'}>
                      Passwords match
                    </span>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={isSubmitting || !isLengthValid || !isMatch}
                  className="w-full mt-2 flex items-center justify-center gap-2 py-2.5 px-4 border border-transparent rounded-lg text-sm font-medium text-white bg-[#169b75] hover:bg-[#0f7a5c] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#169b75] disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm cursor-pointer"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Updating password...</span>
                    </>
                  ) : (
                    <>
                      <span>Update Password</span>
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </form>

              <div className="mt-6 pt-5 border-t border-gray-100 text-center text-xs text-gray-600">
                Remember your credentials?{' '}
                <Link href="/login" className="font-semibold text-[#169b75] hover:underline">
                  Sign in
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
