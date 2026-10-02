"use client";

import React, { useEffect, useState, use } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ExtractionPayload,
  PrescriptionRecord,
  MedicineRecord,
  RawOcrData,
  ConfirmResult,
} from "@/lib/types";
import { clientApi } from "@/lib/api";
import { GateBadge, ExtractionStatusBadge } from "@/components/StatusBadge";
import { MedicalDisclaimer } from "@/components/MedicalDisclaimer";
import { MedicineEditor } from "@/components/MedicineEditor";
import { VitalsDisplay } from "@/components/VitalsDisplay";
import { RawOcrViewer } from "@/components/RawOcrViewer";
import {
  User,
  Calendar,
  Building2,
  Stethoscope,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RefreshCw,
  ArrowLeft,
  FileText,
  ShieldCheck,
  AlertCircle,
  Edit3,
  ExternalLink,
} from "lucide-react";

export default function ExtractionDetailsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  const [payload, setPayload] = useState<ExtractionPayload | null>(null);
  const [record, setRecord] = useState<PrescriptionRecord | null>(null);
  const [rawOcr, setRawOcr] = useState<RawOcrData | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Clinician name for confirmation
  const [confirmedBy, setConfirmedBy] = useState("Dr. Reviewer");
  const [confirming, setConfirming] = useState(false);
  const [discarding, setDiscarding] = useState(false);

  // Duplicate prompt state (HTTP 409)
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null);
  const [confirmSuccess, setConfirmSuccess] = useState<ConfirmResult | null>(null);

  // Active view tab (Extraction vs Raw OCR)
  const [activeTab, setActiveTab] = useState<"review" | "rawOcr">("review");

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await clientApi.getExtraction(Number(id));
      setPayload(data);
      setRecord(data.record);

      if (data.ocr_id) {
        clientApi.getRawOcr(data.ocr_id).then(setRawOcr).catch(() => null);
      }
    } catch (err: any) {
      setError(err.message || `Failed to load extraction #${id}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [id]);

  const handleRecordFieldChange = (section: "patient" | "doctor", field: string, value: string) => {
    if (!record) return;
    setRecord({
      ...record,
      [section]: {
        ...((record[section] || {}) as any),
        [field]: value.trim() === "" ? null : value,
      },
    });
  };

  const handleMedicinesChange = (updatedMeds: MedicineRecord[]) => {
    if (!record) return;
    setRecord({
      ...record,
      medicines: updatedMeds,
    });
  };

  const handleConfirm = async (allowDuplicate = false) => {
    if (!record || !payload) return;
    setError(null);
    setDuplicateWarning(null);

    // Ensure valid ISO date or fallback to today
    let dateIso = record.date_iso?.trim();
    if (!dateIso) {
      dateIso = new Date().toISOString().split("T")[0];
    }

    if (!record.medicines || record.medicines.length === 0) {
      setError("At least one medicine is required to confirm the prescription. Please add a medication.");
      return;
    }

    const currentPatientId = record.patient?.uhid?.trim() || payload.patient_id || "UNKNOWN";

    const updatedRecord: PrescriptionRecord = {
      ...record,
      date_iso: dateIso,
      patient: {
        ...(record.patient || {}),
        name: record.patient?.name || null,
        uhid: record.patient?.uhid || null,
      },
      doctor: {
        ...(record.doctor || {}),
        name: record.doctor?.name || null,
        reg_no: record.doctor?.reg_no || null,
      },
    };
    setRecord(updatedRecord);
    setConfirming(true);

    try {
      const result = await clientApi.confirmExtraction(
        payload.extraction_id,
        updatedRecord,
        confirmedBy,
        allowDuplicate
      );
      setConfirmSuccess(result);
      setError(null);
      // Immediately reflect confirmed status in state
      setPayload((prev) => (prev ? { ...prev, status: "CONFIRMED" } : null));
    } catch (err: any) {
      if (err.status === 409 && err.message?.includes("duplicate")) {
        setDuplicateWarning(err.message);
      } else if (err.status === 409 && err.message?.includes("already confirmed")) {
        setPayload((prev) => (prev ? { ...prev, status: "CONFIRMED" } : null));
        setConfirmSuccess({
          prescription_id: Number(id),
          patient_id: currentPatientId,
          rx_date: dateIso,
          edits: [],
          observations_saved: 0,
          observations_skipped: [],
        });
      } else {
        setError(err.message || "Failed to confirm prescription.");
      }
    } finally {
      setConfirming(false);
    }
  };

  const handleDiscard = async () => {
    if (!payload) return;
    if (!confirm("Are you sure you want to discard this extraction? It will be marked as DISCARDED.")) {
      return;
    }

    setDiscarding(true);
    try {
      await clientApi.discardExtraction(payload.extraction_id);
      loadData();
    } catch (err: any) {
      setError(err.message || "Failed to discard extraction.");
    } finally {
      setDiscarding(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-20 text-center space-y-3">
        <RefreshCw className="w-8 h-8 animate-spin mx-auto text-cyan-400" />
        <h2 className="text-base font-semibold text-slate-200">
          Loading extraction #{id}...
        </h2>
      </div>
    );
  }

  if (error && !payload) {
    return (
      <div className="max-w-xl mx-auto px-4 py-16 text-center space-y-4">
        <div className="w-12 h-12 rounded-xl bg-rose-500/10 text-rose-400 flex items-center justify-center mx-auto">
          <AlertCircle className="w-6 h-6" />
        </div>
        <h2 className="text-lg font-bold text-white">Extraction Not Found</h2>
        <p className="text-xs text-rose-300">{error}</p>
        <Link
          href="/"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-900 text-slate-300 text-xs font-semibold hover:bg-slate-800 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Dashboard
        </Link>
      </div>
    );
  }

  if (!payload || !record) return null;

  const isConfirmed = payload.status === "CONFIRMED";
  const isDiscarded = payload.status === "DISCARDED";
  const isPending = payload.status === "PENDING_USER_CONFIRMATION";
  const patientId = record.patient?.uhid?.trim() || payload.patient_id || "UNKNOWN";

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 space-y-6">
      {/* Top Breadcrumb & Actions Bar */}
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
              <h1 className="text-xl font-bold text-white tracking-tight font-mono">
                Extraction #{payload.extraction_id}
              </h1>
              <ExtractionStatusBadge status={payload.status} />
              <GateBadge status={payload.gate?.status || "NEEDS_CHECK"} size="sm" />
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Source raw OCR: #{payload.ocr_id} • Structured via {payload.llm_model}
            </p>
          </div>
        </div>

        {/* View Switcher Tabs & Quick Patient Link */}
        <div className="flex items-center gap-2.5">
          {isConfirmed && (
            <Link
              href={`/patients/${encodeURIComponent(patientId)}`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-xs font-semibold transition-all hover:scale-105"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Patient Record ({patientId})</span>
              <ExternalLink className="w-3 h-3" />
            </Link>
          )}

          <div className="flex items-center rounded-xl bg-slate-900 p-1 border border-slate-800 text-xs font-medium">
            <button
              onClick={() => setActiveTab("review")}
              className={`px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 ${
                activeTab === "review" ? "bg-cyan-500/20 text-cyan-300 shadow-sm" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Edit3 className="w-3.5 h-3.5" />
              Clinical Review
            </button>
            <button
              onClick={() => setActiveTab("rawOcr")}
              className={`px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 ${
                activeTab === "rawOcr" ? "bg-cyan-500/20 text-cyan-300 shadow-sm" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              Raw OCR Inspector
            </button>
          </div>
        </div>
      </div>

      {/* Safety Notice & Medical Disclaimer */}
      <MedicalDisclaimer />

      {/* Success Notification Modal / Alert */}
      {confirmSuccess && (
        <div className="p-5 rounded-2xl bg-gradient-to-r from-emerald-950/70 to-teal-950/50 border border-emerald-500/40 text-emerald-200 text-xs shadow-2xl shadow-emerald-950/40 space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-emerald-500/20">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-emerald-500/20 text-emerald-400 shrink-0">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  Prescription #{confirmSuccess.prescription_id} Confirmed & Saved to Patient Record
                </h3>
                <p className="text-xs text-emerald-300/80 mt-0.5">
                  Saved under Patient ID: <strong className="font-mono text-white">{confirmSuccess.patient_id}</strong> • Date: <strong className="font-mono text-emerald-200">{confirmSuccess.rx_date}</strong>
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2.5">
              <Link
                href={`/patients/${encodeURIComponent(confirmSuccess.patient_id)}`}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-slate-950 font-bold text-xs shadow-lg shadow-emerald-500/25 transition-all hover:scale-105"
              >
                <span>View Patient Medical Record</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </Link>
              <Link
                href="/"
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs font-semibold border border-slate-700 transition-colors"
              >
                Dashboard
              </Link>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-4 text-[11px] text-emerald-300/90">
            <span>• Clinician modifications saved: <strong className="text-white">{confirmSuccess.edits?.length || 0}</strong></span>
            <span>• Clinical vitals/observations saved: <strong className="text-white">{confirmSuccess.observations_saved || 0}</strong></span>
            {confirmSuccess.observations_skipped && confirmSuccess.observations_skipped.length > 0 && (
              <span className="text-amber-300/90">• Vitals skipped: {confirmSuccess.observations_skipped.length}</span>
            )}
          </div>
        </div>
      )}

      {/* Error Alert Notice */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-start gap-2.5">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400 mt-0.5" />
          <div className="flex-1 space-y-1">
            <div className="font-semibold text-rose-200">Confirmation Alert</div>
            <div className="leading-relaxed">{error}</div>
          </div>
          <button
            type="button"
            onClick={() => setError(null)}
            className="text-slate-400 hover:text-white text-xs px-2 py-1 rounded bg-slate-900 border border-slate-800"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Duplicate Warning Dialog (HTTP 409) */}
      {duplicateWarning && (
        <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs space-y-3">
          <div className="font-semibold text-amber-300 flex items-center gap-2 text-sm">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            Potential Duplicate Prescription Detected
          </div>
          <p className="text-xs text-amber-200/90 leading-relaxed">{duplicateWarning}</p>
          <div className="flex items-center gap-3 pt-1">
            <button
              onClick={() => handleConfirm(true)}
              className="px-3 py-1.5 rounded-lg bg-amber-500 text-slate-950 font-semibold text-xs hover:bg-amber-400 transition-colors"
            >
              Confirm Anyway (Allow Duplicate)
            </button>
            <button
              onClick={() => setDuplicateWarning(null)}
              className="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 text-xs hover:bg-slate-700 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Quality Gate Reasons Notice */}
      {payload.gate?.reasons && payload.gate.reasons.length > 0 && (
        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1.5 text-xs">
          <div className="font-semibold text-slate-300 flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
            Validation Gating Flagged {payload.gate.reasons.length} Attention Points
          </div>
          <ul className="list-disc list-inside space-y-1 text-slate-400 text-[11px]">
            {payload.gate.reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {/* MAIN REVIEW TAB */}
      {activeTab === "review" && (
        <div className="space-y-6">
          {/* Patient, Doctor & Hospital Card */}
          <div className="p-6 rounded-2xl glass-panel border border-slate-800 space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Patient Block */}
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-xs font-semibold text-cyan-400 uppercase tracking-wider">
                  <User className="w-3.5 h-3.5" />
                  Patient Details
                </div>
                <div>
                  <label className="text-[11px] text-slate-400 block mb-0.5">Name</label>
                  {isConfirmed ? (
                    <div className="text-sm font-semibold text-slate-100">{record.patient.name || "Not detected"}</div>
                  ) : (
                    <input
                      type="text"
                      value={record.patient.name || ""}
                      onChange={(e) => handleRecordFieldChange("patient", "name", e.target.value)}
                      placeholder="Patient Name"
                      className="w-full text-sm font-semibold text-slate-100 bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-cyan-500"
                    />
                  )}
                </div>

                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div>
                    <label className="text-[10px] text-slate-500 block">UHID / ID</label>
                    <span className="font-mono text-slate-300 font-semibold">{patientId}</span>
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500 block">Age</label>
                    <span className="text-slate-300">{record.patient?.age ? `${record.patient.age}y` : "—"}</span>
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500 block">Sex</label>
                    <span className="text-slate-300">{record.patient?.sex || "—"}</span>
                  </div>
                </div>

                <div className="pt-2 border-t border-slate-800/60 flex items-center justify-between">
                  <span className="text-[10px] text-slate-500">Clinical History:</span>
                  <Link
                    href={`/patients/${encodeURIComponent(patientId)}`}
                    className="inline-flex items-center gap-1 text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 transition-colors"
                  >
                    <span>View Patient Timeline</span>
                    <ExternalLink className="w-3 h-3" />
                  </Link>
                </div>
              </div>

              {/* Prescribing Doctor Block */}
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-xs font-semibold text-teal-400 uppercase tracking-wider">
                  <Stethoscope className="w-3.5 h-3.5" />
                  Prescribing Clinician
                </div>
                <div>
                  <label className="text-[11px] text-slate-400 block mb-0.5">Doctor Name</label>
                  {isConfirmed ? (
                    <div className="text-sm font-semibold text-slate-100">{record.doctor?.name || "Not detected"}</div>
                  ) : (
                    <input
                      type="text"
                      value={record.doctor?.name || ""}
                      onChange={(e) => handleRecordFieldChange("doctor", "name", e.target.value)}
                      placeholder="Doctor Name"
                      className="w-full text-sm font-semibold text-slate-100 bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-cyan-500"
                    />
                  )}
                </div>
                <div>
                  <label className="text-[10px] text-slate-500 block">Registration No.</label>
                  <span className="font-mono text-xs text-slate-300 font-semibold">{record.doctor?.reg_no || "—"}</span>
                </div>
              </div>

              {/* Hospital & Prescription Date Block */}
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-xs font-semibold text-blue-400 uppercase tracking-wider">
                  <Building2 className="w-3.5 h-3.5" />
                  Facility & Date
                </div>
                <div>
                  <label className="text-[11px] text-slate-400 block mb-0.5">Hospital / Clinic</label>
                  <div className="text-xs font-medium text-slate-200 truncate">{record.hospital || "Not detected"}</div>
                </div>
                <div>
                  <label className="text-[11px] text-slate-400 block mb-0.5">Prescription Date (ISO)</label>
                  {isConfirmed ? (
                    <div className="font-mono text-xs text-cyan-400">{record.date_iso || "Missing"}</div>
                  ) : (
                    <input
                      type="date"
                      value={record.date_iso || ""}
                      onChange={(e) => setRecord({ ...record, date_iso: e.target.value })}
                      className="w-full text-xs font-mono text-slate-100 bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-cyan-500"
                    />
                  )}
                  {record.date_raw && (
                    <span className="text-[10px] text-slate-500 block mt-0.5">
                      Raw read: &quot;{record.date_raw}&quot;
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Vitals Section */}
          <div className="p-6 rounded-2xl glass-panel border border-slate-800 space-y-3">
            <h3 className="text-sm font-semibold text-white uppercase tracking-wider">
              Clinical Vitals & Measurements
            </h3>
            <VitalsDisplay vitals={record.vitals} />
          </div>

          {/* Medicines Section (Interactive Editor) */}
          <div className="p-6 rounded-2xl glass-panel border border-slate-800">
            <MedicineEditor
              medicines={record.medicines}
              onChange={handleMedicinesChange}
              readOnly={isConfirmed || isDiscarded}
            />
          </div>

          {/* Diagnosis, Allergies, Advice, Follow-up */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Diagnosis / Complaints */}
            <div className="p-5 rounded-2xl glass-panel border border-slate-800 space-y-2">
              <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                Complaints & Diagnosis
              </h4>
              {record.diagnosis && record.diagnosis.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {record.diagnosis.map((d, i) => (
                    <span
                      key={i}
                      className="px-2.5 py-1 rounded-lg text-xs bg-slate-900 border border-slate-800 text-slate-200"
                    >
                      {d}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-500">None detected</p>
              )}
            </div>

            {/* Allergies */}
            <div className="p-5 rounded-2xl glass-panel border border-slate-800 space-y-2">
              <h4 className="text-xs font-semibold text-amber-300 uppercase tracking-wider flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5" />
                Allergies & Contraindications
              </h4>
              {record.allergies && record.allergies.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {record.allergies.map((a, i) => (
                    <span
                      key={i}
                      className="px-2.5 py-1 rounded-lg text-xs bg-rose-500/20 border border-rose-500/40 text-rose-200 font-semibold"
                    >
                      {a}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-500">No allergy statements found (e.g. NKDA)</p>
              )}
            </div>

            {/* Advice */}
            <div className="p-5 rounded-2xl glass-panel border border-slate-800 space-y-2">
              <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                Physician Advice & Instructions
              </h4>
              {record.advice && record.advice.length > 0 ? (
                <ul className="list-disc list-inside space-y-1 text-xs text-slate-300">
                  {record.advice.map((adv, i) => (
                    <li key={i}>{adv}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-500">None detected</p>
              )}
            </div>

            {/* Follow-up */}
            <div className="p-5 rounded-2xl glass-panel border border-slate-800 space-y-2">
              <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                Follow-up / Review Instructions
              </h4>
              <p className="text-xs text-slate-200">
                {record.follow_up || "None specified"}
              </p>
            </div>
          </div>

          {/* Bottom Confirmation Action Bar */}
          {isPending && (
            <div className="sticky bottom-4 p-4 rounded-2xl bg-slate-900/95 border border-cyan-500/30 backdrop-blur-xl shadow-2xl flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <ShieldCheck className="w-5 h-5 text-cyan-400" />
                <div>
                  <span className="text-xs font-semibold text-slate-200 block">
                    Authorize Clinical Sign-off
                  </span>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[11px] text-slate-400">Reviewer ID:</span>
                    <input
                      type="text"
                      value={confirmedBy}
                      onChange={(e) => setConfirmedBy(e.target.value)}
                      placeholder="e.g. Dr. John Doe"
                      className="text-xs px-2 py-0.5 rounded bg-slate-950 border border-slate-700 text-slate-200 focus:outline-none focus:border-cyan-500"
                    />
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  disabled={discarding}
                  onClick={handleDiscard}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-rose-500/20 text-slate-300 hover:text-rose-300 text-xs font-semibold transition-colors"
                >
                  {discarding ? "Discarding..." : "Discard Draft"}
                </button>

                <button
                  type="button"
                  disabled={confirming}
                  onClick={() => handleConfirm(false)}
                  className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-slate-950 font-bold text-xs shadow-lg shadow-emerald-500/20 transition-all hover:scale-[1.02] active:scale-[0.98]"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  {confirming ? "Saving Record..." : "Confirm & Save to Record"}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* RAW OCR INSPECTOR TAB */}
      {activeTab === "rawOcr" && (
        <div className="space-y-4">
          {rawOcr ? (
            <RawOcrViewer data={rawOcr} />
          ) : (
            <div className="p-8 text-center rounded-2xl bg-slate-900/60 border border-slate-800 text-slate-400 text-xs">
              <RefreshCw className="w-4 h-4 animate-spin mx-auto mb-2 text-cyan-400" />
              Loading raw OCR lines...
            </div>
          )}
        </div>
      )}
    </div>
  );
}
