/** @type {import('next').NextConfig} */
const nextConfig = {
    reactStrictMode: true,
    transpilePackages: ['recharts'],
    images: {
        unoptimized: true,
    },
};

module.exports = nextConfig;
