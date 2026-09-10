/** Kiểu dữ liệu khớp với schemas Pydantic của backend. */

export interface Subscription {
  plan: string;
  max_groups: number;
  max_clones: number;
  max_comments_per_day: number;
  ai_comments_enabled: boolean;
  bump_enabled: boolean;
  payment_status: string;
  expires_at: string | null;
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  telegram_chat_id: string | null;
  tier: string;
  is_admin: boolean;
  created_at: string;
  subscription: Subscription | null;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface Campaign {
  id: string;
  user_id: string;
  name: string;
  mode: "semi_auto" | "full_auto";
  service_name: string;
  service_specialties: string;
  service_strengths: string;
  landing_page_note: string;
  ai_filter_prompt: string;
  whitelist_keywords: string[];
  blacklist_keywords: string[];
  min_relevance_score: number;
  max_competitor_comments: number;
  is_active: boolean;
  max_comments_per_day: number;
  delay_min_seconds: number;
  delay_max_seconds: number;
  created_at: string;
}

export interface Group {
  id: string;
  campaign_id: string;
  group_url: string;
  group_key: string;
  group_name: string;
  status: string;
  scan_interval_minutes: number;
  last_scanned_at: string | null;
}

export interface Script {
  id: string;
  campaign_id: string;
  name: string;
  type: "spintax" | "ai_contextual";
  template_content: string;
  ai_system_prompt: string;
  attached_media_urls: string[];
  is_default: boolean;
  is_active: boolean;
  /** Số lần kịch bản đã được dùng — cơ sở để xoay vòng đều tay. */
  usage_count: number;
  last_used_at: string | null;
}

export interface ScriptPreview {
  variants: string[];
  total_variants: number;
}

export interface LintIssue {
  level: "error" | "warning";
  message: string;
}

export interface LintReport {
  ok: boolean;
  total_variants: number;
  group_count: number;
  shortest_words: number;
  longest_words: number;
  issues: LintIssue[];
  samples: string[];
  days_without_repeat: number;
}

export interface ExpandResult {
  variants: string[];
  total_variants: number;
  truncated: boolean;
}

export type CloneRole = "scout" | "shooter" | "poster" | "both" | "all";

export interface Clone {
  id: string;
  display_name: string;
  role: CloneRole;
  status: string;
  proxy_address: string | null;
  daily_comment_count: number;
  daily_comment_limit: number;
  daily_post_count?: number;
  daily_post_limit?: number;
  warmup_day: number;
  consecutive_failures: number;
  is_backup: boolean;
  has_cookies: boolean;
  last_activity_at: string | null;
  cooldown_until: string | null;
  created_at: string;
}

export interface PostPublishTarget {
  group_id: string;
  group_name: string;
  group_url?: string;
}

export interface PostPublishResult {
  group_id: string;
  group_name: string;
  group_url?: string;
  post_url: string;
  clone_id: string;
  clone_name: string;
  published_at: string;
  status: "success" | "failed";
  error?: string;
}

export interface PostPublish {
  id: string;
  campaign_id: string | null;
  clone_account_id: string | null;
  title: string;
  content_template: string;
  media_urls: string[];
  target_groups: PostPublishTarget[];
  status: "draft" | "scheduled" | "publishing" | "published" | "partially_published" | "failed";
  scheduled_at: string | null;
  published_at: string | null;
  publish_results: PostPublishResult[];
  error_message: string | null;
  created_at: string;
}

export interface PostPublishList {
  items: PostPublish[];
  total: number;
}

export interface Post {
  id: string;
  campaign_id: string;
  campaign_group_id: string | null;
  post_url: string;
  post_id_fb: string;
  author_name: string;
  content_text: string;
  existing_comment_count: number;
  ai_relevance_score: number;
  ai_reason: string;
  ai_extracted: Record<string, unknown>;
  status: string;
  discovered_at: string;
  notified_at: string | null;
  commented_at: string | null;
}

export interface PostList {
  items: Post[];
  total: number;
  limit: number;
  offset: number;
}

export interface CommentAction {
  id: string;
  comment_content: string;
  status: string;
  error_message: string | null;
  scheduled_at: string | null;
  executed_at: string | null;
}

export interface Bump {
  id: string;
  campaign_id: string;
  target_post_url: string;
  cron_schedule: number[];
  bump_messages: string[];
  is_active: boolean;
  last_bumped_at: string | null;
}

export interface DailyPoint {
  date: string;
  posts: number;
  matched: number;
  comments: number;
}

export interface DashboardStats {
  posts_today: number;
  matched_today: number;
  comments_today: number;
  success_rate: number;
  active_campaigns: number;
  total_groups: number;
  clones_healthy: number;
  clones_total: number;
  trend: DailyPoint[];
}

export interface GroupPerformance {
  group_id: string;
  group_name: string;
  posts: number;
  matched: number;
  match_rate: number;
}

export interface CloneHealth {
  id: string;
  display_name: string;
  status: string;
  daily_comment_count: number;
  daily_comment_limit: number;
  consecutive_failures: number;
  warmup: { day: number; total_days: number; percent: number; next_step: string };
  cooldown_until: string | null;
  proxy_address: string | null;
}

/** Một vấn đề tìm thấy khi chẩn đoán clone (backend: services/account_check.py). */
export interface CloneIssue {
  code: string;
  severity: "critical" | "warning" | "info";
  message: string;
  hint: string;
}

export interface CloneDiagnosis {
  clone_id: string;
  display_name: string;
  status: string;
  /** 0-100; mỗi vấn đề trừ một số điểm cố định. */
  score: number;
  grade: "good" | "warn" | "bad";
  /** Nhận việc được ngay bây giờ hay không. */
  ready: boolean;
  cookie_ok: boolean;
  cookie_expires_at: string | null;
  cookie_days_left: number | null;
  daily_comment_count: number;
  daily_comment_limit: number;
  consecutive_failures: number;
  proxy_address: string | null;
  issues: CloneIssue[];
  checked_at: string;
}

export interface IssueDigest extends CloneIssue {
  /** Số clone cùng dính vấn đề này. */
  count: number;
}

export interface HealthSummary {
  clone_count: number;
  ready_count: number;
  average_score: number;
  grade: "good" | "warn" | "bad";
  critical_count: number;
  warning_count: number;
  capacity_used: number;
  capacity_total: number;
  capacity_left: number;
  top_issues: IssueDigest[];
  unacknowledged_alerts: number;
}

export interface CheckAllResult {
  summary: HealthSummary;
  reports: CloneDiagnosis[];
  /** Tên các clone vừa bị hạ trạng thái vì cookie hỏng. */
  transitioned: string[];
}

export interface HealthEvent {
  id: string;
  clone_account_id: string;
  event_type: string;
  details: string;
  from_state: string | null;
  to_state: string | null;
  created_at: string;
}

export interface Proxy {
  id: string;
  address: string;
  type: string;
  country: string;
  status: string;
  assigned_to_clone_id: string | null;
  is_healthy: boolean;
  last_health_check: string | null;
}

export interface PlanSpec {
  plan: string;
  display_name: string;
  price_vnd: number;
  max_groups: number;
  max_clones: number;
  max_comments_per_day: number;
  ai_comments_enabled: boolean;
  bump_enabled: boolean;
}

export interface Usage {
  plan: string;
  is_active: boolean;
  expires_at: string | null;
  groups_used: number;
  groups_limit: number;
  clones_used: number;
  clones_limit: number;
}

export interface PaymentIntent {
  plan: string;
  months: number;
  amount_vnd: number;
  reference_code: string;
  instructions: string;
}

export interface CookieUploadResult {
  cookie_count: number;
  cookie_names: string[];
  fb_user_id: string;
  status: string;
  /** null = cookie phiên, file không mang hạn dùng. */
  expires_at: string | null;
  days_left: number | null;
}

export interface IngestResult {
  ingested: number;
  evaluated: number;
  matched: number;
  notified: number;
  queued: number;
  skipped: number;
}
