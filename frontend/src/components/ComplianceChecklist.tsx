import { CheckCircle, AlertTriangle, XCircle } from 'lucide-react';
import { motion } from 'framer-motion';
import type { ComplianceCheckItem } from '../types/api';

interface Props {
  items: ComplianceCheckItem[];
}

export function ComplianceChecklist({ items }: Props) {
  return (
    <div className="glass-card-static overflow-hidden">
      <div className="px-6 py-4" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <h3 className="text-sm font-semibold text-slate-200">HIPAA Compliance Checklist</h3>
        <p className="mt-0.5 text-xs text-slate-500">{items.length} requirements verified</p>
      </div>
      <div>
        {items.map((item, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.2, delay: i * 0.05 }}
            className="flex items-start gap-3 px-6 py-3.5 table-row-hover"
            style={{ borderBottom: '1px solid var(--border-subtle)' }}
          >
            <div className="mt-0.5 flex-shrink-0">
              {item.status === 'PASS' ? (
                <CheckCircle className="h-4.5 w-4.5 text-emerald-400" />
              ) : item.status === 'WARNING' ? (
                <AlertTriangle className="h-4.5 w-4.5 text-amber-400" />
              ) : (
                <XCircle className="h-4.5 w-4.5 text-red-400" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-200">{item.requirement}</p>
              <p className="mt-0.5 text-[11px] text-slate-500">{item.evidence}</p>
            </div>
            <span
              className={`flex-shrink-0 rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                item.status === 'PASS'
                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                  : item.status === 'WARNING'
                    ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                    : 'bg-red-500/10 text-red-400 border border-red-500/20'
              }`}
            >
              {item.status}
            </span>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
