import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/context/AuthContext';

export const metadata: Metadata = {
  title: 'Olist AI Assistant | E-Commerce Analytics',
  description: 'Intelligent AI assistant for Brazilian e-commerce analytics on the Olist dataset.',
  icons: { icon: '/favicon.ico' },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full bg-white text-gray-900 antialiased selection:bg-green-100 selection:text-green-900">
        <AuthProvider>
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
