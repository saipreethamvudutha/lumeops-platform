import { useState, useEffect } from 'react';
import { Shield, Download, RefreshCw, CheckCircle } from 'lucide-react';
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
        <RefreshCw className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <p className="text-red-600">{error}</p>
          <button onClick={loadReport} className="mt-3 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white">
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
          <h1 className="text-2xl font-bold text-slate-800">HIPAA Compliance</h1>
          <p className="mt-1 text-sm text-slate-500">
            Compliance evidence and audit-ready reports
          </p>
        </div>
        <button className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
          <Download className="h-4 w-4" />
          Export PDF
        </button>
      </div>

      {/* Compliance Status Banner */}
      <div
        className={`mb-8 rounded-xl border p-6 ${
          isCompliant ? 'border-emerald-200 bg-emerald-50' : 'border-red-200 bg-red-50'
        }`}
      >
        <div className="flex items-center gap-3">
          {isCompliant ? (
            <CheckCircle className="h-8 w-8 text-emerald-600" />
          ) : (
            <Shield className="h-8 w-8 text-red-600" />
          )}
          <div>
            <h2 className={`text-lg font-bold ${isCompliant ? 'text-emerald-800' : 'text-red-800'}`}>
              {isCompliant ? 'HIPAA Compliant' : 'Compliance Issues Detected'}
            </h2>
            <p className={`text-sm ${isCompliant ? 'text-emerald-600' : 'text-red-600'}`}>
              Report generated {new Date(report.generated_at).toLocaleString()}
            </p>
          </div>
        </div>
      </div>

      {/* Executive Summary Cards */}
      <div className="mb-8 grid grid-cols-1 gap-5 sm:grid-cols-3">
        <SummaryCard
          label="Total Inferences"
          value={report.executive_summary.total_inferences.toLocaleString()}
          period={`${report.period.days}-day period`}
        />
        <SummaryCard
          label="PHI Instances Redacted"
          value={report.executive_summary.pii_instances_redacted.toLocaleString()}
          period="Automatically protected"
        />
        <SummaryCard
          label="Audit Events"
          value={report.audit_logging.total_events.toLocaleString()}
          period={`Retained for ${report.audit_logging.retention}`}
        />
      </div>

      {/* Protection Details */}
      <div className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <h3 className="mb-4 text-sm font-semibold text-slate-500 uppercase tracking-wider">
            Data Protection
          </h3>
          <div className="space-y-4">
            <DetailRow
              label="Encryption at Rest"
              status={report.personal_information_safeguarding.encryption_at_rest.status}
              detail={report.personal_information_safeguarding.encryption_at_rest.method}
            />
            <DetailRow
              label="Encryption in Transit"
              status={report.personal_information_safeguarding.encryption_in_transit.status}
              detail={report.personal_information_safeguarding.encryption_in_transit.protocol}
            />
            <DetailRow
              label="PHI Redaction"
              status={report.personal_information_safeguarding.pii_redaction.status}
              detail={report.personal_information_safeguarding.pii_redaction.detection_method}
            />
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <h3 className="mb-4 text-sm font-semibold text-slate-500 uppercase tracking-wider">
            Access & Audit Controls
          </h3>
          <div className="space-y-4">
            <DetailRow
              label="Authentication"
              status={report.access_controls.status}
              detail={report.access_controls.authentication}
            />
            <DetailRow
              label="Rate Limiting"
              status={report.access_controls.rate_limiting === 'ENABLED' ? 'ACTIVE' : 'INACTIVE'}
              detail={`${report.access_controls.unique_keys_used} unique keys used`}
            />
            <DetailRow
              label="Audit Logging"
              status={report.audit_logging.status}
              detail={report.audit_logging.tamper_protection}
            />
          </div>
        </div>
      </div>

      {/* Compliance Checklist */}
      <ComplianceChecklist items={report.compliance_checklist} />
    </div>
  );
}

function SummaryCard({ label, value, period }: { label: string; value: string; period: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-800">{value}</p>
      <p className="mt-1 text-xs text-slate-400">{period}</p>
    </div>
  );
}

function DetailRow({ label, status, detail }: { label: string; status: string; detail: string }) {
  const isActive = status === 'ACTIVE' || status === 'ENABLED';
  return (
    <div className="flex items-start justify-between">
      <div>
        <p className="text-sm font-medium text-slate-700">{label}</p>
        <p className="text-xs text-slate-400">{detail}</p>
      </div>
      <span
        className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
          isActive ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
        }`}
      >
        {status}
      </span>
    </div>
  );
}
