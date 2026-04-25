import type { Metadata } from 'next';
import { Providers } from './providers';
import './globals.css';

export const metadata: Metadata = {
  title: 'LMSR Preclinical Markets',
  description:
    'Dual-layer tokenized milestone payment rights with LS-LMSR prediction market price discovery. Testnet demo on Base Sepolia + Ethereum Sepolia.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
