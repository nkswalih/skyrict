import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Skyrict",
  description: "AI-native business operations platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
