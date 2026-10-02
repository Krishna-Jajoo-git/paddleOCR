"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  Upload,
  Activity,
  FileText,
  Clock,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Search,
  RefreshCw,
  User,
  Calendar,
  Building2,
  Stethoscope,
  Sparkles,
} from "lucide-react";
import { clientApi } from "@/lib/api";
import { ExtractionSummaryItem, HealthResponse } from "@/lib/types";
import { GateBadge, ExtractionStatusBadge } from "@/components/StatusBadge";
import { MedicalDisclaimer } from "@/components/MedicalDisclaimer";

export default function DashboardPage() {
  const [extractions, setExtractions] = useState<ExtractionSummaryItem[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [exList, hData] = await Promise.all([
        clientApi.listExtractions(),
        clientApi.checkHealth().catch(() => null),
      ]);
      setExtractions(exList);
      setHealth(hData);
    } catch (err: any) {
      setError(err.message || "Failed to load recent extractions");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filteredExtractions = extractions.filter((item) => {
    const matchesSearch =
      search === "" ||
      item.patient_id.toLowerCase().includes(search.toLowerCase()) ||
      (item.record?.patient?.name || "").toLowerCase().includes(search.toLowerCase()) ||
      (item.record?.doctor?.name || "").toLowerCase().includes(search.toLowerCase()) ||
      item.filename.toLowerCase().includes(search.toLowerCase()) ||
      String(item.extraction_id).includes(search);

    const matchesStatus =
      statusFilter === "ALL" || item.status === statusFilter;

    return matchesSearch && matchesStatus;
  });

  const pendingCount = extractions.filter((x) => x.status === "PENDING_USER_CONFIRMATION").length;
  const confirmedCount = extractions.filter((x) => x.status === "CONFIRMED").length;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 space-y-8">
      {/* Top Banner & Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-xs font-semibold uppercase tracking-wider mb-2">
            <Sparkles className="w-3.5 h-3.5" />
            Clinical Vision-Language System
          </div>
          <h1 className="text-3xl font-extrabold text-white tracking-tight">
            Prescription <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-teal-400">Intelligence</span>
          </h1>
          <p className="text-sm text-slate-400 mt-1 max-w-2xl">
            Automated prescription digitization, handwritten text OCR via PaddleOCR-VL, and clinical structuring with Google Gemini.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 text-xs font-medium transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
          <Link
            href="/upload"
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-teal-500 hover:from-cyan-400 hover:to-teal-400 text-white font-semibold text-sm shadow-lg shadow-cyan-500/20 transition-all hover:scale-[1.02] active:scale-[0.98]"
          >
            <Upload className="w-4 h-4" />
            Process Prescription
          </Link>
        </div>
      </div>

      {/* Safety Notice Banner */}
      <MedicalDisclaimer compact />

      {/* Status & Operational Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Total Extractions */}
        <div className="p-5 rounded-2xl glass-panel border border-slate-800 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Total Processed</span>
            <div className="p-2 rounded-xl bg-blue-500/10 text-blue-400">
              <FileText className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-white font-mono">{extractions.length}</span>
            <span className="text-xs text-slate-500">records in DB</span>
          </div>
        </div>

        {/* Card 2: Pending Clinical Confirmation */}
        <div className="p-5 rounded-2xl glass-panel border border-slate-800 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Pending Review</span>
            <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400">
              <Clock className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-amber-400 font-mono">{pendingCount}</span>
            <span className="text-xs text-slate-500">drafts awaiting sign-off</span>
          </div>
        </div>

        {/* Card 3: Confirmed Prescriptions */}
        <div className="p-5 rounded-2xl glass-panel border border-slate-800 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Confirmed & Saved</span>
            <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400">
              <CheckCircle2 className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-emerald-400 font-mono">{confirmedCount}</span>
            <span className="text-xs text-slate-500">clinical records</span>
          </div>
        </div>

        {/* Card 4: Medicine Master Index */}
        <div className="p-5 rounded-2xl glass-panel border border-slate-800 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Drug Master Index</span>
            <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400">
              <Stethoscope className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-cyan-400 font-mono">
              {health?.medicine_names_indexed ?? "—"}
            </span>
            <span className="text-xs text-slate-500">active drug names</span>
          </div>
        </div>
      </div>

      {/* Hero Quick Upload Banner */}
      <div className="p-6 rounded-2xl bg-gradient-to-r from-slate-900 via-slate-900/90 to-cyan-950/40 border border-slate-800 relative overflow-hidden">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Upload className="w-5 h-5 text-cyan-400" />
              Upload New Prescription
            </h2>
            <p className="text-xs text-slate-400 max-w-xl">
              Upload prescription scans or mobile phone photos (JPEG, PNG, WebP up to 10MB). PaddleOCR-VL extracts layout and text lines, and Gemini models clinical entities into verified records.
            </p>
          </div>
          <Link
            href="/upload"
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold text-xs transition-colors shrink-0 shadow-md"
          >
            Start Extraction
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      {/* Prescription Processing History Table */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <Activity className="w-5 h-5 text-teal-400" />
              Prescription Processing History
            </h3>
            <p className="text-xs text-slate-400">
              Real-time processing records stored in the local SQLite/PostgreSQL clinical database.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Status Filter */}
            <div className="flex rounded-lg bg-slate-900 p-0.5 border border-slate-800 text-xs">
              {["ALL", "PENDING_USER_CONFIRMATION", "CONFIRMED", "DISCARDED"].map((st) => (
                <button
                  key={st}
                  onClick={() => setStatusFilter(st)}
                  className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                    statusFilter === st
                      ? "bg-cyan-500/20 text-cyan-300"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {st === "ALL" ? "All" : st === "PENDING_USER_CONFIRMATION" ? "Pending" : st === "CONFIRMED" ? "Confirmed" : "Discarded"}
                </button>
              ))}
            </div>

            {/* Search Input */}
            <div className="relative w-full sm:w-56">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search patient or file..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 text-xs rounded-lg bg-slate-900 border border-slate-800 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
              />
            </div>
          </div>
        </div>

        {error && (
          <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-center justify-between">
            <span>{error}</span>
            <button onClick={loadData} className="underline font-semibold ml-4">
              Retry
            </button>
          </div>
        )}

        <div className="border border-slate-800 rounded-2xl overflow-hidden bg-slate-900/60 shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800 font-medium">
                <tr>
                  <th className="py-3 px-4">Extraction ID</th>
                  <th className="py-3 px-4">Patient</th>
                  <th className="py-3 px-4">Prescribing Doctor</th>
                  <th className="py-3 px-4">Quality Gate</th>
                  <th className="py-3 px-4">Medications</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Processed At</th>
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                {loading && extractions.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-12 text-center text-slate-500">
                      <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-cyan-400" />
                      Loading prescription history...
                    </td>
                  </tr>
                ) : filteredExtractions.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-12 text-center text-slate-500">
                      <FileText className="w-8 h-8 mx-auto mb-2 text-slate-600" />
                      No prescription records found matching your filters.
                    </td>
                  </tr>
                ) : (
                  filteredExtractions.map((item) => {
                    const patient = item.record?.patient || {};
                    const doctor = item.record?.doctor || {};
                    const medCount = item.record?.medicines?.length || 0;
                    const dateFormatted = item.created_at
                      ? new Date(item.created_at).toLocaleString()
                      : "—";

                    return (
                      <tr
                        key={item.extraction_id}
                        className="hover:bg-slate-800/40 transition-colors"
                      >
                        <td className="py-3.5 px-4 font-mono font-bold text-cyan-400">
                          #{item.extraction_id}
                        </td>

                        <td className="py-3.5 px-4">
                          <div className="font-semibold text-slate-200">
                            {patient.name || `Patient ID: ${item.patient_id}`}
                          </div>
                          <div className="text-[11px] text-slate-500 flex items-center gap-1.5 mt-0.5">
                            <span className="font-mono">ID: {item.patient_id}</span>
                            {patient.age && <span>• {patient.age}y</span>}
                            {patient.sex && <span>• {patient.sex}</span>}
                          </div>
                        </td>

                        <td className="py-3.5 px-4">
                          <div className="text-slate-300 font-medium">
                            {doctor.name || "Not detected"}
                          </div>
                          {item.record?.hospital && (
                            <div className="text-[11px] text-slate-500 truncate max-w-xs mt-0.5">
                              {item.record.hospital}
                            </div>
                          )}
                        </td>

                        <td className="py-3.5 px-4">
                          <GateBadge status={item.gate?.status || "NEEDS_CHECK"} size="sm" />
                        </td>

                        <td className="py-3.5 px-4 font-mono">
                          <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-medium">
                            {medCount} {medCount === 1 ? "drug" : "drugs"}
                          </span>
                        </td>

                        <td className="py-3.5 px-4">
                          <ExtractionStatusBadge status={item.status} />
                        </td>

                        <td className="py-3.5 px-4 text-slate-400 text-[11px] whitespace-nowrap">
                          {dateFormatted}
                        </td>

                        <td className="py-3.5 px-4 text-right">
                          <Link
                            href={`/extractions/${item.extraction_id}`}
                            className="inline-flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-semibold bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 transition-colors"
                          >
                            Review
                            <ArrowRight className="w-3 h-3" />
                          </Link>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
