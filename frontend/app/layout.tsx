import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'LedgerCore Console — High-Concurrency Financial Payment Engine',
  description: 'Multi-tenant double-entry ledger platform with strict mathematical conservation and idempotency protection.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-50 text-slate-900 min-h-screen font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
