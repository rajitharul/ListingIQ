import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sitescore - AI Marketing Benchmarking Engine",
  description:
    "Multi-dimensional, multi-agent competitive benchmarking for marketing content",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
