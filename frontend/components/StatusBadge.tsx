import React from "react";
import { QualityGateStatus, ExtractionStatus, FieldValidationFlag, MedicineStatus } from "@/lib/types";
import { CheckCircle2, AlertTriangle, AlertCircle, HelpCircle, ShieldCheck, Database, XCircle } from "lucide-react";

interface BadgeProps {
  status?: QualityGateStatus | ExtractionStatus | MedicineStatus | string;
  flag?: FieldValidationFlag;
  size?: "sm" | "md" | "lg";
  showIcon?: boolean;
}

export function GateBadge({ status, size = "md" }: { status: QualityGateStatus; size?: "sm" | "md" }) {
  const isSm = size === "sm";
  switch (status) {
    case "HIGH_CONFIDENCE":
      return (
        <span className={`inline-flex items-center gap-1.5 font-medium rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 ${isSm ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm"}`}>
          <CheckCircle2 className={isSm ? "w-3 h-3" : "w-4 h-4"} />
          High Confidence
        </span>
      );
    case "NEEDS_CHECK":
      return (
        <span className={`inline-flex items-center gap-1.5 font-medium rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 ${isSm ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm"}`}>
          <AlertTriangle className={isSm ? "w-3 h-3" : "w-4 h-4"} />
          Needs Review
        </span>
      );
    case "LOW_QUALITY":
      return (
        <span className={`inline-flex items-center gap-1.5 font-medium rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20 ${isSm ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm"}`}>
          <AlertCircle className={isSm ? "w-3 h-3" : "w-4 h-4"} />
          Low Quality Image
        </span>
      );
    default:
      return null;
  }
}

export function ExtractionStatusBadge({ status }: { status: ExtractionStatus }) {
  switch (status) {
    case "PENDING_USER_CONFIRMATION":
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20">
          <HelpCircle className="w-3 h-3" />
          Pending Review
        </span>
      );
    case "CONFIRMED":
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <CheckCircle2 className="w-3 h-3" />
          Confirmed
        </span>
      );
    case "DISCARDED":
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-500/10 text-slate-400 border border-slate-500/20">
          <XCircle className="w-3 h-3" />
          Discarded
        </span>
      );
    default:
      return null;
  }
}

export function FieldFlagBadge({ flag, conf }: { flag?: FieldValidationFlag; conf?: number | null }) {
  if (!flag) return null;
  const confText = conf !== null && conf !== undefined ? `(${(conf * 100).toFixed(0)}%)` : "";

  switch (flag) {
    case "ok":
      return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" title={`Confidence: ${(conf || 1) * 100}%`}>
          <CheckCircle2 className="w-3 h-3" />
          OK {confText}
        </span>
      );
    case "check":
      return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-mono bg-amber-500/10 text-amber-400 border border-amber-500/20" title="Check recommended / auto-corrected">
          <AlertTriangle className="w-3 h-3" />
          Check {confText}
        </span>
      );
    case "low":
      return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-mono bg-rose-500/10 text-rose-400 border border-rose-500/20" title="Low OCR confidence - please double-check">
          <AlertCircle className="w-3 h-3" />
          Low {confText}
        </span>
      );
    case "missing":
      return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-mono bg-rose-500/20 text-rose-300 border border-rose-500/30">
          <AlertCircle className="w-3 h-3" />
          Missing
        </span>
      );
    case "empty":
      return (
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-mono bg-slate-800 text-slate-400 border border-slate-700">
          Not detected
        </span>
      );
    default:
      return null;
  }
}

export function MedicineDbBadge({
  verified,
  score,
  generic,
}: {
  verified?: boolean;
  score?: number | null;
  generic?: string | null;
}) {
  if (verified) {
    return (
      <span
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-teal-500/10 text-teal-300 border border-teal-500/30"
        title={`Verified in Medicine Master${generic ? `: ${generic}` : ""}`}
      >
        <ShieldCheck className="w-3.5 h-3.5 text-teal-400" />
        DB Verified
      </span>
    );
  }

  if (score && score >= 85) {
    return (
      <span
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-500/10 text-amber-300 border border-amber-500/30"
        title={`Near match (${score}%) in database - confirm exact name`}
      >
        <Database className="w-3.5 h-3.5 text-amber-400" />
        Near Match ({score}%)
      </span>
    );
  }

  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700"
      title="Not present in verified local medicine master"
    >
      Unverified Drug
    </span>
  );
}
