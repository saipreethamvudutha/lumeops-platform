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

// ── Alert Management ─────────────────────────────────────────────

export interface AlertDetail {
  id: string;
  model_id: string;
  alert_type: string;
  severity: string;
  message: string;
  details: Record<string, unknown> | null;
  triggered_at: string;
  inference_id: string | null;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  resolved_at: string | null;
  notified_email: boolean;
  notified_slack: boolean;
  created_at: string;
}

export interface AlertListResponse {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  alerts: AlertDetail[];
}

export interface AlertStats {
  total_active: number;
  total_acknowledged: number;
  total_resolved: number;
  by_severity: Record<string, number>;
  by_type: Record<string, number>;
  mean_time_to_acknowledge_minutes: number | null;
  mean_time_to_resolve_minutes: number | null;
  generated_at: string;
}

export interface AlertBulkResult {
  processed: number;
  skipped: number;
  alert_ids: string[];
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

// ── Webhook Management ───────────────────────────────────────────

export interface WebhookInfo {
  id: string;
  name: string;
  url: string;
  description: string | null;
  events: string[];
  is_active: boolean;
  // Delivery tracking
  last_triggered_at: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_http_status: number | null;
  last_error: string | null;
  consecutive_failures: number;
  total_deliveries: number;
  total_failures: number;
  // Metadata
  created_at: string;
  updated_at: string;
}

export interface WebhookCreateResponse {
  id: string;
  name: string;
  url: string;
  events: string[];
  secret: string;
  is_active: boolean;
  created_at: string;
  warning: string;
}

export interface WebhookListResponse {
  total: number;
  webhooks: WebhookInfo[];
}

export interface WebhookTestResult {
  success: boolean;
  http_status: number | null;
  response_body: string | null;
  message: string;
}

export interface WebhookDelivery {
  id: string;
  event_type: string;
  event_id: string | null;
  http_status: number | null;
  response_time_ms: number | null;
  success: boolean;
  error: string | null;
  attempt_number: number;
  delivered_at: string;
}

export interface WebhookDeliveryListResponse {
  total: number;
  deliveries: WebhookDelivery[];
}

// ── Model Performance Tracking ──────────────────────────────────

export interface ModelOverview {
  id: string;
  model_name: string;
  model_version: string | null;
  framework: string | null;
  is_active: boolean;
  created_at: string | null;
  total_inferences: number;
  recent_inferences: number;
  recent_outliers: number;
  recent_quality_issues: number;
  outlier_rate: number;
  quality_rate: number;
  prediction_mean: number | null;
  avg_confidence: number | null;
  ground_truth_coverage: number;
  last_inference_at: string | null;
}

export interface ModelsOverviewResponse {
  total: number;
  days: number;
  models: ModelOverview[];
  generated_at: string;
}

export interface ModelPerformanceSummary {
  model: {
    id: string;
    model_name: string;
    model_version: string | null;
    description: string | null;
    framework: string | null;
    is_active: boolean;
    tags: Record<string, string> | null;
    created_at: string;
  };
  period: {
    days: number;
    start: string;
    end: string;
  };
  volume: {
    total: number;
    today: number;
    all_time: number;
    with_ground_truth: number;
    ground_truth_coverage: number;
  };
  predictions: {
    mean: number | null;
    std: number | null;
    min: number | null;
    max: number | null;
    p50: number | null;
    p95: number | null;
    p99: number | null;
  };
  accuracy: {
    mae: number | null;
    rmse: number | null;
    mean_error: number | null;
  };
  health: {
    outlier_count: number;
    outlier_rate: number;
    quality_issue_count: number;
    quality_rate: number;
    pii_inferences: number;
    total_pii_redacted: number;
  };
  confidence: {
    avg: number | null;
    min: number | null;
    max: number | null;
  };
  drift: {
    score: number | null;
    status: string;
    baseline_mean: number | null;
    baseline_std: number | null;
  };
  alerts: {
    total: number;
    by_severity: Record<string, number>;
  };
  generated_at: string;
}

export interface PerformanceTimeseriesPoint {
  timestamp: string;
  total_inferences: number;
  with_ground_truth: number;
  prediction_mean: number | null;
  prediction_std: number | null;
  prediction_min: number | null;
  prediction_max: number | null;
  outlier_count: number;
  outlier_rate: number;
  quality_issue_count: number;
  quality_rate: number;
  pii_inferences: number;
  total_pii_redacted: number;
  avg_confidence: number | null;
  mae: number | null;
  rmse: number | null;
}

export interface PerformanceTimeseriesResponse {
  model_id: string;
  days: number;
  granularity: string;
  series: PerformanceTimeseriesPoint[];
  generated_at: string;
}

export interface GroundTruthResult {
  inference_id: string;
  model_id: string;
  prediction: number;
  ground_truth: number;
  absolute_error: number;
  submitted_at: string;
}

export interface GroundTruthBatchResult {
  processed: number;
  skipped: number;
  total: number;
  errors: Array<{ inference_id: string; error: string }> | null;
}
