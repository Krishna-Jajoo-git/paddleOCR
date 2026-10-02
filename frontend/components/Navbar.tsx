"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Stethoscope, Upload, Activity, ShieldCheck, FileText, CheckCircle2, AlertCircle, RefreshCw } from "lucide-react";
import { clientApi } from "@/lib/api";
import { HealthResponse } from "@/lib/types";

export function Navbar() {
  const pathname = usePathname();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState(false);

  const checkStatus = async () => {
    try {
      setHealthLoading(true);
      const res = await clientApi.checkHealth();
      setHealth(res);
      setHealthError(false);
    } catch {
      setHealthError(true);
    } finally {
      setHealthLoading(false);
    }
  };

  useEffect(() => {
    checkStatus();
    const interval = setInterval(checkStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const navLinks = [
    { href: "/", label: "Dashboard", icon: Activity },
    { href: "/upload", label: "Process Prescription", icon: Upload },
  ];

  return (
    <header className="sticky top-0 z-50 w-full border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Platform Name */}
          <div className="flex items-center gap-3">
            <Link href="/" className="flex items-center gap-2.5 group">
              <div className="p-2 rounded-xl bg-gradient-to-tr from-cyan-600 to-teal-500 text-white shadow-lg shadow-cyan-500/20 group-hover:scale-105 transition-transform">
                <Stethoscope className="w-5 h-5" />
              </div>
              <div>
                <span className="text-lg font-bold tracking-tight text-white flex items-center gap-1.5">
                  Prescription<span className="text-cyan-400">Intelligence</span>
                </span>
                <span className="text-[10px] text-slate-400 block -mt-1 font-medium tracking-wider uppercase">
                  PaddleOCR-VL + Gemini Clinical OCR
                </span>
              </div>
            </Link>
          </div>

          {/* Nav Items */}
          <nav className="hidden md:flex items-center gap-1">
            {navLinks.map((link) => {
              const Icon = link.icon;
              const isActive = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all ${
                    isActive
                      ? "bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 shadow-sm"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {link.label}
                </Link>
              );
            })}
          </nav>

          {/* Live Backend Status */}
          <div className="flex items-center gap-3">
            <div
              className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                healthError
                  ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
                  : health?.ok
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                  : "bg-slate-800 text-slate-400 border-slate-700"
              }`}
            >
              {healthLoading ? (
                <RefreshCw className="w-3 h-3 animate-spin text-slate-400" />
              ) : healthError ? (
                <AlertCircle className="w-3 h-3 text-rose-400" />
              ) : (
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              )}
              <span className="hidden sm:inline">
                {healthLoading
                  ? "Connecting..."
                  : healthError
                  ? "Python Service Offline"
                  : `Online: ${health?.ocr || "PaddleOCR-VL"}`}
              </span>
            </div>

            <Link
              href="/upload"
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-sm font-semibold bg-gradient-to-r from-cyan-500 to-teal-500 hover:from-cyan-400 hover:to-teal-400 text-white shadow-md shadow-cyan-500/20 transition-all hover:scale-[1.02] active:scale-[0.98]"
            >
              <Upload className="w-4 h-4" />
              <span className="hidden sm:inline">Upload Prescription</span>
            </Link>
          </div>
        </div>
      </div>
    </header>
  );
}
