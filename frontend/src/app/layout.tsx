import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ListingIQ - AI Product Listing Optimization Engine",
  description:
    "Optimize your ecommerce product listings with an 8-agent AI pipeline. Get scores, recommendations, and optimized rewrites.",
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
