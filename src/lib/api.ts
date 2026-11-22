/**
 * Utility for resolving backend API endpoint URLs in Vercel multi-service architecture.
 *
 * - On the client (browser): Defaults to '' (relative paths like `/api/...`), which
 *   Vercel rewrites directly to the `olist-ai-backend` service under the same domain.
 * - On the server (Next.js server functions/SSR): Uses the bound `process.env.BACKEND_URL`
 *   injected by Vercel for internal private service-to-service communication.
 * - Standalone local dev: Falls back to `process.env.NEXT_PUBLIC_API_URL` or `http://localhost:8000`.
 */
export function getApiBaseUrl(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL.replace(/\/+$/, '');
  }

  // Browser execution: use same-origin relative path routed via Vercel rewrites
  if (typeof window !== 'undefined') {
    return '';
  }

  // Server-side execution in Vercel functions: use internal service binding
  if (process.env.BACKEND_URL) {
    return process.env.BACKEND_URL.replace(/\/+$/, '');
  }

  // In production builds where BACKEND_URL is only available at runtime, default to relative
  if (process.env.NODE_ENV === 'production') {
    return '';
  }

  // Standalone local development fallback
  return 'http://localhost:8000';
}
