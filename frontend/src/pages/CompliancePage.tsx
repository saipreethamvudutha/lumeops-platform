import { useState, useEffect } from 'react';
import { Shield, Download, RefreshCw, CheckCircle, Lock, Eye, FileText } from 'lucide-react';
import { motion } from 'framer-motion';
import { fetchComplianceReport } from '../api/client';
import { ComplianceChecklist } from '../components/ComplianceChecklist';
import type { ComplianceReport } from '../types/api';

export function CompliancePage() {
  const [report, setReport] = useState<ComplianceReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadReport = async () => {
    setLoading(true);
    try {
      const data = await fetchComplianceReport();
      setReport(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load compliance report');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadReport(); }, []);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <RefreshCw className="h-8 w-8 animate-spin text-cyan-400" />
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center glass-card p-8">
          <p className="text-red-300">{error}</p>
          <button onClick={loadReport}
            className="mt-4 rounded-xl px-5 py-2.5 text-sm font-medium text-white"
            style={{ background: 'var(--gradient-brand)' }}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  const isCompliant = report.executive_summary.compliance_status === 'COMPLIANT';

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight">HIPAA Compliance</h1>
          <p className="mt-1 text-sm text-slate-500">
            Compliance evidence and audit-ready reports
          </p>
        </div>
        <button className="flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90"
          style={{ background: 'var(--gradient-brand)' }}>
          <Download className="h-4 w-4" />
          Export PDF
        </button>
      </div>

      {/* Compliance Status Banner */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="mb-8 glass-card-static p-6 relative overflow-hidden"
        style={{
          borderColor: isCompliant ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)',
        }}
      >
        <div className="absolute inset-0 pointer-events-none"
          style={{
            background: isCompliant
              ? 'radial-gradient(ellipse at top left, rgba(16, 185, 129, 0.08), transparent 60%)'
              : 'radial-gradient(ellipse at top left, rgba(239, 68, 68, 0.08), transparent 60%)',
          }} />
        <div className="relative flex items-center gap-4">
          <div className={`flex h-14 w-14 items-center justify-center rounded-2xl ${
            isCompliant ? 'bg-emerald-500/10' : 'bg-red-500/10'
          }`}>
            {isCompliant ? (
              <CheckCircle className="h-7 w-7 text-emerald-400" />
            ) : (
              <Shield className="h-7 w-7 text-red-400" />
            )}
          </div>
          <div>
            <h2 className={`text-xl font-bold ${isCompliant ? 'text-emerald-300' : 'text-red-300'}`}>
              {isCompliant ? 'HIPAA Compliant' : 'Compliance Issues Detected'}
            </h2>
            <p className="text-sm text-slate-500">
              Report generated {new Date(report.generated_at).toLocaleString()}
            </p>
          </div>
        </div>
      </motion.div>

      {/* Executive Summary Cards */}
      <div className="mb-8 grid grid-cols-1 gap-5 sm:grid-cols-3">
        <SummaryCard icon={FileText} label="Total Inferences"
          value={report.executive_summary.total_inferences.toLocaleString()}
          period={`${report.period.days}-day period`} delay={0.1} />
        <SummaryCard icon={Shield} label="PHI Redacted"
          value={report.executive_summary.pii_instances_redacted.toLocaleString()}
          period="Automatically protected" delay={0.15} />
        <SummaryCard icon={Eye} label="Audit Events"
          value={report.audit_logging.total_events.toLocaleString()}
          period={`Retained for ${report.audit_logging.retention}`} delay={0.2} />
      </div>

      {/* Protection Details */}
      <div className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.25 }} className="glass-card-static p-6">
          <div className="flex items-center gap-2 mb-5">
            <Lock className="h-4 w-4 text-cyan-400" />
            <h3 className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-400">
              Data Protection
            </h3>
          </div>
          <div className="space-y-4">
            <DetailRow label="Encryption at Rest"
              status={report.personal_information_safeguarding.encryption_at_rest.status}
              detail={report.personal_information_safeguarding.encryption_at_rest.method} />
            <DetailRow label="Encryption in Transit"
              status={report.personal_information_safeguarding.encryption_in_transit.status}
              detail={report.personal_information_safeguarding.encryption_in_transit.protocol} />
            <DetailRow label="PHI Redaction"
              status={report.personal_information_safeguarding.pii_redaction.status}
              detail={report.personal_information_safeguarding.pii_redaction.detection_method} />
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.3 }} className="glass-card-static p-6">
          <div className="flex items-center gap-2 mb-5">
            <Shield className="h-4 w-4 text-violet-400" />
            <h3 className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-400">
              Access & Audit Controls
            </h3>
          </div>
          <div className="space-y-4">
            <DetailRow label="Authentication"
              status={report.access_controls.status}
              detail={report.access_controls.authentication} />
            <DetailRow label="Rate Limiting"
              status={report.access_controls.rate_limiting === 'ENABLED' ? 'ACTIVE' : 'INACTIVE'}
              detail={`${report.access_controls.unique_keys_used} unique keys used`} />
            <DetailRow label="Audit Logging"
              status={report.audit_logging.status}
              detail={report.audit_logging.tamper_protection} />
          </div>
        </motion.div>
      </div>

      {/* Compliance Checklist */}
      <ComplianceChecklist items={report.compliance_checklist} />
    </div>
  );
}

function SummaryCard({ icon: Icon, label, value, period, delay }: {
  icon: typeof FileText; label: string; value: string; period: string; delay: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay }}
      className="glass-card p-5"
    >
      <div className="flex items-center gap-2 mb-3">
        <Icon className="h-4 w-4 text-cyan-400" />
        <p className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</p>
      </div>
      <p className="text-2xl font-bold text-slate-100">{value}</p>
      <p className="mt-1 text-[11px] text-slate-500">{period}</p>
    </motion.div>
  );
}

function DetailRow({ label, status, detail }: { label: string; status: string; detail: string }) {
  const isActive = status === 'ACTIVE' || status === 'ENABLED';
  return (
    <div className="flex items-start justify-between py-1">
      <div>
        <p className="text-sm font-medium text-slate-300">{label}</p>
        <p className="text-xs text-slate-500">{detail}</p>
      </div>
      <span className={`rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border ${
        isActive
          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
          : 'bg-red-500/10 text-red-400 border-red-500/20'
      }`}>
        {status}
      </span>
    </div>
  );
}
