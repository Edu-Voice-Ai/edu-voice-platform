import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { DataStoreProvider } from "@/hooks/useDataStore";
import { AuthProvider } from "@/hooks/useAuth";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Edu-Voice-AI | AI Admission Counsellor for Educational Institutions",
  description:
    "Launch your educational institution's 24/7 multilingual AI Admission Agent in minutes. Automated phone enquiries, verified knowledge RAG, lead qualification, and human counsellor handoff.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full">
      <body className={`${inter.className} min-h-full flex flex-col bg-slate-50 text-slate-900 antialiased`}>
        <AuthProvider>
          <DataStoreProvider>{children}</DataStoreProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
