export interface DashboardStats {
  inferences: {
    today: number;
    this_week: number;
    this_month: number;
    all_time: number;
  };
  data_quality: {
    quality_rate: number;
    issues_today: number;
  };
  predictions: {
    outliers_today: number;
  };
  pii_protection: {
    total_redacted_today: number;
  };
  alerts: {
    active: number;
    recent: Alert[];
  };
  system: {
    status: string;
    version: string;
  };
  generated_at: string;
}

export interface Alert {
  id: string;
  alert_type: string;
  severity: string;
  message: string;
  triggered_at: string;
  acknowledged_at: string | null;
}

export interface ComplianceReport {
  report_id: string;
  generated_at: string;
  period: {
    start: string;
    end: string;
    days: number;
  };
  executive_summary: {
    total_inferences: number;
    pii_instances_redacted: number;
    compliance_status: string;
  };
  personal_information_safeguarding: {
    encryption_at_rest: { status: string; method: string };
    encryption_in_transit: { status: string; protocol: string };
    pii_redaction: {
      status: string;
      instances_redacted: number;
      detection_method: string;
    };
  };
  access_controls: {
    status: string;
    authentication: string;
    unique_keys_used: number;
    rate_limiting: string;
  };
  audit_logging: {
    status: string;
    total_events: number;
    retention: string;
    tamper_protection: string;
  };
  compliance_checklist: ComplianceCheckItem[];
}

export interface ComplianceCheckItem {
  requirement: string;
  status: string;
  evidence: string;
}

export interface ApiKeyInfo {
  id: string;
  name: string;
  key_prefix: string;
  key_suffix: string;
  created_at: string;
  last_used_at: string | null;
  expires_at: string;
  is_active: boolean;
  scopes: string[];
}

export interface HealthStatus {
  status: string;
  version: string;
  timestamp: string;
  services: {
    database: string;
    redis: string;
  } | null;
}

// ── Time-Series Data ──────────────────────────────────────────────

export interface TimeSeriesPoint {
  label: string;
  timestamp: string;
  inferences: number;
  pii_redacted: number;
  outliers: number;
  quality_issues: number;
}

export interface TimeSeriesResponse {
  period: string;
  granularity: string;
  total_inferences: number;
  total_pii_redacted: number;
  total_outliers: number;
  series: TimeSeriesPoint[];
  generated_at: string;
}

export interface QualityTrendPoint {
  label: string;
  timestamp: string;
  total: number;
  issues: number;
  quality: number;
}

export interface QualityTrendResponse {
  days: number;
  series: QualityTrendPoint[];
  generated_at: string;
}

// ── Inference Log Viewer ──────────────────────────────────────────

export interface InferenceRecord {
  id: string;
  model_id: string;
  prediction: number;
  confidence: number | null;
  pii_detected: boolean;
  pii_redaction_count: number;
  pii_types_found: Record<string, number> | null;
  max_sensitivity_level: string | null;
  sensitivity_counts: Record<string, number> | null;
  contains_clinical_data: boolean;
  contains_behavioral_health: boolean;
  contains_genetic_data: boolean;
  has_quality_issues: boolean;
  is_outlier: boolean;
  outlier_reason: string | null;
  encryption_key_version: number;
  received_at: string;
  request_id: string | null;
  source_ip: string | null;
}

export interface InferenceListResponse {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  inferences: InferenceRecord[];
}
