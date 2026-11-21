import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "QueryPal — Text to SQL",
  description: "Ask questions about the Pagila database in plain English.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
