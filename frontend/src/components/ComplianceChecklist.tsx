import { CheckCircle, AlertTriangle, XCircle } from 'lucide-react';
import type { ComplianceCheckItem } from '../types/api';

interface Props {
  items: ComplianceCheckItem[];
}

export function ComplianceChecklist({ items }: Props) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-5 py-4">
        <h3 className="font-semibold text-slate-800">HIPAA Compliance Checklist</h3>
      </div>
      <div className="divide-y divide-slate-100">
        {items.map((item, i) => (
          <div key={i} className="flex items-start gap-3 px-5 py-3.5">
            <div className="mt-0.5 flex-shrink-0">
              {item.status === 'PASS' ? (
                <CheckCircle className="h-5 w-5 text-emerald-500" />
              ) : item.status === 'WARNING' ? (
                <AlertTriangle className="h-5 w-5 text-amber-500" />
              ) : (
                <XCircle className="h-5 w-5 text-red-500" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-800">{item.requirement}</p>
              <p className="mt-0.5 text-xs text-slate-500">{item.evidence}</p>
            </div>
            <span
              className={`flex-shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                item.status === 'PASS'
                  ? 'bg-emerald-100 text-emerald-700'
                  : item.status === 'WARNING'
                    ? 'bg-amber-100 text-amber-700'
                    : 'bg-red-100 text-red-700'
              }`}
            >
              {item.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
