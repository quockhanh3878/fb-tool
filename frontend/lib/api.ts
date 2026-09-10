/**
 * Client gọi API backend.
 *
 * Access token sống 15 phút nên mọi request 401 đều được thử làm mới bằng
 * refresh token đúng MỘT lần trước khi đá người dùng ra trang đăng nhập —
 * tránh cảnh đang thao tác nửa chừng thì bị văng.
 */
import type {
  Bump,
  Campaign,
  CheckAllResult,
  Clone,
  CloneDiagnosis,
  CloneHealth,
  CommentAction,
  CookieUploadResult,
  DashboardStats,
  ExpandResult,
  Group,
  GroupPerformance,
  HealthEvent,
  HealthSummary,
  IngestResult,
  LintReport,
  PaymentIntent,
  PlanSpec,
  Post,
  PostList,
  PostPublish,
  PostPublishList,
  Proxy,
  Script,
  ScriptPreview,
  Subscription,
  TokenPair,
  Usage,
  User,
} from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") || "http://localhost:8000";

const ACCESS_KEY = "ch_access_token";
const REFRESH_KEY = "ch_refresh_token";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const tokens = {
  access: () => (typeof window === "undefined" ? null : localStorage.getItem(ACCESS_KEY)),
  refresh: () => (typeof window === "undefined" ? null : localStorage.getItem(REFRESH_KEY)),
  save(pair: TokenPair) {
    localStorage.setItem(ACCESS_KEY, pair.access_token);
    localStorage.setItem(REFRESH_KEY, pair.refresh_token);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

/** Rút thông báo lỗi tiếng Việt từ body FastAPI (detail có thể là chuỗi hoặc mảng). */
async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => (typeof item === "string" ? item : (item?.msg ?? JSON.stringify(item))))
        .join("; ");
    }
    return JSON.stringify(body);
  } catch {
    return `Lỗi ${response.status}`;
  }
}

let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  // Nhiều request 401 cùng lúc chỉ được phép gọi /refresh một lần.
  if (refreshing) return refreshing;
  const token = tokens.refresh();
  if (!token) return false;

  refreshing = (async () => {
    try {
      const response = await fetch(`${API_URL}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: token }),
      });
      if (!response.ok) return false;
      tokens.save((await response.json()) as TokenPair);
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  form?: FormData;
  auth?: boolean;
  retry?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, form, auth = true, retry = true } = options;
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = tokens.access();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
  });

  if (response.status === 401 && auth && retry && (await tryRefresh())) {
    return request<T>(path, { ...options, retry: false });
  }
  if (response.status === 401 && auth && typeof window !== "undefined") {
    tokens.clear();
    if (!window.location.pathname.startsWith("/login")) window.location.href = "/login";
  }
  if (!response.ok) throw new ApiError(response.status, await readError(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const qs = (params: Record<string, string | number | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
};

export const api = {
  // ── Auth ───────────────────────────────────────────────────────────────
  register: (email: string, password: string, display_name = "") =>
    request<TokenPair>("/api/auth/register", {
      method: "POST",
      body: { email, password, display_name },
      auth: false,
    }),
  login: (email: string, password: string) =>
    request<TokenPair>("/api/auth/login", {
      method: "POST",
      body: { email, password },
      auth: false,
    }),
  me: () => request<User>("/api/auth/me"),
  updateMe: (payload: { display_name?: string; telegram_chat_id?: string }) =>
    request<User>("/api/auth/me", { method: "PUT", body: payload }),
  connectTelegram: () =>
    request<{ link_code: string; instructions: string }>("/api/auth/connect-telegram", {
      method: "POST",
    }),

  // ── Chiến dịch ─────────────────────────────────────────────────────────
  campaigns: () => request<Campaign[]>("/api/campaigns"),
  campaign: (id: string) => request<Campaign>(`/api/campaigns/${id}`),
  createCampaign: (payload: Partial<Campaign>) =>
    request<Campaign>("/api/campaigns", { method: "POST", body: payload }),
  updateCampaign: (id: string, payload: Partial<Campaign>) =>
    request<Campaign>(`/api/campaigns/${id}`, { method: "PUT", body: payload }),
  deleteCampaign: (id: string) => request<void>(`/api/campaigns/${id}`, { method: "DELETE" }),
  activateCampaign: (id: string) =>
    request<Campaign>(`/api/campaigns/${id}/activate`, { method: "POST" }),
  pauseCampaign: (id: string) =>
    request<Campaign>(`/api/campaigns/${id}/pause`, { method: "POST" }),

  // ── Group ──────────────────────────────────────────────────────────────
  groups: (campaignId: string) => request<Group[]>(`/api/campaigns/${campaignId}/groups`),
  addGroup: (
    campaignId: string,
    payload: { group_url: string; group_name?: string; scan_interval_minutes?: number },
  ) => request<Group>(`/api/campaigns/${campaignId}/groups`, { method: "POST", body: payload }),
  updateGroup: (campaignId: string, groupId: string, payload: Partial<Group>) =>
    request<Group>(`/api/campaigns/${campaignId}/groups/${groupId}`, {
      method: "PUT",
      body: payload,
    }),
  deleteGroup: (campaignId: string, groupId: string) =>
    request<void>(`/api/campaigns/${campaignId}/groups/${groupId}`, { method: "DELETE" }),

  // ── Kịch bản ───────────────────────────────────────────────────────────
  scripts: (campaignId: string) => request<Script[]>(`/api/campaigns/${campaignId}/scripts`),
  createScript: (campaignId: string, payload: Partial<Script>) =>
    request<Script>(`/api/campaigns/${campaignId}/scripts`, { method: "POST", body: payload }),
  updateScript: (campaignId: string, scriptId: string, payload: Partial<Script>) =>
    request<Script>(`/api/campaigns/${campaignId}/scripts/${scriptId}`, {
      method: "PUT",
      body: payload,
    }),
  deleteScript: (campaignId: string, scriptId: string) =>
    request<void>(`/api/campaigns/${campaignId}/scripts/${scriptId}`, { method: "DELETE" }),
  previewScript: (campaignId: string, scriptId: string, count = 5) =>
    request<ScriptPreview>(
      `/api/campaigns/${campaignId}/scripts/${scriptId}/preview?count=${count}`,
      { method: "POST" },
    ),
  /** Soi mẫu CHƯA lưu — dùng cho ô soạn thảo trực tiếp. */
  lintDraft: (campaignId: string, template_content: string, sample_count = 5) =>
    request<LintReport>(`/api/campaigns/${campaignId}/scripts/lint`, {
      method: "POST",
      body: { template_content, sample_count },
    }),
  lintScript: (campaignId: string, scriptId: string) =>
    request<LintReport>(`/api/campaigns/${campaignId}/scripts/${scriptId}/lint`, {
      method: "POST",
    }),
  expandScript: (campaignId: string, scriptId: string) =>
    request<ExpandResult>(`/api/campaigns/${campaignId}/scripts/${scriptId}/expand`, {
      method: "POST",
    }),

  // ── Clone ──────────────────────────────────────────────────────────────
  clones: () => request<Clone[]>("/api/clones"),
  clone: (id: string) => request<Clone>(`/api/clones/${id}`),
  createClone: (payload: Partial<Clone>) =>
    request<Clone>("/api/clones", { method: "POST", body: payload }),
  updateClone: (id: string, payload: Partial<Clone>) =>
    request<Clone>(`/api/clones/${id}`, { method: "PUT", body: payload }),
  deleteClone: (id: string) => request<void>(`/api/clones/${id}`, { method: "DELETE" }),
  cloneHealth: (id: string) => request<CloneHealth>(`/api/clones/${id}/health`),
  /** Kiểm tra + tự hạ trạng thái nếu cookie hỏng. Trả về phiếu chẩn đoán. */
  checkSession: (id: string) =>
    request<CloneDiagnosis>(`/api/clones/${id}/check-session`, { method: "POST" }),
  /** Chỉ đọc — không đổi trạng thái clone. */
  diagnoseClone: (id: string) => request<CloneDiagnosis>(`/api/clones/${id}/diagnose`),
  checkAllClones: () => request<CheckAllResult>("/api/clones/check-all", { method: "POST" }),
  transitionClone: (id: string, event: string, details = "") =>
    request<Clone>(`/api/clones/${id}/transition`, { method: "POST", body: { event, details } }),
  uploadCookie: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<CookieUploadResult>(`/api/clones/${id}/upload-cookie`, {
      method: "POST",
      form,
    });
  },

  // ── Bài viết ───────────────────────────────────────────────────────────
  posts: (
    params: { campaign_id?: string; status?: string; limit?: number; offset?: number } = {},
  ) => request<PostList>(`/api/posts${qs(params)}`),
  post: (id: string) => request<Post>(`/api/posts/${id}`),
  postActions: (id: string) => request<CommentAction[]>(`/api/posts/${id}/actions`),
  applyPost: (id: string, payload: { comment_text?: string; clone_id?: string }) =>
    request<CommentAction>(`/api/posts/${id}/apply`, { method: "POST", body: payload }),
  skipPost: (id: string) => request<Post>(`/api/posts/${id}/skip`, { method: "POST" }),
  ingest: (campaignId: string, groupId: string, posts: unknown[]) =>
    request<IngestResult>(`/api/campaigns/${campaignId}/ingest`, {
      method: "POST",
      body: { group_id: groupId, posts },
    }),

  // ── Đăng bài (Publishing / Seeding) ──────────────────────────────────
  publishingPosts: (
    params: { campaign_id?: string; status?: string; limit?: number; offset?: number } = {},
  ) => request<PostPublishList>(`/api/publishing${qs(params)}`),
  publishingPost: (id: string) => request<PostPublish>(`/api/publishing/${id}`),
  createPublishingPost: (payload: {
    campaign_id?: string | null;
    clone_account_id?: string | null;
    title: string;
    content_template: string;
    media_urls?: string[];
    target_groups: Array<{ group_id: string; group_name: string; group_url?: string }>;
    scheduled_at?: string | null;
  }) => request<PostPublish>("/api/publishing", { method: "POST", body: payload }),
  publishPostNow: (id: string) =>
    request<PostPublish>(`/api/publishing/${id}/publish-now`, { method: "POST" }),
  deletePublishingPost: (id: string) =>
    request<void>(`/api/publishing/${id}`, { method: "DELETE" }),

  // ── Hàng đợi ───────────────────────────────────────────────────────────
  queue: () => request<CommentAction[]>("/api/queue"),
  cancelQueued: (actionId: string) =>
    request<CommentAction>(`/api/queue/${actionId}/cancel`, { method: "POST" }),

  // ── Bump ───────────────────────────────────────────────────────────────
  bumps: (campaignId: string) => request<Bump[]>(`/api/campaigns/${campaignId}/bumps`),
  createBump: (campaignId: string, payload: Partial<Bump>) =>
    request<Bump>(`/api/campaigns/${campaignId}/bumps`, { method: "POST", body: payload }),
  updateBump: (campaignId: string, bumpId: string, payload: Partial<Bump>) =>
    request<Bump>(`/api/campaigns/${campaignId}/bumps/${bumpId}`, { method: "PUT", body: payload }),
  deleteBump: (campaignId: string, bumpId: string) =>
    request<void>(`/api/campaigns/${campaignId}/bumps/${bumpId}`, { method: "DELETE" }),

  // ── Thống kê ───────────────────────────────────────────────────────────
  dashboard: (days = 7) => request<DashboardStats>(`/api/stats/dashboard?days=${days}`),
  groupPerformance: () => request<GroupPerformance[]>("/api/stats/groups"),
  statusBreakdown: () => request<Record<string, number>>("/api/stats/status-breakdown"),

  // ── Sức khỏe & proxy ───────────────────────────────────────────────────
  healthOverview: () => request<CloneHealth[]>("/api/health/overview"),
  healthSummary: () => request<HealthSummary>("/api/health/summary"),
  healthDiagnostics: () => request<CloneDiagnosis[]>("/api/health/diagnostics"),
  healthTimeline: (cloneId: string, limit = 50) =>
    request<HealthEvent[]>(`/api/health/clone/${cloneId}/timeline?limit=${limit}`),
  alerts: () => request<HealthEvent[]>("/api/health/alerts"),
  ackAlert: (alertId: string) =>
    request<HealthEvent>(`/api/health/alerts/${alertId}/ack`, { method: "POST" }),
  ackAllAlerts: () =>
    request<{ acknowledged: number }>("/api/health/alerts/ack-all", { method: "POST" }),
  proxies: () => request<Proxy[]>("/api/health/proxies"),
  addProxy: (payload: { address: string; type?: string; country?: string }) =>
    request<Proxy>("/api/health/proxies", { method: "POST", body: payload }),
  assignProxy: (cloneId: string) =>
    request<Proxy>(`/api/health/proxies/assign/${cloneId}`, { method: "POST" }),
  rotateProxy: (cloneId: string, reason = "manual") =>
    request<Proxy>(`/api/health/proxies/rotate/${cloneId}?reason=${encodeURIComponent(reason)}`, {
      method: "POST",
    }),
  proxyOverview: () => request<Record<string, number>>("/api/health/proxies/overview"),

  // ── Gói cước ───────────────────────────────────────────────────────────
  plans: () => request<PlanSpec[]>("/api/billing/plans"),
  subscription: () => request<Subscription>("/api/billing/subscription"),
  usage: () => request<Usage>("/api/billing/usage"),
  subscribe: (plan: string, months = 1) =>
    request<PaymentIntent>("/api/billing/subscribe", { method: "POST", body: { plan, months } }),
  confirmPayment: (plan: string, months = 1) =>
    request<Subscription>("/api/billing/confirm", { method: "POST", body: { plan, months } }),
};
