"use client";

import React, { useState } from "react";
import { RawOcrData } from "@/lib/types";
import { Search, Hash, AlignLeft, ShieldAlert } from "lucide-react";

export function RawOcrViewer({ data }: { data: RawOcrData }) {
  const [filter, setFilter] = useState("");

  const filteredLines = (data.lines || []).filter((line) =>
    line.text.toLowerCase().includes(filter.toLowerCase()) ||
    line.id.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl bg-slate-900/60 border border-slate-800">
        <div className="flex items-center gap-6 text-xs text-slate-400">
          <div>
            <span className="text-slate-500 block">OCR Engine</span>
            <span className="font-semibold text-slate-200">{data.ocr_engine}</span>
          </div>
          <div>
            <span className="text-slate-500 block">Total Lines</span>
            <span className="font-semibold text-slate-200">{data.lines?.length || 0}</span>
          </div>
          <div>
            <span className="text-slate-500 block">Average Confidence</span>
            <span className="font-semibold text-emerald-400">
              {((data.avg_conf || 1) * 100).toFixed(1)}%
            </span>
          </div>
          <div>
            <span className="text-slate-500 block">Image Resolution</span>
            <span className="font-semibold text-slate-200">
              {data.image_w} × {data.image_h} px
            </span>
          </div>
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
          <input
            type="text"
            placeholder="Search OCR lines..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-xs rounded-lg bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
          />
        </div>
      </div>

      <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-950/80">
        <div className="max-h-96 overflow-y-auto">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-slate-900/90 text-slate-400 border-b border-slate-800 font-medium">
              <tr>
                <th className="py-2.5 px-3 w-16">Line</th>
                <th className="py-2.5 px-3 w-14">Row</th>
                <th className="py-2.5 px-3">Extracted Text</th>
                <th className="py-2.5 px-3 w-28">Confidence</th>
                <th className="py-2.5 px-3 w-28">Position (x, y)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
              {filteredLines.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-slate-500 font-sans">
                    No matching OCR lines found
                  </td>
                </tr>
              ) : (
                filteredLines.map((line) => {
                  const confPct = Math.round(line.conf * 100);
                  const isLow = line.conf < 0.75;
                  return (
                    <tr
                      key={line.id}
                      className="hover:bg-slate-900/50 transition-colors"
                    >
                      <td className="py-2 px-3 text-cyan-400 font-bold">{line.id}</td>
                      <td className="py-2 px-3 text-slate-500">{line.row}</td>
                      <td className="py-2 px-3 font-sans text-slate-200">{line.text}</td>
                      <td className="py-2 px-3">
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                            <div
                              className={`h-full ${
                                isLow ? "bg-rose-500" : "bg-emerald-500"
                              }`}
                              style={{ width: `${confPct}%` }}
                            />
                          </div>
                          <span
                            className={
                              isLow ? "text-rose-400 text-[11px]" : "text-emerald-400 text-[11px]"
                            }
                          >
                            {confPct}%
                          </span>
                        </div>
                      </td>
                      <td className="py-2 px-3 text-slate-500 text-[11px]">
                        {line.x.toFixed(2)}, {line.y.toFixed(2)}
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
  );
}
