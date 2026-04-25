'use client';

import dynamic from 'next/dynamic';
import { ReactNode } from 'react';

// Dynamically import the actual provider tree with SSR explicitly disabled.
// This prevents WalletConnect's storage layer from running localStorage
// calls during server-side module initialization.
const ClientProviders = dynamic(() => import('./ClientProviders'), {
  ssr: false,
});

export function Providers({ children }: { children: ReactNode }) {
  return <ClientProviders>{children}</ClientProviders>;
}