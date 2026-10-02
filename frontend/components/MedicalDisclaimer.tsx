import React from "react";
import { AlertTriangle, ShieldAlert } from "lucide-react";

export function MedicalDisclaimer({ compact = false }: { compact?: boolean }) {
  if (compact) {
    return (
      <div className="flex items-center gap-2 p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs">
        <ShieldAlert className="w-4 h-4 shrink-0 text-amber-400" />
        <span>
          <strong>Clinical Review Required:</strong> Unverified AI draft. An authorized medical professional must verify all medication names, strengths, and dosages before clinical use.
        </span>
      </div>
    );
  }

  return (
    <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-200 text-sm flex items-start gap-3 shadow-sm">
      <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400 shrink-0 mt-0.5">
        <AlertTriangle className="w-5 h-5" />
      </div>
      <div className="space-y-1">
        <h4 className="font-semibold text-amber-300 text-sm tracking-wide uppercase">
          Unverified Clinical Draft & Safety Notice
        </h4>
        <p className="text-xs text-amber-200/90 leading-relaxed">
          This document has been extracted by PaddleOCR-VL and structured using Google Gemini. It represents an unverified draft for physician and pharmacist review. Do not administer medication or rely on these values without direct verification against the original signed prescription.
        </p>
      </div>
    </div>
  );
}
