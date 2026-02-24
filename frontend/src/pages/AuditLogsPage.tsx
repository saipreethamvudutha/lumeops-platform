import { useState, useEffect, useCallback } from 'react';
import {
  ScrollText, RefreshCw, Search, Filter, Download, ChevronLeft,
  ChevronRight, X, Shield, Eye, AlertTriangle, Key, FileText,
  Activity, Globe, Clock, ChevronDown,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { fetchAuditTrail, fetchAuditTrailStats, downloadAuditTrailCsv } from '../api/client';
import type { AuditLogEntry, AuditTrailResponse, AuditTrailStats } from '../types/api';

// ── Action Type Metadata ──────────────────────────────────────────
const ACTION_META: Record<string, { label: string; color: string; icon: typeof Activity }> = {
  INFERENCE_RECEIVED: { label: 'Inference Received', color: 'cyan', icon: Activity },
  PII_DETECTED_AND_REDACTED: { label: 'PII Redacted', color: 'amber', icon: Shield },
  REPORT_GENERATED: { label: 'Report Generated', color: 'violet', icon: FileText },
  API_KEY_CREATED: { label: 'Key Created', color: 'emerald', icon: Key },
  API_KEY_REVOKED: { label: 'Key Revoked', color: 'red', icon: Key },
  ALERT_ACKNOWLEDGED: { label: 'Alert Acknowledged', color: 'blue', icon: Eye },
  ALERT_RESOLVED: { label: 'Alert Resolved', color: 'emerald', icon: Eye },
  ALERTS_BULK_ACKNOWLEDGED: { label: 'Alerts Bulk Ack', color: 'blue', icon: Eye },
  ENCRYPTION_KEY_ROTATED: { label: 'Key Rotated', color: 'violet', icon: Shield },
  ENCRYPTION_KEY_ROTATION_BATCH: { label: 'Key Rotation Batch', color: 'violet', icon: Shield },
  WEBHOOK_CREATED: { label: 'Webhook Created', color: 'cyan', icon: Globe },
  WEBHOOK_DELETED: { label: 'Webhook Deleted', color: 'red', icon: Globe },
};

const RESOURCE_TYPES = ['inference', 'api_key', 'report', 'alert', 'tenant', 'webhook'];
const DAY_OPTIONS = [7, 14, 30, 60, 90, 180, 365];
const PAGE_SIZE = 50;

function getActionMeta(action: string) {
  return ACTION_META[action] || { label: action, color: 'slate', icon: Activity };
}

function getColorClasses(color: string) {
  const map: Record<string, { bg: string; text: string; border: string }> = {
    cyan: { bg: 'bg-cyan-500/10', text: 'text-cyan-400', border: 'border-cyan-500/20' },
    amber: { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/20' },
    violet: { bg: 'bg-violet-500/10', text: 'text-violet-400', border: 'border-violet-500/20' },
    emerald: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20' },
    red: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/20' },
    blue: { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/20' },
    slate: { bg: 'bg-slate-500/10', text: 'text-slate-400', border: 'border-slate-500/20' },
  };
  return map[color] || map.slate;
}

export function AuditLogsPage() {
  // ── State ─────────────────────────────────────────────────────
  const [data, setData] = useState<AuditTrailResponse | null>(null);
  const [stats, setStats] = useState<AuditTrailStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedEntry, setSelectedEntry] = useState<AuditLogEntry | null>(null);

  // ── Filters ───────────────────────────────────────────────────
  const [days, setDays] = useState(30);
  const [actionFilter, setActionFilter] = useState<string>('');
  const [resourceFilter, setResourceFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(0);
  const [showFilters, setShowFilters] = useState(false);

  // ── Load Data ─────────────────────────────────────────────────
  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [trailData, statsData] = await Promise.all([
        fetchAuditTrail({
          days,
          action: actionFilter || undefined,
          resource_type: resourceFilter || undefined,
          search: searchQuery || undefined,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
        }),
        fetchAuditTrailStats(days),
      ]);
      setData(trailData);
      setStats(statsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load audit trail');
    } finally {
      setLoading(false);
    }
  }, [days, actionFilter, resourceFilter, searchQuery, page]);

  useEffect(() => { loadData(); }, [loadData]);

  // Reset page when filters change
  useEffect(() => { setPage(0); }, [days, actionFilter, resourceFilter, searchQuery]);

  const handleExport = async () => {
    setExporting(true);
    try {
      await downloadAuditTrailCsv({
        days,
        action: actionFilter || undefined,
        resource_type: resourceFilter || undefined,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to export CSV');
    } finally {
      setExporting(false);
    }
  };

  const clearFilters = () => {
    setActionFilter('');
    setResourceFilter('');
    setSearchQuery('');
    setDays(30);
  };

  const hasActiveFilters = actionFilter || resourceFilter || searchQuery || days !== 30;
  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  // ── Render ────────────────────────────────────────────────────
  return (
    <div className="p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Audit Trail</h1>
          <p className="mt-1 text-sm text-slate-500">
            HIPAA-compliant immutable event log for all system activity
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleExport}
            disabled={exporting || !data?.total}
            className="flex items-center gap-2 rounded-xl border border-slate-700 px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800/50 transition-all disabled:opacity-50"
          >
            {exporting ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            Export CSV
          </button>
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium text-white transition-all hover:opacity-90"
            style={{ background: 'var(--gradient-brand)' }}
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error Banner */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="mb-6 flex items-center gap-3 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3"
          >
            <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
            <p className="text-sm text-red-300">{error}</p>
            <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-300">
              <X className="h-4 w-4" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Stats Cards */}
      {stats && (
        <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard label="Total Events" value={stats.total_events} icon={ScrollText} color="cyan" />
          <StatCard label="PII Events" value={stats.pii_events} icon={Shield} color="amber" />
          <StatCard
            label="Action Types"
            value={Object.keys(stats.events_by_action).length}
            icon={Activity}
            color="violet"
          />
          <StatCard
            label="Resource Types"
            value={Object.keys(stats.events_by_resource_type).length}
            icon={Globe}
            color="emerald"
          />
        </div>
      )}

      {/* Filter Bar */}
      <div className="mb-4 glass-card-static p-4">
        <div className="flex items-center gap-3 flex-wrap">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by resource ID..."
              className="w-full rounded-lg border border-slate-700 bg-slate-900/50 pl-10 pr-4 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30"
            />
          </div>

          {/* Days Selector */}
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-lg border border-slate-700 bg-slate-900/50 px-3 py-2 text-sm text-slate-300 focus:border-cyan-500/50 focus:outline-none"
          >
            {DAY_OPTIONS.map((d) => (
              <option key={d} value={d}>{d} days</option>
            ))}
          </select>

          {/* Toggle Filters */}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium transition-all ${
              hasActiveFilters
                ? 'border-cyan-500/40 bg-cyan-500/10 text-cyan-300'
                : 'border-slate-700 text-slate-400 hover:border-slate-600'
            }`}
          >
            <Filter className="h-3.5 w-3.5" />
            Filters
            {hasActiveFilters && (
              <span className="ml-1 flex h-4 w-4 items-center justify-center rounded-full bg-cyan-500/20 text-[10px] text-cyan-300">
                !
              </span>
            )}
            <ChevronDown className={`h-3 w-3 transition-transform ${showFilters ? 'rotate-180' : ''}`} />
          </button>

          {/* Clear Filters */}
          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-all"
            >
              <X className="h-3 w-3" />
              Clear all
            </button>
          )}
        </div>

        {/* Expanded Filters */}
        <AnimatePresence>
          {showFilters && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <div className="mt-4 pt-4 flex gap-4 flex-wrap" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                {/* Action Filter */}
                <div className="flex-1 min-w-[180px]">
                  <label className="block text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-1.5">Action</label>
                  <select
                    value={actionFilter}
                    onChange={(e) => setActionFilter(e.target.value)}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900/50 px-3 py-2 text-sm text-slate-300 focus:border-cyan-500/50 focus:outline-none"
                  >
                    <option value="">All actions</option>
                    {Object.entries(ACTION_META).map(([key, meta]) => (
                      <option key={key} value={key}>{meta.label}</option>
                    ))}
                  </select>
                </div>

                {/* Resource Type Filter */}
                <div className="flex-1 min-w-[180px]">
                  <label className="block text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-1.5">Resource Type</label>
                  <select
                    value={resourceFilter}
                    onChange={(e) => setResourceFilter(e.target.value)}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900/50 px-3 py-2 text-sm text-slate-300 focus:border-cyan-500/50 focus:outline-none"
                  >
                    <option value="">All resources</option>
                    {RESOURCE_TYPES.map((rt) => (
                      <option key={rt} value={rt}>{rt}</option>
                    ))}
                  </select>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Loading */}
      {loading && !data && (
        <div className="flex h-64 items-center justify-center">
          <RefreshCw className="h-8 w-8 animate-spin text-cyan-400" />
        </div>
      )}

      {/* Audit Log Table */}
      {data && (
        <div className="glass-card-static overflow-hidden">
          {/* Table Header */}
          <div className="px-6 py-3 flex items-center justify-between" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
            <div className="flex items-center gap-2">
              <ScrollText className="h-4 w-4 text-cyan-400" />
              <h3 className="text-sm font-semibold text-slate-200">Events</h3>
            </div>
            <div className="flex items-center gap-3 text-xs text-slate-500">
              <span>{data.total.toLocaleString()} total</span>
              {totalPages > 1 && (
                <span>Page {page + 1} of {totalPages}</span>
              )}
            </div>
          </div>

          {/* Table Body */}
          <div className="divide-y divide-[var(--border-subtle)]">
            {data.entries.map((entry, i) => (
              <AuditRow
                key={entry.id}
                entry={entry}
                index={i}
                onClick={() => setSelectedEntry(entry)}
              />
            ))}
          </div>

          {/* Empty State */}
          {data.entries.length === 0 && (
            <div className="px-6 py-16 text-center">
              <div className="mx-auto h-12 w-12 rounded-xl flex items-center justify-center bg-slate-800/50 mb-3">
                <ScrollText className="h-5 w-5 text-slate-600" />
              </div>
              <p className="text-sm text-slate-500 mb-1">No audit events found</p>
              <p className="text-xs text-slate-600">Try adjusting your filters or time range</p>
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="px-6 py-3 flex items-center justify-between" style={{ borderTop: '1px solid var(--border-subtle)' }}>
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                Previous
              </button>
              <div className="flex items-center gap-1">
                {Array.from({ length: Math.min(7, totalPages) }, (_, i) => {
                  let pageNum: number;
                  if (totalPages <= 7) {
                    pageNum = i;
                  } else if (page < 4) {
                    pageNum = i;
                  } else if (page > totalPages - 4) {
                    pageNum = totalPages - 7 + i;
                  } else {
                    pageNum = page - 3 + i;
                  }
                  return (
                    <button
                      key={pageNum}
                      onClick={() => setPage(pageNum)}
                      className={`h-7 w-7 rounded-md text-xs font-medium transition-all ${
                        page === pageNum
                          ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/30'
                          : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800/50'
                      }`}
                    >
                      {pageNum + 1}
                    </button>
                  );
                })}
              </div>
              <button
                onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                disabled={page >= totalPages - 1}
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              >
                Next
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
        </div>
      )}

      {/* Detail Modal */}
      <AnimatePresence>
        {selectedEntry && (
          <AuditDetailModal entry={selectedEntry} onClose={() => setSelectedEntry(null)} />
        )}
      </AnimatePresence>

      {/* HIPAA Info */}
      <div className="mt-6 rounded-xl border border-slate-800 bg-slate-900/30 px-5 py-4">
        <div className="flex items-start gap-3">
          <Shield className="h-4 w-4 text-violet-400 mt-0.5 shrink-0" />
          <div className="text-xs text-slate-500 space-y-1">
            <p><strong className="text-slate-400">HIPAA Compliance:</strong></p>
            <ul className="list-disc list-inside space-y-0.5 ml-1">
              <li>All events are append-only (immutable) and cannot be modified or deleted</li>
              <li>Dual-write to PostgreSQL (primary) and Elasticsearch (secondary) for redundancy</li>
              <li>Audit logs are retained for 7 years per HIPAA 164.312(b) requirements</li>
              <li>No PHI is stored in audit logs; PII detection counts are recorded without the data itself</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
//  Sub-Components
// ══════════════════════════════════════════════════════════════════

function StatCard({ label, value, icon: Icon, color }: {
  label: string; value: number; icon: typeof Activity; color: string;
}) {
  const colors = getColorClasses(color);
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-4"
    >
      <div className="flex items-center gap-2 mb-2">
        <div className={`flex h-7 w-7 items-center justify-center rounded-lg ${colors.bg}`}>
          <Icon className={`h-3.5 w-3.5 ${colors.text}`} />
        </div>
        <p className="text-[10px] font-medium uppercase tracking-wider text-slate-500">{label}</p>
      </div>
      <p className="text-xl font-bold text-slate-100">{value.toLocaleString()}</p>
    </motion.div>
  );
}

function AuditRow({ entry, index, onClick }: {
  entry: AuditLogEntry; index: number; onClick: () => void;
}) {
  const meta = getActionMeta(entry.action);
  const colors = getColorClasses(meta.color);
  const Icon = meta.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15, delay: index * 0.02 }}
      onClick={onClick}
      className="flex items-center gap-4 px-6 py-3.5 table-row-hover cursor-pointer"
    >
      {/* Icon */}
      <div className={`flex h-9 w-9 items-center justify-center rounded-lg shrink-0 ${colors.bg}`}>
        <Icon className={`h-4 w-4 ${colors.text}`} />
      </div>

      {/* Action & Details */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={`text-sm font-medium ${colors.text}`}>{meta.label}</span>
          {entry.pii_detected && (
            <span className="rounded-md px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider bg-amber-500/10 text-amber-400 border border-amber-500/20">
              PHI
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          {entry.resource_type && (
            <span className="text-[10px] text-slate-500">{entry.resource_type}</span>
          )}
          {entry.resource_id && (
            <span className="text-[10px] text-slate-600 font-mono truncate max-w-[180px]">
              {entry.resource_id}
            </span>
          )}
        </div>
      </div>

      {/* IP / Key */}
      <div className="hidden lg:block text-right shrink-0">
        {entry.api_key_prefix && (
          <p className="text-[10px] text-slate-500 font-mono">{entry.api_key_prefix}***</p>
        )}
        {entry.ip_address && (
          <p className="text-[10px] text-slate-600">{entry.ip_address}</p>
        )}
      </div>

      {/* Status */}
      <span className={`rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border shrink-0 ${
        entry.status === 'success'
          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
          : 'bg-red-500/10 text-red-400 border-red-500/20'
      }`}>
        {entry.status}
      </span>

      {/* Timestamp */}
      <div className="flex items-center gap-1 text-[10px] text-slate-600 shrink-0 w-[130px] justify-end">
        <Clock className="h-3 w-3" />
        {new Date(entry.timestamp).toLocaleString(undefined, {
          month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
        })}
      </div>
    </motion.div>
  );
}

function AuditDetailModal({ entry, onClose }: {
  entry: AuditLogEntry; onClose: () => void;
}) {
  const meta = getActionMeta(entry.action);
  const colors = getColorClasses(meta.color);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
        className="w-full max-w-xl glass-card-static p-6 mx-4 max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${colors.bg}`}>
              <meta.icon className={`h-5 w-5 ${colors.text}`} />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-100">{meta.label}</h2>
              <p className="text-xs text-slate-500">Audit Event Detail</p>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Fields */}
        <div className="space-y-3">
          <DetailField label="Event ID" value={entry.id} mono />
          <DetailField label="Action" value={entry.action} />
          <DetailField label="Timestamp" value={new Date(entry.timestamp).toLocaleString()} />
          <DetailField label="Status" value={entry.status} badge={entry.status === 'success' ? 'emerald' : 'red'} />
          {entry.resource_type && <DetailField label="Resource Type" value={entry.resource_type} />}
          {entry.resource_id && <DetailField label="Resource ID" value={entry.resource_id} mono />}
          {entry.api_key_prefix && <DetailField label="API Key" value={`${entry.api_key_prefix}***`} mono />}
          {entry.ip_address && <DetailField label="IP Address" value={entry.ip_address} mono />}
          {entry.error_message && <DetailField label="Error" value={entry.error_message} />}

          {entry.pii_detected && (
            <div>
              <p className="text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-1">PII Detection</p>
              <div className="flex items-center gap-2">
                <span className="rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  PHI Detected
                </span>
                {entry.pii_types && (
                  <span className="text-xs text-slate-400">
                    {Object.entries(entry.pii_types).map(([k, v]) => `${k}: ${v}`).join(', ')}
                  </span>
                )}
              </div>
            </div>
          )}

          {entry.details && Object.keys(entry.details).length > 0 && (
            <div>
              <p className="text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-1.5">Additional Details</p>
              <div className="rounded-lg bg-slate-900/60 border border-slate-800 p-3">
                <pre className="text-xs text-slate-300 whitespace-pre-wrap break-all font-mono leading-relaxed">
                  {JSON.stringify(entry.details, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

function DetailField({ label, value, mono, badge }: {
  label: string; value: string; mono?: boolean; badge?: string;
}) {
  return (
    <div className="flex items-start justify-between py-1" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
      <p className="text-[10px] font-medium text-slate-500 uppercase tracking-wider">{label}</p>
      {badge ? (
        <span className={`rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border ${
          badge === 'emerald'
            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
            : 'bg-red-500/10 text-red-400 border-red-500/20'
        }`}>
          {value}
        </span>
      ) : (
        <p className={`text-sm text-slate-300 text-right max-w-[60%] break-all ${mono ? 'font-mono text-xs' : ''}`}>
          {value}
        </p>
      )}
    </div>
  );
}
