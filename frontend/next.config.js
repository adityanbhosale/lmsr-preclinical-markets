/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  webpack: (config) => {
    // Suppress warnings about optional Node.js-only deps (pino-pretty, lokijs, encoding)
    // that wagmi / walletconnect pull in but never actually use in the browser.
    config.externals.push('pino-pretty', 'lokijs', 'encoding');
    return config;
  },
};

module.exports = nextConfig;
