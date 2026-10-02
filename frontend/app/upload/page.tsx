"use client";

import React, { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import {
  Upload,
  FileImage,
  X,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  ArrowRight,
  ShieldAlert,
  Sparkles,
  Info,
} from "lucide-react";
import { clientApi } from "@/lib/api";
import { MedicalDisclaimer } from "@/components/MedicalDisclaimer";

const MAX_UPLOAD_MB = 10;
const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;
const ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"];

type ProcessingStep = "idle" | "uploading" | "ocr" | "structuring" | "finalizing" | "success" | "error";

export default function UploadPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [patientId, setPatientId] = useState("");
  const [patientName, setPatientName] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);

  const [step, setStep] = useState<ProcessingStep>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [rawOcrId, setRawOcrId] = useState<number | undefined>(undefined);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const handleFileSelect = (file: File) => {
    setErrorMessage(null);

    if (!ALLOWED_MIME_TYPES.includes(file.type)) {
      setErrorMessage(`Invalid file format (${file.type || "unknown"}). Please upload a JPEG, PNG, or WebP image.`);
      return;
    }

    if (file.size > MAX_UPLOAD_BYTES) {
      setErrorMessage(
        `File size (${(file.size / (1024 * 1024)).toFixed(1)} MB) exceeds maximum limit of ${MAX_UPLOAD_MB} MB.`
      );
      return;
    }

    setSelectedFile(file);
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleRemoveFile = () => {
    setSelectedFile(null);
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    setErrorMessage(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setErrorMessage("Please select a prescription image.");
      return;
    }
    if (!patientId.trim()) {
      setErrorMessage("Please enter a Patient ID / UHID.");
      return;
    }

    setErrorMessage(null);
    setStep("uploading");
    setElapsedSeconds(0);

    // Live elapsed timer for realistic transparency during heavy CPU vision inference
    const timerInterval = setInterval(() => {
      setElapsedSeconds((prev) => {
        const next = prev + 1;
        if (next >= 3 && next < 45) {
          setStep("ocr");
        } else if (next >= 45 && next < 65) {
          setStep("structuring");
        } else if (next >= 65) {
          setStep("finalizing");
        }
        return next;
      });
    }, 1000);

    try {
      const result = await clientApi.uploadPrescription(
        selectedFile,
        patientId.trim(),
        patientName.trim() || undefined
      );

      clearInterval(timerInterval);
      setStep("success");

      // Redirect directly to review the extracted draft
      router.push(`/extractions/${result.extraction_id}`);
    } catch (err: any) {
      clearInterval(timerInterval);
      setStep("error");
      setErrorMessage(err.message || "Failed to process prescription image.");
      if (err.rawOcrId) {
        setRawOcrId(err.rawOcrId);
      }
    }
  };

  const handleRetryStructuring = async () => {
    if (!rawOcrId) return;
    setStep("structuring");
    setErrorMessage(null);

    try {
      const result = await clientApi.retryStructure(rawOcrId, patientName || undefined);
      setStep("success");
      router.push(`/extractions/${result.extraction_id}`);
    } catch (err: any) {
      setStep("error");
      setErrorMessage(err.message || "Retry structuring failed.");
    }
  };

  const isProcessing = step !== "idle" && step !== "error" && step !== "success";

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
          <Upload className="w-6 h-6 text-cyan-400" />
          Process Medical Prescription
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Upload handwritten or printed prescription images to extract text with PaddleOCR-VL and clinical entities with Gemini.
        </p>
      </div>

      <MedicalDisclaimer compact />

      {/* Main Upload Card */}
      <form onSubmit={handleSubmit} className="p-6 rounded-2xl glass-panel border border-slate-800 space-y-6">
        {/* Patient Details */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">
              Patient ID / UHID <span className="text-cyan-400">*</span>
            </label>
            <input
              type="text"
              required
              disabled={isProcessing}
              placeholder="e.g. NCRI/21/1427 or P10023"
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
              className="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors"
            />
            <p className="text-[11px] text-slate-500 mt-1">
              Required by hospital workflow to link prescriptions to patient history.
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">
              Expected Patient Name <span className="text-slate-500">(Optional)</span>
            </label>
            <input
              type="text"
              disabled={isProcessing}
              placeholder="e.g. Dalia Kundu"
              value={patientName}
              onChange={(e) => setPatientName(e.target.value)}
              className="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors"
            />
            <p className="text-[11px] text-slate-500 mt-1">
              Used by AI validator to cross-check extracted patient name.
            </p>
          </div>
        </div>

        {/* Drag and Drop Zone / Image Preview */}
        {!selectedFile ? (
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all ${
              isDragOver
                ? "border-cyan-400 bg-cyan-500/10"
                : "border-slate-800 hover:border-slate-700 bg-slate-950/60"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".jpg,.jpeg,.png,.webp"
              onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
              className="hidden"
            />
            <div className="mx-auto w-12 h-12 rounded-xl bg-cyan-500/10 text-cyan-400 flex items-center justify-center mb-3">
              <FileImage className="w-6 h-6" />
            </div>
            <h3 className="text-sm font-semibold text-slate-200">
              Drop prescription image here, or <span className="text-cyan-400 underline">browse</span>
            </h3>
            <p className="text-xs text-slate-500 mt-1">
              Supports JPEG, PNG, and WebP (up to {MAX_UPLOAD_MB} MB)
            </p>
          </div>
        ) : (
          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs text-slate-300 font-medium truncate">
                <FileImage className="w-4 h-4 text-cyan-400 shrink-0" />
                <span className="truncate">{selectedFile.name}</span>
                <span className="text-slate-500 shrink-0">
                  ({(selectedFile.size / (1024 * 1024)).toFixed(2)} MB)
                </span>
              </div>
              {!isProcessing && (
                <button
                  type="button"
                  onClick={handleRemoveFile}
                  className="p-1 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-900 transition-colors"
                  title="Remove image"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            {previewUrl && (
              <div className="relative max-h-72 w-full overflow-hidden rounded-lg border border-slate-800/80 bg-slate-900/40 flex justify-center">
                <img
                  src={previewUrl}
                  alt="Prescription preview"
                  className="object-contain max-h-72 w-auto"
                />
              </div>
            )}
          </div>
        )}

        {/* Error message alert */}
        {errorMessage && (
          <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-start gap-2.5">
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-400 mt-0.5" />
            <div className="flex-1 space-y-2">
              <div className="font-semibold text-rose-200">Processing Alert</div>
              <div className="leading-relaxed">{errorMessage}</div>
              <div className="pt-1 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setErrorMessage(null);
                    setStep("idle");
                    setElapsedSeconds(0);
                  }}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs border border-slate-700 transition-colors"
                >
                  <RefreshCw className="w-3 h-3" />
                  Try Again / Re-upload
                </button>
                <button
                  type="button"
                  onClick={() => router.push("/")}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-200 font-semibold text-xs border border-cyan-500/40 transition-colors"
                >
                  <ArrowRight className="w-3 h-3" />
                  Check Dashboard for Results
                </button>
                {rawOcrId && (
                  <button
                    type="button"
                    onClick={handleRetryStructuring}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 font-medium text-xs transition-colors"
                  >
                    <RefreshCw className="w-3 h-3" />
                    Retry Gemini Structuring (stored OCR #{rawOcrId})
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Processing Indicator State */}
        {isProcessing && (
          <div className="p-5 rounded-xl bg-slate-950/80 border border-cyan-500/30 space-y-3">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-200">
              <span className="flex items-center gap-2">
                <RefreshCw className="w-4 h-4 text-cyan-400 animate-spin" />
                {step === "uploading" && "Uploading prescription image..."}
                {step === "ocr" && "PaddleOCR-VL analyzing document layout & vision tokens on CPU..."}
                {step === "structuring" && "Google Gemini structuring medications, vitals & dosages..."}
                {step === "finalizing" && "Validating against Drug Master & checking clinical safety rules..."}
              </span>
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded-full bg-slate-800 text-[11px] font-mono text-cyan-300 border border-slate-700">
                  ⏱️ {elapsedSeconds}s
                </span>
                <span className="font-mono text-cyan-400">
                  {step === "uploading"
                    ? "15%"
                    : step === "ocr"
                    ? `${Math.min(75, 20 + Math.floor(elapsedSeconds * 1.2))}%`
                    : step === "structuring"
                    ? "85%"
                    : "95%"}
                </span>
              </div>
            </div>

            <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-cyan-500 to-teal-400 transition-all duration-500 ease-out"
                style={{
                  width:
                    step === "uploading"
                      ? "15%"
                      : step === "ocr"
                      ? `${Math.min(75, 20 + Math.floor(elapsedSeconds * 1.2))}%`
                      : step === "structuring"
                      ? "85%"
                      : "95%",
                }}
              />
            </div>

            <div className="flex items-start justify-between text-[11px] text-slate-400 leading-relaxed">
              <span>
                {elapsedSeconds > 60
                  ? "PaddleOCR-VL is processing complex vision tokens on CPU. The pipeline is actively running—please keep this page open."
                  : "Note: PaddleOCR-VL runs on CPU (typically 30–60s). Please keep this page open."}
              </span>
            </div>
          </div>
        )}

        {/* Action Button */}
        <div className="flex items-center justify-end gap-3 pt-2 border-t border-slate-800/80">
          <button
            type="submit"
            disabled={!selectedFile || !patientId.trim() || isProcessing}
            className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-teal-500 hover:from-cyan-400 hover:to-teal-400 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm shadow-lg shadow-cyan-500/20 transition-all"
          >
            {isProcessing ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Processing...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                Process Prescription
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
