"use client";
import Link from "next/link";

import { IssueList, ScoreRing } from "@/components/AccountHealth";
import {
  IconAlertCircle,
  IconArrowRight,
  IconChevronRight,
  IconExternalLink,
  IconHeartPulse,
  IconLayers,
  IconPlus,
  IconPosts,
  IconSearch,
  IconSparkles,
  IconUsers,
} from "@/components/icons";
import {
  Badge,
  BarChart,
  Button,
  Card,
  Empty,
  ErrorNote,
  Skeleton,
  Spinner,
  Stat,
  cx,
  fmtDate,
  useAsync,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function DashboardPage() {
  const { user } = useAuth();
  const stats = useAsync(() => api.dashboard(7));
  const alerts = useAsync(() => api.alerts());
  const health = useAsync(() => api.healthSummary());
  const feed = useAsync(() => api.posts({ status: "notified", limit: 6 }));

  if (stats.loading && !stats.data) {
    return (
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-9 w-36" />
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-64 lg:col-span-2" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }

  if (stats.error) return <ErrorNote>{stats.error}</ErrorNote>;
  const data = stats.data!;

  const healthTone =
    health.data?.grade ??
    (data.clones_total === 0
      ? "warn"
      : data.clones_healthy === data.clones_total
        ? "good"
        : data.clones_healthy === 0
          ? "bad"
          : "warn");

  return (
    <div className="space-y-6">
      {/* ── TOP HEADER & QUICK ACTIONS ─────────────────────────────────── */}
      <header className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200/80 bg-white/90 p-5 shadow-xs backdrop-blur-md dark:border-slate-800/80 dark:bg-slate-900/90">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-2xl">
              Chào {user?.display_name || user?.email?.split("@")[0]} 👋
            </h1>
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Sẵn sàng
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Tổng hợp dữ liệu săn lead Facebook và trạng thái tài khoản hôm nay.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <Link href="/campaigns">
            <Button size="sm" icon={<IconPlus size={15} />}>
              Chiến dịch mới
            </Button>
          </Link>
          <Link href="/posts">
            <Button size="sm" variant="ghost" icon={<IconPosts size={15} />}>
              Xem bài chờ duyệt
            </Button>
          </Link>
        </div>
      </header>

      {/* ── STATS CARDS ─────────────────────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Bài quét hôm nay"
          value={data.posts_today.toLocaleString("vi-VN")}
          hint="Tự động thu thập từ các group"
          icon={<IconSearch size={18} />}
        />
        <Stat
          label="Bài phù hợp (Lead)"
          value={data.matched_today.toLocaleString("vi-VN")}
          tone="good"
          hint={`Đạt ${data.posts_today ? ((data.matched_today / data.posts_today) * 100).toFixed(1) : 0}% tỉ lệ khớp AI`}
          icon={<IconSparkles size={18} />}
        />
        <Stat
          label="Comment đã gửi"
          value={data.comments_today.toLocaleString("vi-VN")}
          hint={`Tỉ lệ thành công ${(data.success_rate * 100).toFixed(0)}%`}
          icon={<IconPosts size={18} />}
        />
        <Stat
          label="Clone sẵn sàng"
          value={
            health.data
              ? `${health.data.ready_count}/${health.data.clone_count}`
              : `${data.clones_healthy}/${data.clones_total}`
          }
          tone={healthTone}
          hint={
            data.clones_total === 0
              ? "Chưa thêm clone nào"
              : health.data
                ? `Điểm TB ${health.data.average_score}/100 · còn ${health.data.capacity_left} quota`
                : undefined
          }
          icon={<IconHeartPulse size={18} />}
        />
      </div>

      {/* ── 7-DAY TREND & HEALTH ALERT ─────────────────────────────────── */}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card
          title={
            <div className="flex items-center gap-2">
              <IconLayers size={17} className="text-indigo-500" />
              <span>Hiệu suất săn lead 7 ngày gần nhất</span>
            </div>
          }
          className="lg:col-span-2"
        >
          <BarChart
            height={160}
            data={data.trend.map((point) => ({
              label: point.date.slice(5),
              values: [
                { name: "Bài quét", value: point.posts, color: "bg-slate-300 dark:bg-slate-700" },
                { name: "Phù hợp", value: point.matched, color: "bg-indigo-500 dark:bg-indigo-400" },
                { name: "Comment", value: point.comments, color: "bg-emerald-500" },
              ],
            }))}
          />
          <div className="mt-4 flex flex-wrap items-center justify-between border-t border-slate-100 pt-3 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
            <div className="flex gap-4">
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-slate-400 dark:bg-slate-600" />
                Bài quét
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-indigo-500" />
                Khớp tiêu chí AI
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                Comment thành công
              </span>
            </div>
            <Link href="/stats" className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">
              Chi tiết thống kê →
            </Link>
          </div>
        </Card>

        {/* Cảnh báo sức khỏe */}
        <Card
          title={
            <div className="flex items-center gap-2">
              <IconHeartPulse size={17} className="text-rose-500" />
              <span>Sức khỏe tài khoản & Cảnh báo</span>
            </div>
          }
          action={
            <Link
              href="/health"
              className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
            >
              Xem tất cả
            </Link>
          }
        >
          {health.data && (
            <div className="mb-4 flex items-center justify-between rounded-xl bg-slate-50/80 p-3 dark:bg-slate-800/40">
              <div className="text-xs">
                <p className="font-semibold text-slate-800 dark:text-slate-200">Điểm sức khỏe tổng thể</p>
                <p className="text-slate-500">
                  {health.data.ready_count}/{health.data.clone_count} clone đang sẵn sàng
                </p>
              </div>
              <ScoreRing score={health.data.average_score} grade={health.data.grade} size="sm" />
            </div>
          )}

          {!!health.data?.top_issues.length && (
            <div className="mb-3">
              <IssueList issues={health.data.top_issues.slice(0, 2)} />
            </div>
          )}

          {alerts.loading && <Spinner label="Đang kiểm tra cảnh báo…" />}
          {!alerts.loading && !alerts.data?.length && !health.data?.top_issues.length && (
            <Empty
              icon={<IconSparkles size={20} className="text-emerald-500" />}
            >
              Hệ thống hoạt động mượt mà, không có cảnh báo nào!
            </Empty>
          )}

          <ul className="space-y-2.5">
            {alerts.data?.slice(0, 4).map((event) => (
              <li
                key={event.id}
                className="rounded-xl border border-slate-100 bg-slate-50/50 p-2.5 text-xs dark:border-slate-800/60 dark:bg-slate-800/30"
              >
                <div className="flex items-center justify-between gap-2">
                  <Badge value={event.to_state ?? event.event_type} />
                  <span className="text-[11px] text-slate-400">{fmtDate(event.created_at)}</span>
                </div>
                <p className="mt-1 text-slate-600 dark:text-slate-300 leading-snug">
                  {event.details}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {/* ── LEADS FEED INBOX ────────────────────────────────────────────── */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <IconPosts size={17} className="text-indigo-600 dark:text-indigo-400" />
            <span>Lead mới tìm thấy đang chờ bạn duyệt</span>
          </div>
        }
        action={
          <Link
            href="/posts"
            className="flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:underline dark:text-indigo-400"
          >
            Mở toàn bộ ({feed.data?.total ?? 0})
            <IconChevronRight size={14} />
          </Link>
        }
      >
        {feed.loading && <Spinner label="Đang tải danh sách bài viết…" />}
        {!feed.loading && !feed.data?.items.length && (
          <Empty
            icon={<IconSearch size={22} />}
            action={
              <Link href="/campaigns">
                <Button size="sm" variant="outline">
                  Kiểm tra từ khóa chiến dịch
                </Button>
              </Link>
            }
          >
            Chưa có bài nào đang chờ duyệt. Scout Worker đang tích cực rà soát các group Facebook.
          </Empty>
        )}

        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {feed.data?.items.map((post) => {
            const isHighMatch = post.ai_relevance_score >= 0.8;
            return (
              <div
                key={post.id}
                className="flex flex-col justify-between rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs transition-all duration-150 hover:border-indigo-300 hover:shadow-xs dark:border-slate-800 dark:bg-slate-850/50 dark:hover:border-indigo-500/50"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-tr from-indigo-500 to-violet-500 text-xs font-bold text-white">
                        {post.author_name?.[0]?.toUpperCase() || "FB"}
                      </div>
                      <div className="min-w-0">
                        <p className="truncate text-xs font-bold text-slate-800 dark:text-slate-200">
                          {post.author_name || "Thành viên Facebook"}
                        </p>
                        <p className="text-[10px] text-slate-400">{fmtDate(post.discovered_at)}</p>
                      </div>
                    </div>
                    <span
                      className={cx(
                        "rounded-full px-2 py-0.5 text-[10px] font-bold",
                        isHighMatch
                          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                          : "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300",
                      )}
                    >
                      ★ {post.ai_relevance_score.toFixed(2)}
                    </span>
                  </div>

                  <p className="mt-3 line-clamp-3 text-xs text-slate-600 dark:text-slate-300 leading-relaxed whitespace-pre-line">
                    {post.content_text}
                  </p>
                </div>

                <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3 dark:border-slate-800/80">
                  <Badge value={post.status} />
                  <Link
                    href={`/posts?post=${post.id}`}
                    className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-700 dark:text-indigo-400"
                  >
                    Xem & Ứng tuyển
                    <IconChevronRight size={14} />
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
