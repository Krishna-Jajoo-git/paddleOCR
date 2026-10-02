import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Navbar } from "@/components/Navbar";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Prescription Intelligence | AI Medical Record Extraction & OCR Platform",
  description:
    "Production-ready healthcare OCR platform powered by PaddleOCR-VL and Google Gemini for extracting, structuring, and clinically validating medical prescriptions.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased dark`}
    >
      <body className="min-h-full flex flex-col bg-[#080d18] text-slate-100 font-sans">
        <Navbar />
        <main className="flex-1 pb-16">{children}</main>
        <footer className="border-t border-slate-800/80 bg-slate-950/60 py-6 text-center text-xs text-slate-500">
          <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-3">
            <div>
              Prescription Intelligence Platform • Powered by PaddleOCR-VL & Google Gemini
            </div>
            <div className="text-slate-400">
              Clinical Decision Support • Authorized Medical Personnel Only
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
