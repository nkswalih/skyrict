/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@skyrict/api-client", "@skyrict/auth", "@skyrict/ui"],
};

module.exports = nextConfig;
