import { useState, useEffect, useCallback } from 'react';
import {
  Brain, RefreshCw, Activity, TrendingUp, TrendingDown, AlertTriangle,
  ChevronRight, Shield, Zap, BarChart3, Target, Clock, Database,
  ArrowLeft, Eye, Gauge,
} from 'lucide-react';
import { motion } from 'framer-motion';
import {
  fetchModelsOverview, fetchModelPerformance, fetchPerformanceTimeseries,
} from '../api/client';
import type {
  ModelOverview, ModelPerformanceSummary, PerformanceTimeseriesPoint,
} from '../types/api';
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip,
  BarChart, Bar, CartesianGrid, LineChart, Line,
} from 'recharts';

// ── Helper ──────────────────────────────────────────────────────

function fmt(val: number | null | undefined, digits = 2): string {
  if (val === null || val === undefined) return 'N/A';
  return val.toFixed(digits);
}

function pct(val: number | null | undefined): string {
  if (val === null || val === undefined) return 'N/A';
  return `${(val * 100).toFixed(1)}%`;
}

function timeAgo(iso: string | null): string {
  if (!iso) return 'Never';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ── Drift Status Badge ──────────────────────────────────────────

const DRIFT_CONFIG: Record<string, { color: string; bg: string; label: string }> = {
  stable: { color: 'text-emerald-400', bg: 'bg-emerald-500/20', label: 'Stable' },
  minor_drift: { color: 'text-amber-400', bg: 'bg-amber-500/20', label: 'Minor Drift' },
  moderate_drift: { color: 'text-orange-400', bg: 'bg-orange-500/20', label: 'Moderate Drift' },
  significant_drift: { color: 'text-red-400', bg: 'bg-red-500/20', label: 'Significant Drift' },
  no_data: { color: 'text-slate-500', bg: 'bg-slate-500/20', label: 'No Data' },
  no_baseline: { color: 'text-slate-500', bg: 'bg-slate-500/20', label: 'No Baseline' },
  constant_baseline: { color: 'text-cyan-400', bg: 'bg-cyan-500/20', label: 'Constant' },
};

function DriftBadge({ status }: { status: string }) {
  const cfg = DRIFT_CONFIG[status] || DRIFT_CONFIG.no_data;
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${cfg.bg} ${cfg.color}`}>
      {cfg.label}
    </span>
  );
}

// ── Stat Card ───────────────────────────────────────────────────

function MiniStat({ label, value, icon: Icon, color }: {
  label: string; value: string; icon: React.ComponentType<{ className?: string }>; color: string;
}) {
  return (
    <div className="glass-card-static p-4 flex items-center gap-3">
      <div className={`w-10 h-10 rounded-lg ${color} flex items-center justify-center`}>
        <Icon className="w-5 h-5 text-white" />
      </div>
      <div>
        <div className="text-xs text-slate-400">{label}</div>
        <div className="text-lg font-bold text-white">{value}</div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
//  MODELS PAGE — List + Detail Views
// ══════════════════════════════════════════════════════════════════

export function ModelsPage() {
  const [models, setModels] = useState<ModelOverview[]>([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(7);

  // Detail view state
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [perf, setPerf] = useState<ModelPerformanceSummary | null>(null);
  const [series, setSeries] = useState<PerformanceTimeseriesPoint[]>([]);
  const [_detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await fetchModelsOverview(days);
      setModels(resp.models);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { load(); }, [load]);

  const selectModel = useCallback(async (id: string) => {
    setSelectedId(id);
    setDetailLoading(true);
    try {
      const [perfData, tsData] = await Promise.all([
        fetchModelPerformance(id, days),
        fetchPerformanceTimeseries(id, { days, granularity: days <= 2 ? 'hourly' : 'daily' }),
      ]);
      setPerf(perfData);
      setSeries(tsData.series);
    } catch {
      /* ignore */
    } finally {
      setDetailLoading(false);
    }
  }, [days]);

  const goBack = () => { setSelectedId(null); setPerf(null); setSeries([]); };

  // ── Detail View ─────────────────────────────────────────────
  if (selectedId && perf) {
    return <ModelDetailView perf={perf} series={series} onBack={goBack} />;
  }

  // ── List View ───────────────────────────────────────────────
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Brain className="w-7 h-7 text-violet-400" />
            Model Performance
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Track prediction accuracy, drift, and health across all monitored models
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="glass-card-static px-3 py-2 text-sm text-slate-300 bg-transparent border-0 focus:ring-1 focus:ring-cyan-500/50 rounded-lg"
          >
            <option value={1}>Last 24h</option>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <button
            onClick={load}
            className="glass-card-static px-3 py-2 text-sm text-cyan-400 hover:text-cyan-300 rounded-lg flex items-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Models Grid */}
      {loading ? (
        <div className="glass-card p-12 text-center">
          <RefreshCw className="w-8 h-8 text-cyan-400 animate-spin mx-auto mb-3" />
          <p className="text-slate-400">Loading models...</p>
        </div>
      ) : models.length === 0 ? (
        <div className="glass-card p-12 text-center">
          <Brain className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400">No models registered yet</p>
          <p className="text-xs text-slate-500 mt-1">
            Register models via POST /api/v1/models and send inferences
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {models.map((m, i) => (
            <motion.div
              key={m.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              onClick={() => selectModel(m.id)}
              className="glass-card p-5 cursor-pointer hover:border-cyan-500/30 transition-colors group"
            >
              {/* Model Header */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="text-white font-semibold truncate">{m.model_name}</h3>
                    <span className={`w-2 h-2 rounded-full ${m.is_active ? 'bg-emerald-400' : 'bg-slate-600'}`} />
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    {m.model_version && (
                      <span className="text-xs text-slate-500">v{m.model_version}</span>
                    )}
                    {m.framework && (
                      <span className="text-xs text-cyan-500/60 bg-cyan-500/10 px-1.5 py-0.5 rounded">
                        {m.framework}
                      </span>
                    )}
                  </div>
                </div>
                <ChevronRight className="w-5 h-5 text-slate-600 group-hover:text-cyan-400 transition-colors" />
              </div>

              {/* Quick Stats */}
              <div className="grid grid-cols-3 gap-3 mb-3">
                <div>
                  <div className="text-xs text-slate-500">Inferences</div>
                  <div className="text-sm font-mono text-white">
                    {m.recent_inferences.toLocaleString()}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-slate-500">Quality</div>
                  <div className={`text-sm font-mono ${m.quality_rate >= 0.95 ? 'text-emerald-400' : m.quality_rate >= 0.8 ? 'text-amber-400' : 'text-red-400'}`}>
                    {pct(m.quality_rate)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-slate-500">Outliers</div>
                  <div className={`text-sm font-mono ${m.outlier_rate < 0.05 ? 'text-emerald-400' : m.outlier_rate < 0.15 ? 'text-amber-400' : 'text-red-400'}`}>
                    {pct(m.outlier_rate)}
                  </div>
                </div>
              </div>

              {/* Footer */}
              <div className="flex items-center justify-between text-xs text-slate-500 pt-3 border-t border-white/5">
                <span>
                  <Database className="w-3 h-3 inline mr-1" />
                  {m.total_inferences.toLocaleString()} total
                </span>
                <span>
                  <Clock className="w-3 h-3 inline mr-1" />
                  {timeAgo(m.last_inference_at)}
                </span>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </motion.div>
  );
}

// ══════════════════════════════════════════════════════════════════
//  MODEL DETAIL VIEW
// ══════════════════════════════════════════════════════════════════

function ModelDetailView({ perf, series, onBack }: {
  perf: ModelPerformanceSummary;
  series: PerformanceTimeseriesPoint[];
  onBack: () => void;
}) {
  const m = perf.model;
  const v = perf.volume;
  const p = perf.predictions;
  const h = perf.health;
  const a = perf.accuracy;
  const d = perf.drift;
  const c = perf.confidence;

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={onBack}
            className="glass-card-static p-2 text-slate-400 hover:text-cyan-400 rounded-lg"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-3">
              {m.model_name}
              <span className={`w-2.5 h-2.5 rounded-full ${m.is_active ? 'bg-emerald-400' : 'bg-slate-600'}`} />
            </h1>
            <div className="flex items-center gap-3 text-sm text-slate-400 mt-1">
              {m.model_version && <span>v{m.model_version}</span>}
              {m.framework && <span className="text-cyan-400/70">{m.framework}</span>}
              {m.description && <span>{m.description}</span>}
            </div>
          </div>
        </div>
        <DriftBadge status={d.status} />
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <MiniStat label="Period Volume" value={v.total.toLocaleString()} icon={BarChart3} color="bg-cyan-600" />
        <MiniStat label="Today" value={v.today.toLocaleString()} icon={Zap} color="bg-violet-600" />
        <MiniStat label="Quality Rate" value={pct(h.quality_rate)} icon={Shield} color={h.quality_rate >= 0.95 ? 'bg-emerald-600' : 'bg-amber-600'} />
        <MiniStat label="Outlier Rate" value={pct(h.outlier_rate)} icon={AlertTriangle} color={h.outlier_rate < 0.05 ? 'bg-emerald-600' : 'bg-red-600'} />
        <MiniStat label="Drift Score" value={d.score !== null ? fmt(d.score) : 'N/A'} icon={TrendingUp} color={d.score !== null && d.score < 1 ? 'bg-emerald-600' : 'bg-orange-600'} />
        <MiniStat label="Avg Confidence" value={c.avg !== null ? pct(c.avg) : 'N/A'} icon={Gauge} color="bg-blue-600" />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Inference Volume Chart */}
        <div className="glass-card-static p-5">
          <h3 className="text-sm text-slate-300 font-semibold mb-4 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-cyan-400" />
            Inference Volume
          </h3>
          {series.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={series}>
                <defs>
                  <linearGradient id="volGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis
                  dataKey="timestamp"
                  tickFormatter={(t) => new Date(t).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  stroke="transparent"
                />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} stroke="transparent" />
                <Tooltip
                  contentStyle={{ background: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                  labelFormatter={(t) => new Date(t as string).toLocaleString()}
                />
                <Area type="monotone" dataKey="total_inferences" name="Inferences" stroke="#06b6d4" fill="url(#volGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[220px] flex items-center justify-center text-slate-500">
              No data for this period
            </div>
          )}
        </div>

        {/* Prediction Distribution Chart */}
        <div className="glass-card-static p-5">
          <h3 className="text-sm text-slate-300 font-semibold mb-4 flex items-center gap-2">
            <Activity className="w-4 h-4 text-violet-400" />
            Prediction Mean Trend
          </h3>
          {series.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={series}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis
                  dataKey="timestamp"
                  tickFormatter={(t) => new Date(t).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  stroke="transparent"
                />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} stroke="transparent" />
                <Tooltip
                  contentStyle={{ background: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                  labelFormatter={(t) => new Date(t as string).toLocaleString()}
                />
                <Line type="monotone" dataKey="prediction_mean" name="Mean" stroke="#8b5cf6" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="prediction_min" name="Min" stroke="#475569" strokeWidth={1} dot={false} strokeDasharray="4 2" />
                <Line type="monotone" dataKey="prediction_max" name="Max" stroke="#475569" strokeWidth={1} dot={false} strokeDasharray="4 2" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[220px] flex items-center justify-center text-slate-500">
              No data for this period
            </div>
          )}
        </div>
      </div>

      {/* Health & Accuracy Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Health Metrics Chart */}
        <div className="glass-card-static p-5">
          <h3 className="text-sm text-slate-300 font-semibold mb-4 flex items-center gap-2">
            <Shield className="w-4 h-4 text-emerald-400" />
            Data Quality Trend
          </h3>
          {series.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={series}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis
                  dataKey="timestamp"
                  tickFormatter={(t) => new Date(t).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  stroke="transparent"
                />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} stroke="transparent" domain={[0, 1]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                <Tooltip
                  contentStyle={{ background: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                  labelFormatter={(t) => new Date(t as string).toLocaleString()}
                  formatter={(val: number | undefined) => [`${((val ?? 0) * 100).toFixed(1)}%`, 'Quality Rate']}
                />
                <Bar dataKey="quality_rate" name="Quality" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[220px] flex items-center justify-center text-slate-500">
              No data for this period
            </div>
          )}
        </div>

        {/* Outlier Rate Chart */}
        <div className="glass-card-static p-5">
          <h3 className="text-sm text-slate-300 font-semibold mb-4 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            Outlier Rate Trend
          </h3>
          {series.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={series}>
                <defs>
                  <linearGradient id="outlierGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis
                  dataKey="timestamp"
                  tickFormatter={(t) => new Date(t).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  stroke="transparent"
                />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} stroke="transparent" tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                <Tooltip
                  contentStyle={{ background: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                  labelFormatter={(t) => new Date(t as string).toLocaleString()}
                  formatter={(val: number | undefined) => [`${((val ?? 0) * 100).toFixed(1)}%`, 'Outlier Rate']}
                />
                <Area type="monotone" dataKey="outlier_rate" name="Outlier Rate" stroke="#f59e0b" fill="url(#outlierGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[220px] flex items-center justify-center text-slate-500">
              No data for this period
            </div>
          )}
        </div>
      </div>

      {/* Detailed Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Prediction Distribution */}
        <div className="glass-card-static p-5">
          <h3 className="text-sm text-slate-300 font-semibold mb-3 flex items-center gap-2">
            <Target className="w-4 h-4 text-cyan-400" />
            Prediction Distribution
          </h3>
          <div className="space-y-2 text-sm">
            <MetricRow label="Mean" value={fmt(p.mean, 4)} />
            <MetricRow label="Std Dev" value={fmt(p.std, 4)} />
            <MetricRow label="Median (P50)" value={fmt(p.p50, 4)} />
            <MetricRow label="P95" value={fmt(p.p95, 4)} />
            <MetricRow label="P99" value={fmt(p.p99, 4)} />
            <MetricRow label="Min" value={fmt(p.min, 4)} />
            <MetricRow label="Max" value={fmt(p.max, 4)} />
          </div>
        </div>

        {/* Accuracy Metrics */}
        <div className="glass-card-static p-5">
          <h3 className="text-sm text-slate-300 font-semibold mb-3 flex items-center gap-2">
            <Eye className="w-4 h-4 text-violet-400" />
            Accuracy Metrics
          </h3>
          {v.with_ground_truth > 0 ? (
            <div className="space-y-2 text-sm">
              <MetricRow label="MAE" value={fmt(a.mae, 4)} />
              <MetricRow label="RMSE" value={fmt(a.rmse, 4)} />
              <MetricRow label="Mean Error (Bias)" value={fmt(a.mean_error, 4)} />
              <div className="mt-3 pt-3 border-t border-white/5">
                <MetricRow label="Ground Truth Coverage" value={pct(v.ground_truth_coverage)} />
                <MetricRow label="Samples with GT" value={v.with_ground_truth.toLocaleString()} />
              </div>
            </div>
          ) : (
            <div className="text-center py-4">
              <TrendingDown className="w-8 h-8 text-slate-600 mx-auto mb-2" />
              <p className="text-sm text-slate-500">No ground truth submitted</p>
              <p className="text-xs text-slate-600 mt-1">
                POST /models/{'{id}'}/ground-truth/{'{inf_id}'}
              </p>
            </div>
          )}
        </div>

        {/* Drift & Baseline */}
        <div className="glass-card-static p-5">
          <h3 className="text-sm text-slate-300 font-semibold mb-3 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-orange-400" />
            Drift Detection
          </h3>
          <div className="space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Status</span>
              <DriftBadge status={d.status} />
            </div>
            <MetricRow label="Drift Score" value={d.score !== null ? fmt(d.score) : 'N/A'} />
            <MetricRow label="Baseline Mean" value={d.baseline_mean !== null ? fmt(d.baseline_mean, 4) : 'N/A'} />
            <MetricRow label="Baseline Std" value={d.baseline_std !== null ? fmt(d.baseline_std, 4) : 'N/A'} />
            <div className="mt-3 pt-3 border-t border-white/5 text-xs text-slate-500">
              <p>{'< 0.5: Stable'}</p>
              <p>0.5-1.0: Minor drift</p>
              <p>1.0-2.0: Moderate drift</p>
              <p>{'> 2.0: Significant drift'}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Health Summary */}
      <div className="glass-card-static p-5">
        <h3 className="text-sm text-slate-300 font-semibold mb-4 flex items-center gap-2">
          <Shield className="w-4 h-4 text-emerald-400" />
          Health Summary ({perf.period.days}-Day Window)
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 text-sm">
          <div>
            <div className="text-xs text-slate-500">Total Inferences</div>
            <div className="text-lg font-mono text-white">{v.total.toLocaleString()}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Outliers</div>
            <div className="text-lg font-mono text-amber-400">{h.outlier_count}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Quality Issues</div>
            <div className="text-lg font-mono text-red-400">{h.quality_issue_count}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">PII Inferences</div>
            <div className="text-lg font-mono text-violet-400">{h.pii_inferences}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">PII Redacted</div>
            <div className="text-lg font-mono text-violet-400">{h.total_pii_redacted}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Alerts Triggered</div>
            <div className="text-lg font-mono text-orange-400">{perf.alerts.total}</div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

// ── Metric Row Component ────────────────────────────────────────

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-400">{label}</span>
      <span className="font-mono text-white">{value}</span>
    </div>
  );
}
