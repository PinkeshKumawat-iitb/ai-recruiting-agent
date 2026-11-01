import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "NexaHire — AI Recruiting Agent", description: "A smarter way to find, interview, and hire great people." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
