import { useState, useEffect, useCallback } from 'react';
import {
  Search, RefreshCw, AlertTriangle, ShieldCheck, Lock,
  ChevronLeft, ChevronRight, Eye, Filter, X,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { fetchInferences } from '../api/client';
import type { InferenceRecord } from '../types/api';

const PAGE_SIZE = 25;

function SensitivityBadge({ level }: { level: string | null }) {
  if (!level) return <span className="text-xs text-slate-600">-</span>;
  const colors: Record<string, string> = {
    CRITICAL: 'bg-red-500/10 text-red-400 border-red-500/20',
    HIGH: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
    MODERATE: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    LOW: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  };
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${colors[level] || 'bg-slate-500/10 text-slate-400'}`}>
      {level}
    </span>
  );
}

export function InferencesPage() {
  const [records, setRecords] = useState<InferenceRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [filterPii, setFilterPii] = useState<boolean | undefined>(undefined);
  const [filterOutlier, setFilterOutlier] = useState<boolean | undefined>(undefined);
  const [days, setDays] = useState(7);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchInferences({
        days,
        has_pii: filterPii,
        is_outlier: filterOutlier,
        limit: PAGE_SIZE,
        offset,
      });
      setRecords(data.inferences);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load inferences');
    } finally {
      setLoading(false);
    }
  }, [days, filterPii, filterOutlier, offset]);

  useEffect(() => {
    load();
  }, [load]);

  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const selected = selectedId ? records.find((r) => r.id === selectedId) : null;

  const selectClasses = "rounded-lg px-3 py-1.5 text-sm text-slate-300 appearance-none cursor-pointer transition-colors hover:border-cyan-500/30 focus:border-cyan-500/50 focus:outline-none";
  const selectStyle = { background: 'rgba(30, 41, 59, 0.5)', border: '1px solid var(--border-default)' };

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Inference Log</h1>
          <p className="mt-1 text-sm text-slate-500">
            Browse and inspect inference records ({total.toLocaleString()} total)
          </p>
        </div>
        <button
          onClick={() => { setOffset(0); load(); }}
          className="glass-card-static flex items-center gap-2 px-4 py-2 text-sm text-slate-400 hover:text-cyan-400 transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="mb-6 glass-card-static flex flex-wrap items-center gap-3 p-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-500/10">
          <Filter className="h-4 w-4 text-cyan-400" />
        </div>

        <select value={days} onChange={(e) => { setDays(Number(e.target.value)); setOffset(0); }}
          className={selectClasses} style={selectStyle}>
          <option value={1}>Last 24h</option>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>

        <select value={filterPii === undefined ? '' : String(filterPii)}
          onChange={(e) => { setFilterPii(e.target.value === '' ? undefined : e.target.value === 'true'); setOffset(0); }}
          className={selectClasses} style={selectStyle}>
          <option value="">All PII status</option>
          <option value="true">PHI detected</option>
          <option value="false">No PHI</option>
        </select>

        <select value={filterOutlier === undefined ? '' : String(filterOutlier)}
          onChange={(e) => { setFilterOutlier(e.target.value === '' ? undefined : e.target.value === 'true'); setOffset(0); }}
          className={selectClasses} style={selectStyle}>
          <option value="">All outlier status</option>
          <option value="true">Outliers only</option>
          <option value="false">Normal only</option>
        </select>

        <span className="ml-auto text-xs text-slate-500">
          {total.toLocaleString()} records
        </span>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 flex items-center gap-3 glass-card-static p-4" style={{ borderColor: 'rgba(239, 68, 68, 0.2)' }}>
          <AlertTriangle className="h-5 w-5 text-red-400" />
          <span className="text-sm text-red-300">{error}</span>
        </div>
      )}

      {/* Table */}
      <div className="glass-card-static overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-default)' }}>
                {['Time', 'ID', 'Prediction', 'PHI', 'Sensitivity', 'Quality', 'Enc', ''].map((h) => (
                  <th key={h} className="px-4 py-3.5 text-left text-[10px] font-semibold uppercase tracking-[0.15em] text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-4 py-16 text-center">
                    <RefreshCw className="mx-auto h-6 w-6 animate-spin text-cyan-400" />
                    <p className="mt-3 text-sm text-slate-500">Loading...</p>
                  </td>
                </tr>
              ) : records.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-16 text-center">
                    <Search className="mx-auto h-6 w-6 text-slate-600" />
                    <p className="mt-3 text-sm text-slate-500">No inferences found</p>
                  </td>
                </tr>
              ) : (
                records.map((inf) => {
                  const time = new Date(inf.received_at);
                  return (
                    <tr
                      key={inf.id}
                      className={`cursor-pointer table-row-hover ${selectedId === inf.id ? 'bg-cyan-500/5' : ''}`}
                      style={{ borderBottom: '1px solid var(--border-subtle)' }}
                      onClick={() => setSelectedId(selectedId === inf.id ? null : inf.id)}
                    >
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">
                        {time.toLocaleDateString()} {time.toLocaleTimeString()}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-slate-500">
                        {inf.id.slice(0, 12)}...
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-sm font-semibold text-slate-200">
                        {inf.prediction.toFixed(4)}
                        {inf.confidence !== null && (
                          <span className="ml-1.5 text-xs font-normal text-slate-500">
                            {(inf.confidence * 100).toFixed(0)}%
                          </span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        {inf.pii_detected ? (
                          <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-[10px] font-bold text-emerald-400">
                            <ShieldCheck className="h-3 w-3" />
                            {inf.pii_redaction_count}
                          </span>
                        ) : (
                          <span className="text-xs text-slate-600">-</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <SensitivityBadge level={inf.max_sensitivity_level} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        {inf.has_quality_issues ? (
                          <span className="inline-flex items-center gap-1 text-xs text-amber-400">
                            <AlertTriangle className="h-3 w-3" /> Issues
                          </span>
                        ) : inf.is_outlier ? (
                          <span className="inline-flex items-center gap-1 text-xs text-red-400">
                            <AlertTriangle className="h-3 w-3" /> Outlier
                          </span>
                        ) : (
                          <span className="text-xs text-emerald-400">OK</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                          <Lock className="h-3 w-3" /> v{inf.encryption_key_version}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <Eye className={`h-4 w-4 ${selectedId === inf.id ? 'text-cyan-400' : 'text-slate-600'}`} />
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3" style={{ borderTop: '1px solid var(--border-default)' }}>
            <span className="text-xs text-slate-500">
              Page {currentPage} of {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                disabled={offset === 0}
                className="glass-card-static inline-flex items-center gap-1 px-3 py-1.5 text-xs text-slate-400 hover:text-cyan-400 disabled:opacity-30 disabled:hover:text-slate-400 transition-colors"
              >
                <ChevronLeft className="h-3 w-3" /> Previous
              </button>
              <button
                onClick={() => setOffset(offset + PAGE_SIZE)}
                disabled={(offset + PAGE_SIZE) >= total}
                className="glass-card-static inline-flex items-center gap-1 px-3 py-1.5 text-xs text-slate-400 hover:text-cyan-400 disabled:opacity-30 disabled:hover:text-slate-400 transition-colors"
              >
                Next <ChevronRight className="h-3 w-3" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Detail Panel */}
      <AnimatePresence>
        {selected && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            transition={{ duration: 0.2 }}
            className="mt-6 glass-card-static p-6"
          >
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-sm font-semibold text-slate-200">
                Inference Detail
              </h3>
              <button onClick={() => setSelectedId(null)} className="text-slate-500 hover:text-slate-300">
                <X className="h-4 w-4" />
              </button>
            </div>
            <p className="mb-4 font-mono text-xs text-cyan-400">{selected.id}</p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <DetailField label="Prediction" value={String(selected.prediction)} />
              <DetailField label="Confidence" value={selected.confidence !== null ? `${(selected.confidence * 100).toFixed(1)}%` : 'N/A'} />
              <DetailField label="Received At" value={new Date(selected.received_at).toLocaleString()} />
              <DetailField label="PHI Redacted" value={`${selected.pii_redaction_count} items`} />
              <DetailField label="PII Types" value={selected.pii_types_found
                ? Object.entries(selected.pii_types_found).map(([k, v]) => `${k}: ${v}`).join(', ')
                : 'None'} />
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1">Sensitivity</p>
                <SensitivityBadge level={selected.max_sensitivity_level} />
              </div>
              <DetailField label="Data Types" value={[
                selected.contains_clinical_data && 'Clinical',
                selected.contains_behavioral_health && 'Behavioral',
                selected.contains_genetic_data && 'Genetic',
              ].filter(Boolean).join(', ') || 'Standard'} />
              <DetailField label="Encryption" value={`AES-128-CBC (key v${selected.encryption_key_version})`} />
              <DetailField label="Source IP" value={selected.source_ip || 'N/A'} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function DetailField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1">{label}</p>
      <p className="text-sm text-slate-300">{value}</p>
    </div>
  );
}
