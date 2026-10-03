"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  User,
  Stethoscope,
  Plus,
  LayoutDashboard,
  Clock,
  TrendingUp,
  Pill,
  FileText,
  AlertCircle,
  FileCheck,
  Share2,
  Database,
  RotateCcw,
  LogOut,
  Upload,
  FilePlus,
  ShieldCheck,
  Heart,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Info,
  X,
  Sparkles,
  Loader2,
  Building,
} from "lucide-react";

export default function PatientDashboard() {
  const router = useRouter();
  const [user, setUser] = useState<{ name: string; email: string } | null>(null);
  const [activeTab, setActiveTab] = useState("Overview");
  const [portalMode, setPortalMode] = useState<"patient" | "doctor">("patient");
  const [ocrModalOpen, setOcrModalOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [filePreview, setFilePreview] = useState<string | null>(null);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [ocrResult, setOcrResult] = useState<any | null>(null);

  useEffect(() => {
    // Verify JWT Auth token
    const token = localStorage.getItem("auth_token");
    const storedUser = localStorage.getItem("user");

    if (storedUser) {
      try {
        setUser(JSON.parse(storedUser));
      } catch (e) {
        setUser({ name: "Rahul Sharma", email: "rahul.sharma@example.com" });
      }
    } else {
      setUser({ name: "Rahul Sharma", email: "rahul.sharma@example.com" });
    }

    // Call /api/auth/me for backend session verification
    fetch("/api/auth/me")
      .then((res) => res.json())
      .then((data) => {
        if (data.authenticated && data.user) {
          setUser(data.user);
        }
      })
      .catch(() => {});
  }, []);

  const handleLogout = async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch (e) {}
    localStorage.removeItem("auth_token");
    localStorage.removeItem("user");
    router.push("/auth");
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      setFilePreview(URL.createObjectURL(file));
      setOcrResult(null);
    }
  };

  const handleRunOcr = async () => {
    if (!selectedFile) return;

    setOcrLoading(true);
    setOcrResult(null);

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      // Connect to Python PaddleOCR backend server at http://localhost:8000/api/ocr
      const res = await fetch("http://localhost:8000/api/ocr", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error("OCR server error or connection timed out");
      }

      const data = await res.json();
      setOcrResult(data);
    } catch (err: any) {
      setOcrResult({
        error: true,
        message: err.message || "Failed to process image with PaddleOCR engine",
      });
    } finally {
      setOcrLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f4f7f6] text-slate-800 font-sans flex flex-col">
      {/* Top Header Navbar */}
      <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between sticky top-0 z-30 shadow-xs">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[#0d9488] flex items-center justify-center text-white shadow-xs">
            <Activity className="w-5 h-5 stroke-[2.5]" />
          </div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold text-slate-900 tracking-tight">
              Patient-Centric DMR
            </h1>
            <span className="px-2 py-0.5 text-[11px] font-bold text-[#0d9488] border border-[#0d9488]/30 rounded bg-[#0d9488]/5 tracking-wider uppercase">
              DEMO MVP
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 bg-slate-100 p-1 rounded-full border border-slate-200">
          <button
            onClick={() => setPortalMode("patient")}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-full transition-all ${
              portalMode === "patient"
                ? "bg-white text-slate-900 shadow-xs"
                : "text-slate-500 hover:text-slate-800"
            }`}
          >
            <User className="w-3.5 h-3.5" />
            Patient Portal
          </button>
          <button
            onClick={() => setPortalMode("doctor")}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-full transition-all ${
              portalMode === "doctor"
                ? "bg-white text-slate-900 shadow-xs"
                : "text-slate-500 hover:text-slate-800"
            }`}
          >
            <Stethoscope className="w-3.5 h-3.5" />
            Doctor Portal
          </button>
        </div>
      </header>

      <div className="flex flex-1">
        {/* Left Sidebar Navigation */}
        <aside className="w-64 bg-white border-r border-slate-200 p-4 flex flex-col justify-between shrink-0">
          <div className="space-y-4">
            {/* User Profile Info Card */}
            <div className="bg-[#f0fdfa] border border-[#ccfbf1] p-3 rounded-2xl flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-[#0f766e] text-white flex items-center justify-center font-bold text-sm shadow-xs">
                RS
              </div>
              <div className="overflow-hidden">
                <h2 className="text-xs font-bold text-slate-900 truncate">
                  {user?.name || "Rahul Sharma"}
                </h2>
                <p className="text-[11px] text-slate-500 truncate">
                  42y • Male • DEMO-P001
                </p>
              </div>
            </div>

            {/* Primary Action Button */}
            <button
              onClick={() => setOcrModalOpen(true)}
              className="w-full bg-[#008080] hover:bg-[#006666] text-white text-xs font-bold py-2.5 px-4 rounded-xl flex items-center justify-center gap-2 shadow-xs transition-colors"
            >
              <Plus className="w-4 h-4 stroke-[2.5]" />
              Add Medical Info
            </button>

            {/* Nav Menu Items */}
            <nav className="space-y-1 pt-2">
              {[
                { name: "Overview", icon: LayoutDashboard },
                { name: "Medical Timeline", icon: Clock, badge: "1 conflict" },
                { name: "Health Trends", icon: TrendingUp },
                { name: "Medicines", icon: Pill },
                { name: "Documents", icon: FileText },
                { name: "Symptoms & Side Effects", icon: AlertCircle },
                { name: "Patient Summary", icon: FileCheck },
                { name: "Share Records", icon: Share2 },
                { name: "HMS Integration", icon: Database },
              ].map((item) => {
                const Icon = item.icon;
                const isActive = activeTab === item.name;
                return (
                  <button
                    key={item.name}
                    onClick={() => {
                      setActiveTab(item.name);
                      if (item.name === "Documents") setOcrModalOpen(true);
                    }}
                    className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-medium transition-all ${
                      isActive
                        ? "bg-[#e6f4f1] text-[#006666] font-bold border-l-4 border-[#008080]"
                        : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <Icon className={`w-4 h-4 ${isActive ? "text-[#008080]" : "text-slate-400"}`} />
                      <span>{item.name}</span>
                    </div>
                    {item.badge && (
                      <span className="bg-[#fef3c7] text-[#b45309] text-[10px] font-bold px-2 py-0.5 rounded-full">
                        {item.badge}
                      </span>
                    )}
                  </button>
                );
              })}
            </nav>
          </div>

          {/* App Controls Bottom Section */}
          <div className="pt-4 border-t border-slate-100 space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-2">
              App Controls
            </p>
            <button
              onClick={() => window.location.reload()}
              className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-50 rounded-xl transition-colors border border-slate-200"
            >
              <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
              Reset Demo Data
            </button>
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-slate-600 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition-colors border border-slate-200"
            >
              <LogOut className="w-3.5 h-3.5 text-slate-400" />
              Return to Home / Sign Out
            </button>
          </div>
        </aside>

        {/* Main Content Area */}
        <main className="flex-1 p-8 overflow-y-auto space-y-6 max-w-7xl">
          {/* Welcome Banner */}
          <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <h2 className="text-2xl font-extrabold text-slate-900">
                  Welcome, {user?.name || "Rahul Sharma"}
                </h2>
                <span className="bg-teal-50 text-teal-700 text-xs font-bold px-2.5 py-0.5 rounded border border-teal-200">
                  DEMO-P001
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Personal Medical Record • Longitudinal Care Summary as of September 2026
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2.5">
              <button className="flex items-center gap-2 bg-[#0284c7] hover:bg-[#0369a1] text-white text-xs font-semibold px-4 py-2 rounded-xl shadow-xs transition-colors">
                <Database className="w-4 h-4" />
                Import from HMS
              </button>
              <button
                onClick={() => setOcrModalOpen(true)}
                className="flex items-center gap-2 bg-[#008080] hover:bg-[#006666] text-white text-xs font-semibold px-4 py-2 rounded-xl shadow-xs transition-colors"
              >
                <Upload className="w-4 h-4" />
                Upload Document
              </button>
              <button className="flex items-center gap-2 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold px-4 py-2 rounded-xl border border-slate-300 transition-colors">
                <FilePlus className="w-4 h-4 text-slate-400" />
                Add Manual Entry
              </button>
            </div>
          </div>

          {/* Alert Warning Box */}
          <div className="bg-[#fffbeb] border border-[#fef3c7] p-4 rounded-2xl flex items-start gap-3 shadow-xs">
            <AlertTriangle className="w-5 h-5 text-[#b45309] shrink-0 mt-0.5" />
            <div className="flex-1 text-xs text-[#92400e]">
              <h3 className="font-bold text-[#b45309] mb-0.5">
                Conflicting Clinical Information Detected (1 Item)
              </h3>
              <p className="leading-relaxed">
                A patient manual entry for Metformin (1000 mg) conflicts with the hospital prescription order (500 mg). Hospital HMS is prioritized for clinical continuity. Both records are preserved in the timeline.
              </p>
            </div>
            <button className="text-xs font-bold text-[#b45309] hover:underline flex items-center gap-1 shrink-0">
              Review Discrepancy &rarr;
            </button>
          </div>

          {/* 6 Key Metric Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            {/* Card 1 */}
            <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col justify-between">
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-[11px] font-semibold text-slate-500">Total Records</span>
                <FileText className="w-4 h-4 text-slate-400" />
              </div>
              <div>
                <span className="text-2xl font-extrabold text-slate-900">14</span>
                <p className="text-[10px] text-slate-400 mt-0.5">Across 7 years</p>
              </div>
            </div>

            {/* Card 2 */}
            <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col justify-between">
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-[11px] font-semibold text-slate-500">Hospital Verified</span>
                <ShieldCheck className="w-4 h-4 text-emerald-500" />
              </div>
              <div>
                <span className="text-2xl font-extrabold text-slate-900">7</span>
                <p className="text-[10px] text-teal-600 font-medium mt-0.5">50% of total</p>
              </div>
            </div>

            {/* Card 3 */}
            <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col justify-between">
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-[11px] font-semibold text-slate-500">Active Meds</span>
                <Pill className="w-4 h-4 text-indigo-500" />
              </div>
              <div>
                <span className="text-2xl font-extrabold text-slate-900">2</span>
                <p className="text-[10px] text-slate-400 mt-0.5">Oral therapies</p>
              </div>
            </div>

            {/* Card 4 */}
            <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col justify-between">
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-[11px] font-semibold text-slate-500">Last HbA1c</span>
                <Activity className="w-4 h-4 text-amber-500" />
              </div>
              <div>
                <span className="text-2xl font-extrabold text-[#d97706]">8.1%</span>
                <p className="text-[10px] text-amber-600 font-medium mt-0.5">Aug 2026 (Elevated)</p>
              </div>
            </div>

            {/* Card 5 */}
            <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col justify-between">
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-[11px] font-semibold text-slate-500">Latest Blood Pressure</span>
                <Heart className="w-4 h-4 text-rose-500" />
              </div>
              <div>
                <div className="text-lg font-extrabold text-slate-900 leading-tight">146/92</div>
                <span className="text-[11px] font-bold text-slate-900">mmHg</span>
                <p className="text-[10px] text-slate-400 mt-0.5">10 Sep 2026 (Stage 1)</p>
              </div>
            </div>

            {/* Card 6 */}
            <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col justify-between">
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-[11px] font-semibold text-slate-500">History Coverage</span>
                <CheckCircle2 className="w-4 h-4 text-teal-500" />
              </div>
              <div>
                <span className="text-2xl font-extrabold text-slate-900">70%</span>
                <p className="text-[10px] text-teal-600 font-medium mt-0.5">Good baseline</p>
              </div>
            </div>
          </div>

          {/* Bottom Grid: Longitudinal Care Summary & Prioritization Hierarchy */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left 2 Columns: Longitudinal Health Status Summary */}
            <div className="lg:col-span-2 bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-[#008080]" />
                  <h3 className="text-sm font-bold text-slate-900">
                    Longitudinal Health Status Summary
                  </h3>
                </div>
                <span className="text-[11px] text-slate-400">Updated 13 Sep 2026</span>
              </div>

              <p className="text-xs text-slate-600 leading-relaxed">
                Rahul Sharma is a 42-year-old male with active <strong className="text-slate-800">Type 2 Diabetes Mellitus</strong> (diagnosed June 2021) and <strong className="text-slate-800">Essential Hypertension</strong> (diagnosed March 2023). Current glycemic indices demonstrate sub-optimal control with an HbA1c of 8.1% (August 2026) and fasting glucose of 168 mg/dL. On 10 September 2026, Dr. Priya Deshmukh initiated Metformin 500 mg BID alongside ongoing Telmisartan 40 mg OD. Mild transient epigastric discomfort was subsequently logged by the patient.
              </p>

              {/* Sub-cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
                <div className="bg-slate-50 p-3 rounded-xl border border-slate-200/60">
                  <span className="text-[10px] font-semibold text-slate-400 block mb-1">Primary Diagnosis</span>
                  <h4 className="text-xs font-bold text-slate-900 mb-1.5">Type 2 Diabetes Mellitus</h4>
                  <span className="inline-block text-[10px] font-bold text-sky-700 bg-sky-50 border border-sky-200 px-1.5 py-0.5 rounded">
                    ICD E11.9
                  </span>
                </div>

                <div className="bg-slate-50 p-3 rounded-xl border border-slate-200/60">
                  <span className="text-[10px] font-semibold text-slate-400 block mb-1">Secondary Diagnosis</span>
                  <h4 className="text-xs font-bold text-slate-900 mb-1.5">Essential Hypertension</h4>
                  <span className="inline-block text-[10px] font-bold text-indigo-700 bg-indigo-50 border border-indigo-200 px-1.5 py-0.5 rounded">
                    ICD I10
                  </span>
                </div>

                <div className="bg-slate-50 p-3 rounded-xl border border-slate-200/60">
                  <span className="text-[10px] font-semibold text-slate-400 block mb-1">Primary Facility</span>
                  <h4 className="text-xs font-bold text-slate-900 mb-1.5">Demo General Hospital</h4>
                  <span className="inline-block text-[10px] font-bold text-teal-700 bg-teal-50 border border-teal-200 px-1.5 py-0.5 rounded">
                    ABDM Connected
                  </span>
                </div>
              </div>
            </div>

            {/* Right Column: How Records Are Prioritized */}
            <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs space-y-4">
              <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
                <Info className="w-4 h-4 text-[#008080]" />
                <h3 className="text-sm font-bold text-slate-900">
                  How Records Are Prioritized
                </h3>
              </div>

              <p className="text-xs text-slate-500 leading-relaxed">
                To guarantee clinical safety, this system applies deterministic provenance hierarchy when displaying data:
              </p>

              <div className="space-y-3">
                <div className="bg-sky-50/60 p-3 rounded-xl border border-sky-100">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="text-xs font-bold text-sky-900">1. Hospital HMS</h4>
                    <span className="bg-sky-200 text-sky-900 text-[10px] font-extrabold px-2 py-0.5 rounded uppercase">
                      Highest
                    </span>
                  </div>
                  <p className="text-[11px] text-sky-700 leading-relaxed">
                    Direct EHR/FHIR telemetry with cryptographic certificates. Takes priority in dose or medication conflicts.
                  </p>
                </div>

                <div className="bg-amber-50/60 p-3 rounded-xl border border-amber-100">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="text-xs font-bold text-amber-900">2. Patient-Uploaded Documents</h4>
                    <span className="bg-amber-200 text-amber-900 text-[10px] font-extrabold px-2 py-0.5 rounded uppercase">
                      Medium
                    </span>
                  </div>
                  <p className="text-[11px] text-amber-700 leading-relaxed">
                    External clinic records, scanned prescriptions, and lab printouts verified via document PaddleOCR.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>

      {/* PaddleOCR Document Upload Modal */}
      {ocrModalOpen && (
        <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-3xl max-w-xl w-full p-6 shadow-2xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-teal-500/10 text-teal-600 flex items-center justify-center">
                  <Sparkles className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">PaddleOCR Medical Document Scanner</h3>
                  <p className="text-[11px] text-slate-400">Powered by Python 3.11 & NVIDIA RTX 4050</p>
                </div>
              </div>
              <button
                onClick={() => setOcrModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drop Zone */}
            <div className="border-2 border-dashed border-slate-300 hover:border-teal-500 rounded-2xl p-6 text-center transition-colors bg-slate-50 relative">
              <input
                type="file"
                accept="image/*"
                onChange={handleFileChange}
                className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
              />
              <Upload className="w-8 h-8 text-teal-600 mx-auto mb-2" />
              <p className="text-xs font-bold text-slate-800 mb-1">
                {selectedFile ? selectedFile.name : "Choose or drop prescription image"}
              </p>
              <p className="text-[10px] text-slate-400">PNG, JPG, JPEG up to 10MB</p>
            </div>

            {/* Image Preview */}
            {filePreview && (
              <div className="max-h-40 overflow-hidden rounded-xl border border-slate-200 bg-slate-950 flex items-center justify-center p-2">
                <img src={filePreview} alt="Preview" className="max-h-36 object-contain" />
              </div>
            )}

            {/* OCR Processing Results */}
            {ocrResult && (
              <div className="p-3 bg-slate-900 text-slate-100 rounded-xl text-xs font-mono max-h-48 overflow-y-auto space-y-2 border border-slate-800">
                <div className="flex items-center justify-between text-teal-400 text-[11px] font-bold font-sans">
                  <span>PaddleOCR Output</span>
                  <span>{ocrResult.results?.length || 0} text boxes detected</span>
                </div>
                {ocrResult.results ? (
                  ocrResult.results.map((item: any, idx: number) => (
                    <div key={idx} className="bg-slate-950 p-2 rounded border border-slate-800 flex items-center justify-between text-[11px]">
                      <span className="text-emerald-400">{item.text}</span>
                      <span className="text-slate-500 text-[10px]">{(item.confidence * 100).toFixed(1)}% conf</span>
                    </div>
                  ))
                ) : (
                  <p className="text-rose-400 text-[11px]">{ocrResult.message || "No text detected."}</p>
                )}
              </div>
            )}

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                onClick={() => setOcrModalOpen(false)}
                className="px-4 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-xl"
              >
                Close
              </button>
              <button
                onClick={handleRunOcr}
                disabled={!selectedFile || ocrLoading}
                className="px-4 py-2 bg-gradient-to-r from-teal-600 to-emerald-600 hover:from-teal-500 hover:to-emerald-500 text-white text-xs font-bold rounded-xl shadow-xs flex items-center gap-2 disabled:opacity-50"
              >
                {ocrLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Running PaddleOCR...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    Extract Medical Text
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
