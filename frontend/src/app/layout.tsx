import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "HormuzFlow | Strait of Hormuz Maritime Intelligence & Oil Price Signal Terminal",
  description:
    "Real-time Strait of Hormuz crude & product oil tanker intelligence correlating outbound laden flows, TSS congestion, and dark-fleet AIS anomalies with Brent & WTI crude oil price swings.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} font-sans antialiased bg-[#0B0F19] text-[#F1F5F9] selection:bg-sky-500/25 selection:text-sky-100`}
      >
        {children}
      </body>
    </html>
  );
}
