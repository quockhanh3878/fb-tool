"use client";
import { useState } from "react";

import {
  IconBarChart,
  IconFacebook,
  IconFilter,
  IconPosts,
  IconSearch,
  IconSparkles,
} from "@/components/icons";
import {
  Badge,
  BarChart,
  Button,
  Card,
  Empty,
  ErrorNote,
  Progress,
  Spinner,
  Stat,
  cx,
  useAsync,
} from "@/components/ui";
import { api } from "@/lib/api";

const RANGES = [7, 14, 30];

export default function StatsPage() {
  const [days, setDays] = useState(7);
  const stats = useAsync(() => api.dashboard(days), [days]);
  const groups = useAsync(() => api.groupPerformance());
  const breakdown = useAsync(() => api.statusBreakdown());

  const totals = stats.data?.trend.reduce(
    (acc, point) => ({
      posts: acc.posts + point.posts,
      matched: acc.matched + point.matched,
      comments: acc.comments + point.comments,
    }),
    { posts: 0, matched: 0, comments: 0 },
  );

  const matchRate = totals?.posts ? (totals.matched / totals.posts) * 100 : 0;

  return (
    <div className="space-y-6">
      {/* ── HEADER & RANGE PICKER ───────────────────────────────────────── */}
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
              <IconBarChart size={18} />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-2xl">
              Báo cáo & Thống kê
            </h1>
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Phân tích hiệu quả săn lead, tỉ lệ chuyển đổi AI và xếp hạng các hội nhóm Facebook.
          </p>
        </div>

        <div className="flex items-center gap-1 rounded-xl border border-slate-200/80 bg-slate-100/80 p-1 dark:border-slate-800 dark:bg-slate-900/80">
          {RANGES.map((range) => (
            <button
              key={range}
              onClick={() => setDays(range)}
              className={cx(
                "rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all duration-150",
                days === range
                  ? "bg-white text-indigo-600 shadow-xs dark:bg-slate-800 dark:text-indigo-400"
                  : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200",
              )}
            >
              {range} ngày qua
            </button>
          ))}
        </div>
      </header>

      <ErrorNote>{stats.error}</ErrorNote>
      {stats.loading && <Spinner label="Đang tổng hợp báo cáo…" />}

      {stats.data && (
        <>
          {/* ── STATS CARDS ─────────────────────────────────────────────── */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label={`Bài quét ${days} ngày`}
              value={(totals?.posts ?? 0).toLocaleString("vi-VN")}
              icon={<IconSearch size={18} />}
            />
            <Stat
              label="Bài phù hợp (Lead)"
              value={(totals?.matched ?? 0).toLocaleString("vi-VN")}
              tone="good"
              icon={<IconSparkles size={18} />}
            />
            <Stat
              label="Tỉ lệ phù hợp"
              value={`${matchRate.toFixed(1)}%`}
              hint="Khớp từ khóa & ngữ cảnh AI"
              icon={<IconFilter size={18} />}
            />
            <Stat
              label="Comment đã gửi"
              value={(totals?.comments ?? 0).toLocaleString("vi-VN")}
              hint={`Thành công ${(stats.data.success_rate * 100).toFixed(0)}%`}
              icon={<IconPosts size={18} />}
            />
          </div>

          {/* ── CHART ───────────────────────────────────────────────────── */}
          <Card
            title={
              <div className="flex items-center gap-2">
                <IconBarChart size={17} className="text-indigo-500" />
                <span>Diễn biến hoạt động {days} ngày qua</span>
              </div>
            }
          >
            <BarChart
              height={180}
              data={stats.data.trend.map((point) => ({
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
              <span>Rê chuột vào từng cột để xem số liệu chi tiết</span>
            </div>
          </Card>
        </>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* ── GROUP PERFORMANCE ────────────────────────────────────────── */}
        <Card
          title={
            <div className="flex items-center gap-2">
              <IconFacebook size={17} className="text-blue-600" />
              <span>Hiệu quả theo nhóm Facebook</span>
            </div>
          }
        >
          {groups.loading && <Spinner label="Đang đánh giá hiệu quả group…" />}
          {!groups.loading && !groups.data?.length && (
            <Empty icon={<IconFacebook size={20} />}>
              Chưa đủ dữ liệu. Hệ thống cần ít nhất một lượt quét bài để xếp hạng.
            </Empty>
          )}
          {!!groups.data?.length && (
            <div className="overflow-x-auto">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Tên Group</th>
                    <th className="text-right">Bài quét</th>
                    <th className="text-right">Lead</th>
                    <th className="text-right w-28">Tỉ lệ khớp</th>
                  </tr>
                </thead>
                <tbody>
                  {[...groups.data]
                    .sort((a, b) => b.match_rate - a.match_rate)
                    .map((row) => (
                      <tr key={row.group_id}>
                        <td className="font-semibold text-slate-800 dark:text-slate-200">
                          {row.group_name}
                        </td>
                        <td className="text-right tabular-nums text-slate-600 dark:text-slate-400">
                          {row.posts}
                        </td>
                        <td className="text-right tabular-nums font-semibold text-indigo-600 dark:text-indigo-400">
                          {row.matched}
                        </td>
                        <td className="text-right tabular-nums">
                          <div className="flex items-center justify-end gap-2">
                            <span className="font-bold text-xs">
                              {(row.match_rate * 100).toFixed(1)}%
                            </span>
                            <div className="h-1.5 w-12 rounded-full bg-slate-100 overflow-hidden dark:bg-slate-800">
                              <div
                                className="h-full rounded-full bg-indigo-600"
                                style={{ width: `${Math.min(100, row.match_rate * 100)}%` }}
                              />
                            </div>
                          </div>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
              <p className="mt-3.5 text-xs text-slate-400 leading-relaxed">
                💡 <b>Mẹo tối ưu:</b> Nhóm có tỉ lệ khớp thấp kéo dài nên được tạm dừng để tiết kiệm quota tài khoản và tập trung vào các nhóm có nhiều khách tiềm năng hơn.
              </p>
            </div>
          )}
        </Card>

        {/* ── STATUS BREAKDOWN ─────────────────────────────────────────── */}
        <Card
          title={
            <div className="flex items-center gap-2">
              <IconFilter size={17} className="text-indigo-500" />
              <span>Phân bố trạng thái bài viết</span>
            </div>
          }
        >
          {breakdown.loading && <Spinner label="Đang tải phân bố trạng thái…" />}
          {!breakdown.loading && !Object.keys(breakdown.data ?? {}).length && (
            <Empty icon={<IconPosts size={20} />}>Chưa có dữ liệu bài viết nào.</Empty>
          )}
          <ul className="space-y-3.5">
            {Object.entries(breakdown.data ?? {})
              .sort((a, b) => b[1] - a[1])
              .map(([status, count]) => {
                const totalPosts = totals?.posts || 1;
                const percent = Math.min(100, (count / totalPosts) * 100);
                return (
                  <li key={status} className="space-y-1.5">
                    <div className="flex items-center justify-between gap-3 text-xs">
                      <Badge value={status} />
                      <span className="font-bold tabular-nums text-slate-700 dark:text-slate-300">
                        {count.toLocaleString("vi-VN")} bài
                      </span>
                    </div>
                    <Progress percent={percent} />
                  </li>
                );
              })}
          </ul>
        </Card>
      </div>
    </div>
  );
}
