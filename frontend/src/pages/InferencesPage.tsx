import { useState, useEffect, useCallback } from 'react';
import {
  Search, RefreshCw, AlertTriangle, ShieldCheck, Lock,
  ChevronLeft, ChevronRight, Eye, Filter,
} from 'lucide-react';
import { fetchInferences } from '../api/client';
import type { InferenceRecord } from '../types/api';

const PAGE_SIZE = 25;

function SensitivityBadge({ level }: { level: string | null }) {
  if (!level) return <span className="text-xs text-slate-400">-</span>;
  const colors: Record<string, string> = {
    CRITICAL: 'bg-red-100 text-red-700 border-red-200',
    HIGH: 'bg-orange-100 text-orange-700 border-orange-200',
    MODERATE: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    LOW: 'bg-green-100 text-green-700 border-green-200',
  };
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${colors[level] || 'bg-slate-100 text-slate-700'}`}>
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

  // Filters
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

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Inference Log</h1>
          <p className="mt-1 text-sm text-slate-500">
            Browse and inspect inference records ({total.toLocaleString()} total)
          </p>
        </div>
        <button
          onClick={() => { setOffset(0); load(); }}
          className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <Filter className="h-4 w-4 text-slate-400" />

        <select
          value={days}
          onChange={(e) => { setDays(Number(e.target.value)); setOffset(0); }}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700"
        >
          <option value={1}>Last 24h</option>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>

        <select
          value={filterPii === undefined ? '' : String(filterPii)}
          onChange={(e) => {
            setFilterPii(e.target.value === '' ? undefined : e.target.value === 'true');
            setOffset(0);
          }}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700"
        >
          <option value="">All PII status</option>
          <option value="true">PHI detected</option>
          <option value="false">No PHI</option>
        </select>

        <select
          value={filterOutlier === undefined ? '' : String(filterOutlier)}
          onChange={(e) => {
            setFilterOutlier(e.target.value === '' ? undefined : e.target.value === 'true');
            setOffset(0);
          }}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700"
        >
          <option value="">All outlier status</option>
          <option value="true">Outliers only</option>
          <option value="false">Normal only</option>
        </select>

        <span className="ml-auto text-xs text-slate-400">
          {total.toLocaleString()} records match
        </span>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-4">
          <AlertTriangle className="h-5 w-5 text-red-500" />
          <span className="text-sm text-red-700">{error}</span>
        </div>
      )}

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Time</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">ID</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Prediction</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">PHI</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Sensitivity</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Quality</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Enc</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center">
                    <RefreshCw className="mx-auto h-6 w-6 animate-spin text-slate-400" />
                    <p className="mt-2 text-sm text-slate-400">Loading...</p>
                  </td>
                </tr>
              ) : records.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center">
                    <Search className="mx-auto h-6 w-6 text-slate-300" />
                    <p className="mt-2 text-sm text-slate-400">No inferences found</p>
                  </td>
                </tr>
              ) : (
                records.map((inf) => {
                  const time = new Date(inf.received_at);
                  return (
                    <tr
                      key={inf.id}
                      className={`cursor-pointer hover:bg-slate-50 ${selectedId === inf.id ? 'bg-blue-50' : ''}`}
                      onClick={() => setSelectedId(selectedId === inf.id ? null : inf.id)}
                    >
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-600">
                        {time.toLocaleDateString()} {time.toLocaleTimeString()}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-slate-500">
                        {inf.id.slice(0, 16)}...
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-sm font-medium text-slate-700">
                        {inf.prediction.toFixed(4)}
                        {inf.confidence !== null && (
                          <span className="ml-1 text-xs text-slate-400">
                            ({(inf.confidence * 100).toFixed(0)}%)
                          </span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        {inf.pii_detected ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                            <ShieldCheck className="h-3 w-3" />
                            {inf.pii_redaction_count} redacted
                          </span>
                        ) : (
                          <span className="text-xs text-slate-400">None</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <SensitivityBadge level={inf.max_sensitivity_level} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        {inf.has_quality_issues ? (
                          <span className="inline-flex items-center gap-1 text-xs text-amber-600">
                            <AlertTriangle className="h-3 w-3" /> Issues
                          </span>
                        ) : inf.is_outlier ? (
                          <span className="inline-flex items-center gap-1 text-xs text-red-600">
                            <AlertTriangle className="h-3 w-3" /> Outlier
                          </span>
                        ) : (
                          <span className="text-xs text-green-600">OK</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                          <Lock className="h-3 w-3" /> v{inf.encryption_key_version}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <Eye className="h-4 w-4 text-slate-400" />
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
          <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-4 py-3">
            <span className="text-xs text-slate-500">
              Page {currentPage} of {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                disabled={offset === 0}
                className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-40"
              >
                <ChevronLeft className="h-3 w-3" /> Previous
              </button>
              <button
                onClick={() => setOffset(offset + PAGE_SIZE)}
                disabled={(offset + PAGE_SIZE) >= total}
                className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-40"
              >
                Next <ChevronRight className="h-3 w-3" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Detail Panel */}
      {selected && (
        <div className="mt-6 rounded-xl border border-slate-200 bg-white p-6">
          <h3 className="mb-4 text-sm font-semibold text-slate-800">
            Inference Detail: <span className="font-mono text-blue-600">{selected.id}</span>
          </h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <p className="text-xs font-medium text-slate-400 uppercase">Prediction</p>
              <p className="text-sm text-slate-700">{selected.prediction}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-400 uppercase">Confidence</p>
              <p className="text-sm text-slate-700">{selected.confidence !== null ? `${(selected.confidence * 100).toFixed(1)}%` : 'N/A'}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-400 uppercase">Received At</p>
              <p className="text-sm text-slate-700">{new Date(selected.received_at).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-400 uppercase">PHI Redacted</p>
              <p className="text-sm text-slate-700">{selected.pii_redaction_count} items</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-400 uppercase">PII Types</p>
              <p className="text-sm text-slate-700">
                {selected.pii_types_found
                  ? Object.entries(selected.pii_types_found).map(([k, v]) => `${k}: ${v}`).join(', ')
                  : 'None'}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-400 uppercase">Sensitivity</p>
              <SensitivityBadge level={selected.max_sensitivity_level} />
            </div>
            <div>
              <p className="text-xs font-medium text-slate-400 uppercase">Data Types</p>
              <p className="text-sm text-slate-700">
                {[
                  selected.contains_clinical_data && 'Clinical',
                  selected.contains_behavioral_health && 'Behavioral',
                  selected.contains_genetic_data && 'Genetic',
                ].filter(Boolean).join(', ') || 'Standard'}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-400 uppercase">Encryption</p>
              <p className="text-sm text-slate-700">AES-128-CBC (key v{selected.encryption_key_version})</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-400 uppercase">Source IP</p>
              <p className="text-sm text-slate-700">{selected.source_ip || 'N/A'}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
