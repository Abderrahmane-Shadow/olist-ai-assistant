import { NextResponse } from 'next/server';
import { createServerClient } from '@supabase/ssr';
import { cookies } from 'next/headers';

export async function GET(request: Request) {
  const requestUrl = new URL(request.url);
  const code = requestUrl.searchParams.get('code');
  const type = requestUrl.searchParams.get('type');
  const errorParam = requestUrl.searchParams.get('error');
  const errorDesc = requestUrl.searchParams.get('error_description');
  let next = requestUrl.searchParams.get('next') ?? '/';
  const forwardedHost = request.headers.get('x-forwarded-host');
  const isLocalEnv = process.env.NODE_ENV === 'development';
  let origin = requestUrl.origin;
  if (!isLocalEnv && forwardedHost) {
    origin = `https://${forwardedHost}`;
  }

  const isRecovery = type === 'recovery' || next.includes('reset-password');

  // Handle provider error passed in query parameters (e.g. expired link)
  if (errorParam || errorDesc) {
    const errorMsg = errorDesc || errorParam || 'Authentication link is invalid or has expired.';
    if (isRecovery) {
      return NextResponse.redirect(`${origin}/reset-password?error=${encodeURIComponent(errorMsg)}`);
    }
    return NextResponse.redirect(`${origin}/login?error=${encodeURIComponent(errorMsg)}`);
  }

  if (isRecovery && next === '/') {
    next = '/reset-password';
  }

  if (code) {
    const cookieStore = cookies();
    const response = NextResponse.redirect(`${origin}${next}`);

    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://demo-placeholder.supabase.co',
      process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
        'demo-placeholder-publishable-key',
      {
        cookies: {
          getAll() {
            return cookieStore.getAll();
          },
          setAll(cookiesToSet) {
            cookiesToSet.forEach(({ name, value, options }) => {
              cookieStore.set(name, value, options);
              response.cookies.set(name, value, options);
            });
          },
        },
      }
    );

    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return response;
    }
    console.error('Supabase exchangeCodeForSession failed in callback:', error.message);

    if (isRecovery) {
      return NextResponse.redirect(
        `${origin}/reset-password?error=${encodeURIComponent(
          error.message || 'Could not verify recovery link. It may have expired or already been used.'
        )}`
      );
    }
  }

  // Return the user to login with informative error message
  return NextResponse.redirect(
    `${origin}/login?error=Could%20not%20verify%20authentication%20code.%20Please%20try%20signing%20in%20directly.`
  );
}
