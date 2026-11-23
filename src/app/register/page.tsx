'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { BarChart2, Mail, Lock, User, ArrowRight, AlertCircle, CheckCircle, Loader2, Eye, EyeOff } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

export default function RegisterPage() {
  const router = useRouter();
  const { signUp } = useAuth();
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isAlreadyRegistered, setIsAlreadyRegistered] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;

    setError(null);
    setIsAlreadyRegistered(false);
    setSuccess(null);

    const trimmedEmail = email.trim();
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(trimmedEmail)) {
      setError('Please enter a valid email address.');
      return;
    }

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
      const res = await signUp(trimmedEmail, password, displayName.trim());
      if (res.alreadyExists) {
        setIsAlreadyRegistered(true);
        setError('This email address is already registered. Please sign in or reset your password.');
        setIsSubmitting(false);
      } else if (res.error) {
        if (
          res.error.toLowerCase().includes('already registered') ||
          res.error.toLowerCase().includes('already exists')
        ) {
          setIsAlreadyRegistered(true);
          setError('This email address is already registered. Please sign in or reset your password.');
        } else {
          setError(res.error);
        }
        setIsSubmitting(false);
      } else {
        setSuccess('Registration successful! A confirmation email has been sent to your address. Please click the link in your email to confirm your account and sign in.');
        setIsSubmitting(false);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to create account.');
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
          Create your account
        </h2>
        <p className="mt-1.5 text-xs text-gray-500">
          Get started with your free multi-user analytics workspace
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-6 shadow-sm border border-gray-200 sm:rounded-xl sm:px-10">
          {isAlreadyRegistered ? (
            <div className="mb-5 p-3.5 rounded-lg bg-amber-50 border border-amber-200 flex flex-col gap-2.5 text-xs text-amber-900">
              <div className="flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                <div className="space-y-0.5">
                  <p className="font-semibold text-amber-900">Account already exists</p>
                  <p className="text-amber-800 leading-relaxed">
                    This email address is already registered. Please sign in or reset your password.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3 pl-6 pt-1 text-xs">
                <Link
                  href="/login"
                  className="font-semibold text-[#169b75] hover:text-[#0f7a5c] hover:underline"
                >
                  Sign in &rarr;
                </Link>
                <span className="text-amber-300">|</span>
                <Link
                  href="/forgot-password"
                  className="font-semibold text-gray-700 hover:text-gray-900 hover:underline"
                >
                  Reset password
                </Link>
              </div>
            </div>
          ) : error ? (
            <div className="mb-5 p-3 rounded-lg bg-red-50 border border-red-200 flex items-start gap-2.5 text-xs text-red-700">
              <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          ) : null}

          {success && (
            <div className="mb-5 p-3 rounded-lg bg-green-50 border border-green-200 flex items-start gap-2.5 text-xs text-[#0f7a5c]">
              <CheckCircle className="w-4 h-4 text-[#169b75] shrink-0 mt-0.5" />
              <span>{success}</span>
            </div>
          )}

          <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Full Name
              </label>
              <div className="relative">
                <User className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="text"
                  required
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Alex Santos"
                  className="w-full bg-white border border-gray-300 rounded-lg pl-9 pr-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-[#169b75] focus:ring-1 focus:ring-[#169b75] transition-colors"
                />
              </div>
            </div>

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
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Password
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

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Confirm Password
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type={showConfirmPassword ? 'text' : 'password'}
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Repeat your password"
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

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full mt-2 flex items-center justify-center gap-2 py-2.5 px-4 border border-transparent rounded-lg text-sm font-medium text-white bg-[#169b75] hover:bg-[#0f7a5c] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#169b75] disabled:opacity-50 transition-colors shadow-sm cursor-pointer"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Creating account...</span>
                </>
              ) : (
                <>
                  <span>Create Account</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          <div className="mt-6 pt-5 border-t border-gray-100 text-center text-xs text-gray-600">
            Already have an account?{' '}
            <Link href="/login" className="font-semibold text-[#169b75] hover:underline">
              Sign in
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
