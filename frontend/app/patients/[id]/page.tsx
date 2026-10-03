"use client";

import React, { useEffect, useState, use } from "react";
import Link from "next/link";
import {
  ConfirmedPrescription,
  ObservationRecord,
} from "@/lib/types";
import { clientApi } from "@/lib/api";
import {
  User,
  Calendar,
  Building2,
  Stethoscope,
  Clock,
  ArrowLeft,
  FileText,
  Activity,
  Heart,
  Pill,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
} from "lucide-react";

export default function PatientHistoryPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const patientId = decodeURIComponent(id);

  const [prescriptions, setPrescriptions] = useState<ConfirmedPrescription[]>([]);
  const [observations, setObservations] = useState<ObservationRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [rxList, obsList] = await Promise.all([
        clientApi.getPatientPrescriptions(patientId),
        clientApi.getPatientObservations(patientId).catch(() => []),
      ]);
      setPrescriptions(rxList);
      setObservations(obsList);
    } catch (err: any) {
      setError(err.message || "Failed to load patient history");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [patientId]);

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-20 text-center space-y-3">
        <RefreshCw className="w-8 h-8 animate-spin mx-auto text-cyan-400" />
        <h2 className="text-base font-semibold text-slate-200">
          Loading patient timeline for {patientId}...
        </h2>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 space-y-8">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="p-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors border border-slate-800"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-white tracking-tight">
                Patient Medical Record
              </h1>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                {patientId}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Verified prescription timeline & clinical observation history
            </p>
          </div>
        </div>

        <button
          onClick={loadData}
          className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 text-xs font-medium transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </button>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center justify-between">
          <span>{error}</span>
          <button onClick={loadData} className="underline font-semibold ml-4">
            Retry
          </button>
        </div>
      )}

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-5 rounded-2xl glass-panel border border-slate-800">
          <span className="text-xs font-medium text-slate-400 block">Confirmed Prescriptions</span>
          <span className="text-2xl font-bold text-emerald-400 font-mono mt-1 block">
            {prescriptions.length}
          </span>
        </div>

        <div className="p-5 rounded-2xl glass-panel border border-slate-800">
          <span className="text-xs font-medium text-slate-400 block">Recorded Observations</span>
          <span className="text-2xl font-bold text-cyan-400 font-mono mt-1 block">
            {observations.length}
          </span>
        </div>

        <div className="p-5 rounded-2xl glass-panel border border-slate-800">
          <span className="text-xs font-medium text-slate-400 block">Latest Prescription Date</span>
          <span className="text-sm font-semibold text-slate-200 mt-2 block font-mono">
            {prescriptions.length > 0 ? prescriptions[prescriptions.length - 1].rx_date : "No records yet"}
          </span>
        </div>
      </div>

      {/* Prescriptions Timeline */}
      <div className="space-y-4">
        <h2 className="text-base font-bold text-white flex items-center gap-2">
          <Calendar className="w-4 h-4 text-cyan-400" />
          Prescription Timeline
        </h2>

        {prescriptions.length === 0 ? (
          <div className="p-8 text-center rounded-2xl bg-slate-900/60 border border-slate-800 text-slate-500 text-xs">
            No confirmed prescriptions on file for this patient.
          </div>
        ) : (
          <div className="space-y-4">
            {prescriptions.map((rx) => {
              const meds = rx.data?.medicines || [];
              const edits = rx.edits || [];

              return (
                <div
                  key={rx.id}
                  className="p-5 rounded-2xl glass-panel border border-slate-800 space-y-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
                    <div className="flex items-center gap-3">
                      <Link
                        href={`/extractions/${rx.extraction_id}`}
                        className="px-2.5 py-1 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 font-mono font-bold text-xs border border-emerald-500/20 transition-colors inline-flex items-center gap-1"
                        title="View original clinical extraction & OCR"
                      >
                        <span>Rx #{rx.id}</span>
                        <ExternalLink className="w-3 h-3" />
                      </Link>
                      <div>
                        <span className="text-sm font-bold text-white font-mono">{rx.rx_date}</span>
                        <span className="text-xs text-slate-400 block">
                          Confirmed by {rx.confirmed_by || "Clinician"} on {new Date(rx.confirmed_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>

                    <div className="text-right text-xs text-slate-400">
                      <span className="font-semibold text-slate-200 block">{rx.doctor || "Doctor Unspecified"}</span>
                      <span className="text-slate-500">{rx.hospital || "Hospital Unspecified"}</span>
                    </div>
                  </div>

                  {/* Medicines list */}
                  <div className="space-y-2">
                    <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                      <Pill className="w-3.5 h-3.5 text-cyan-400" />
                      Medications Prescribed ({meds.length})
                    </span>
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                      {meds.map((m, mi) => (
                        <div
                          key={mi}
                          className="p-2.5 rounded-xl bg-slate-950 border border-slate-800/80 text-xs space-y-1"
                        >
                          <div className="font-semibold text-slate-100 flex items-center justify-between">
                            <span>{m.name || "Unnamed"}</span>
                            {m.form && <span className="text-[10px] text-slate-500">{m.form}</span>}
                          </div>
                          <div className="text-[11px] text-slate-400 flex items-center gap-2">
                            <span>{m.strength || "—"}</span>
                            <span>•</span>
                            <span>{m.frequency || "—"}</span>
                            {m.duration && <span>• {m.duration}</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Clinician edits diff */}
                  {edits.length > 0 && (
                    <div className="p-3 rounded-xl bg-blue-500/10 border border-blue-500/20 text-xs text-blue-300 space-y-1">
                      <span className="font-semibold block">Clinician Corrections Recorded:</span>
                      <ul className="list-disc list-inside text-[11px] space-y-0.5 text-blue-200/90">
                        {edits.map((e, ei) => (
                          <li key={ei}>
                            <span className="font-mono">{e.path}</span>: changed from &quot;{String(e.machine)}&quot; to &quot;{String(e.confirmed)}&quot;
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Observations & Trends Table */}
      {observations.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Activity className="w-4 h-4 text-teal-400" />
            Clinical Observations & Trends
          </h2>
          <div className="border border-slate-800 rounded-2xl overflow-hidden bg-slate-900/60 shadow-lg">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800 font-medium">
                <tr>
                  <th className="py-2.5 px-4">Date</th>
                  <th className="py-2.5 px-4">Measurement</th>
                  <th className="py-2.5 px-4">Value</th>
                  <th className="py-2.5 px-4">Unit</th>
                  <th className="py-2.5 px-4">Recorded Text</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300 font-mono">
                {observations.map((obs) => (
                  <tr key={obs.id} className="hover:bg-slate-800/40">
                    <td className="py-2.5 px-4">{obs.obs_date}</td>
                    <td className="py-2.5 px-4 capitalize font-sans text-cyan-400">{obs.kind}</td>
                    <td className="py-2.5 px-4 font-bold text-white">
                      {obs.kind === "bp" && obs.systolic && obs.diastolic
                        ? `${obs.systolic} / ${obs.diastolic}`
                        : obs.value || "—"}
                    </td>
                    <td className="py-2.5 px-4 text-slate-400">{obs.unit || "—"}</td>
                    <td className="py-2.5 px-4 text-slate-500 font-sans">{obs.raw_text || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
