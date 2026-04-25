import { getDefaultConfig } from '@rainbow-me/rainbowkit';
import { baseSepolia, sepolia } from 'wagmi/chains';
import { http } from 'viem';

export const wagmiConfig = getDefaultConfig({
  appName: 'LMSR Preclinical Markets',
  projectId: process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID ?? 'YOUR_PROJECT_ID',
  chains: [baseSepolia, sepolia],
  transports: {
    [baseSepolia.id]: http('https://sepolia.base.org'),
    [sepolia.id]: http('https://ethereum-sepolia-rpc.publicnode.com'),
  },
  ssr: false,  // disable SSR — wagmi runs only on the client
});