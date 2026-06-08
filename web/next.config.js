/** @type {import('next').NextConfig} */
const nextConfig = {
    reactStrictMode: true,
    transpilePackages: ['recharts'],
    typescript: {
        ignoreBuildErrors: true,
    },
    images: {
        unoptimized: true,
    },
    /* The dashboard moved from /dashboard-v2 to /dashboard. Redirect old links
     * (query string — e.g. ?device= — is preserved automatically). */
    async redirects() {
        return [
            { source: '/dashboard-v2', destination: '/dashboard', permanent: true },
            { source: '/dashboard-v2/:path*', destination: '/dashboard/:path*', permanent: true },
        ];
    },
};

module.exports = nextConfig;
