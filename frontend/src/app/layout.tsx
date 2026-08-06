import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "RoboWeaver Control Center",
    template: "%s | RoboWeaver",
  },
  description: "Compile, verify, simulate, and operate portable robot skills with RoboIR.",
  applicationName: "RoboWeaver",
};

export const viewport = {
  themeColor: "#070b12",
  colorScheme: "dark",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
