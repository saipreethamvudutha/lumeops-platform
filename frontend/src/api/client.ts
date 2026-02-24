import axios from 'axios';
import type {
  DashboardStats,
  ComplianceReport,
  ApiKeyInfo,
  HealthStatus,
  TimeSeriesResponse,
  QualityTrendResponse,
  InferenceListResponse,
  WebhookInfo,
  WebhookCreateResponse,
  WebhookListResponse,
  WebhookTestResult,
  WebhookDeliveryListResponse,
} from '../types/api';

const api = axios.create({
  baseURL: '',
  headers: { 'Content-Type': 'application/json' },
});

// Inject API key from localStorage
api.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem('lumeops_api_key');
  if (apiKey) {
    config.headers.Authorization = `Bearer ${apiKey}`;
  }
  return config;
});

export async function fetchDashboardStats(): Promise<DashboardStats> {
  const { data } = await api.get<DashboardStats>('/api/v1/dashboard/stats');
  return data;
}

export async function fetchComplianceReport(): Promise<ComplianceReport> {
  const { data } = await api.get<ComplianceReport>('/api/v1/reports/hipaa');
  return data;
}

export async function fetchApiKeys(): Promise<ApiKeyInfo[]> {
  const { data } = await api.get<{ keys: ApiKeyInfo[] }>('/api/v1/apikeys');
  return data.keys;
}

export async function fetchHealth(): Promise<HealthStatus> {
  const { data } = await api.get<HealthStatus>('/ready');
  return data;
}

export async function fetchTimeSeries(period: '24h' | '7d' | '30d' = '24h'): Promise<TimeSeriesResponse> {
  const { data } = await api.get<TimeSeriesResponse>(`/api/v1/dashboard/timeseries?period=${period}`);
  return data;
}

export async function fetchQualityTrend(days: number = 7): Promise<QualityTrendResponse> {
  const { data } = await api.get<QualityTrendResponse>(`/api/v1/dashboard/quality-trend?days=${days}`);
  return data;
}

export async function fetchInferences(params: {
  days?: number;
  has_pii?: boolean;
  is_outlier?: boolean;
  limit?: number;
  offset?: number;
} = {}): Promise<InferenceListResponse> {
  const searchParams = new URLSearchParams();
  if (params.days) searchParams.set('days', String(params.days));
  if (params.has_pii !== undefined) searchParams.set('has_pii', String(params.has_pii));
  if (params.is_outlier !== undefined) searchParams.set('is_outlier', String(params.is_outlier));
  if (params.limit) searchParams.set('limit', String(params.limit));
  if (params.offset) searchParams.set('offset', String(params.offset));
  const qs = searchParams.toString();
  const { data } = await api.get<InferenceListResponse>(`/api/v1/inferences${qs ? `?${qs}` : ''}`);
  return data;
}

// ── Webhook Endpoints ────────────────────────────────────────────

export async function fetchWebhooks(): Promise<WebhookInfo[]> {
  const { data } = await api.get<WebhookListResponse>('/api/v1/webhooks');
  return data.webhooks;
}

export async function createWebhook(payload: {
  name: string;
  url: string;
  events: string[];
  description?: string;
  headers?: Record<string, string>;
}): Promise<WebhookCreateResponse> {
  const { data } = await api.post<WebhookCreateResponse>('/api/v1/webhooks', payload);
  return data;
}

export async function updateWebhook(
  id: string,
  payload: {
    name?: string;
    url?: string;
    events?: string[];
    description?: string;
    headers?: Record<string, string>;
    is_active?: boolean;
  },
): Promise<WebhookInfo> {
  const { data } = await api.patch<WebhookInfo>(`/api/v1/webhooks/${id}`, payload);
  return data;
}

export async function deleteWebhook(id: string): Promise<void> {
  await api.delete(`/api/v1/webhooks/${id}`);
}

export async function testWebhook(id: string): Promise<WebhookTestResult> {
  const { data } = await api.post<WebhookTestResult>(`/api/v1/webhooks/${id}/test`);
  return data;
}

export async function fetchWebhookDeliveries(
  id: string,
  params: { limit?: number; offset?: number } = {},
): Promise<WebhookDeliveryListResponse> {
  const searchParams = new URLSearchParams();
  if (params.limit) searchParams.set('limit', String(params.limit));
  if (params.offset) searchParams.set('offset', String(params.offset));
  const qs = searchParams.toString();
  const { data } = await api.get<WebhookDeliveryListResponse>(
    `/api/v1/webhooks/${id}/deliveries${qs ? `?${qs}` : ''}`,
  );
  return data;
}

// ── API Key Storage ──────────────────────────────────────────────

export function setApiKey(key: string) {
  localStorage.setItem('lumeops_api_key', key);
}

export function getApiKey(): string | null {
  return localStorage.getItem('lumeops_api_key');
}

export function clearApiKey() {
  localStorage.removeItem('lumeops_api_key');
}
