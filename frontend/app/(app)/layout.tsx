"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ThemeToggle } from "@/components/ThemeToggle";
import {
  IconBarChart,
  IconCreditCard,
  IconDashboard,
  IconHeartPulse,
  IconLayers,
  IconLogout,
  IconMenu,
  IconPosts,
  IconSettings,
  IconSparkles,
  IconUsers,
  IconX,
} from "@/components/icons";
import { Badge, Button, cx } from "@/components/ui";
import { tokens } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const NAV = [
  { href: "/dashboard", label: "Tổng quan", Icon: IconDashboard },
  { href: "/campaigns", label: "Chiến dịch", Icon: IconLayers },
  { href: "/posts", label: "Bài viết", Icon: IconPosts },
  { href: "/clones", label: "Tài khoản clone", Icon: IconUsers },
  { href: "/health", label: "Sức khỏe & Proxy", Icon: IconHeartPulse },
  { href: "/stats", label: "Thống kê", Icon: IconBarChart },
  { href: "/billing", label: "Gói cước", Icon: IconCreditCard },
  { href: "/settings", label: "Cài đặt", Icon: IconSettings },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Chặn ngay ở client: không có token thì chuyển hướng đăng nhập
  useEffect(() => {
    if (!loading && !user && !tokens.access()) router.replace("/login");
  }, [loading, user, router]);

  // Tự động đóng mobile menu khi chuyển trang
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [pathname]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 dark:bg-slate-950">
        <div className="flex flex-col items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-lg shadow-indigo-500/30 animate-pulse">
            <IconSparkles size={24} />
          </div>
          <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
            Đang khởi động phiên làm việc…
          </p>
        </div>
      </div>
    );
  }

  if (!user) return null;

  const userInitials = (user.display_name || user.email || "CH")
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="flex min-h-screen bg-slate-50/60 dark:bg-slate-950">
      {/* ── SIDEBAR DESKTOP ──────────────────────────────────────────────── */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200/80 bg-white p-4 md:flex dark:border-slate-800/80 dark:bg-slate-900/95">
        {/* Brand Header */}
        <Link href="/dashboard" className="mb-6 flex items-center gap-3 px-2 py-1 group">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 text-white shadow-md shadow-indigo-500/25 group-hover:scale-105 transition-transform duration-200">
            <IconSparkles size={20} />
          </div>
          <div className="flex-1 overflow-hidden">
            <div className="flex items-center gap-1.5">
              <span className="font-bold tracking-tight text-slate-900 dark:text-white">
                CommHunter
              </span>
              <span className="rounded bg-indigo-100 px-1 py-0.2 text-[10px] font-bold text-indigo-700 dark:bg-indigo-950/80 dark:text-indigo-300">
                AI
              </span>
            </div>
            <p className="truncate text-xs text-slate-400 dark:text-slate-500">
              Săn lead Facebook tự động
            </p>
          </div>
        </Link>

        {/* Navigation Menu */}
        <nav className="flex-1 space-y-1 overflow-y-auto">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cx(
                  "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-150",
                  active
                    ? "bg-indigo-50/80 text-indigo-900 font-semibold dark:bg-indigo-950/50 dark:text-indigo-200"
                    : "text-slate-600 hover:bg-slate-100/80 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200",
                )}
              >
                {active && (
                  <span className="absolute left-0 top-2 bottom-2 w-1 rounded-r-full bg-indigo-600 dark:bg-indigo-400" />
                )}
                <item.Icon
                  size={19}
                  className={cx(
                    "shrink-0 transition-colors",
                    active
                      ? "text-indigo-600 dark:text-indigo-400"
                      : "text-slate-400 group-hover:text-slate-600 dark:text-slate-500 dark:group-hover:text-slate-300",
                  )}
                />
                <span className="truncate">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Quota Mini Widget */}
        <div className="mb-3 rounded-xl border border-slate-200/70 bg-slate-50/70 p-3 dark:border-slate-800/70 dark:bg-slate-800/40">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-slate-700 dark:text-slate-300">Gói hiện tại</span>
            <Badge value={user.subscription?.plan ?? "starter"} />
          </div>
          <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
            Hạn mức: {user.subscription?.max_comments_per_day ?? 20} comment/ngày
          </p>
          <Link
            href="/billing"
            className="mt-2 block text-center text-xs font-semibold text-indigo-600 hover:text-indigo-700 dark:text-indigo-400"
          >
            Nâng cấp gói →
          </Link>
        </div>

        {/* User Card & Actions */}
        <div className="border-t border-slate-200/80 pt-3 dark:border-slate-800/80">
          <div className="flex items-center justify-between gap-2 px-1">
            <div className="flex min-w-0 items-center gap-2.5">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-slate-700 to-slate-900 text-xs font-bold text-white shadow-xs dark:from-indigo-600 dark:to-violet-600">
                {userInitials}
              </div>
              <div className="min-w-0">
                <p className="truncate text-xs font-semibold text-slate-800 dark:text-slate-200">
                  {user.display_name || "Thành viên"}
                </p>
                <p className="truncate text-[11px] text-slate-400">{user.email}</p>
              </div>
            </div>
            <ThemeToggle />
          </div>

          <Button
            variant="ghost"
            size="sm"
            className="mt-2.5 w-full justify-center text-xs text-rose-600 hover:bg-rose-50 hover:text-rose-700 dark:text-rose-400 dark:hover:bg-rose-950/30"
            onClick={logout}
            icon={<IconLogout size={14} />}
          >
            Đăng xuất
          </Button>
        </div>
      </aside>

      {/* ── MAIN CONTENT AREA ────────────────────────────────────────────── */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Mobile Sticky Header */}
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur-md md:hidden dark:border-slate-800/80 dark:bg-slate-900/90">
          <Link href="/dashboard" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white">
              <IconSparkles size={16} />
            </div>
            <span className="font-bold text-slate-900 dark:text-white">CommHunter</span>
          </Link>

          <div className="flex items-center gap-2">
            <ThemeToggle />
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
              aria-label="Mở menu"
            >
              <IconMenu size={19} />
            </button>
          </div>
        </header>

        {/* Mobile Off-canvas Drawer */}
        {mobileMenuOpen && (
          <div className="fixed inset-0 z-50 flex md:hidden">
            <div
              className="fixed inset-0 bg-slate-950/60 backdrop-blur-xs transition-opacity"
              onClick={() => setMobileMenuOpen(false)}
            />
            <div className="relative flex w-4/5 max-w-xs flex-col bg-white p-5 shadow-2xl dark:bg-slate-900">
              <div className="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-slate-800">
                <div className="flex items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white">
                    <IconSparkles size={16} />
                  </div>
                  <span className="font-bold">CommHunter AI</span>
                </div>
                <button
                  onClick={() => setMobileMenuOpen(false)}
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                >
                  <IconX size={18} />
                </button>
              </div>

              <nav className="mt-4 flex-1 space-y-1.5 overflow-y-auto">
                {NAV.map((item) => {
                  const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={cx(
                        "flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition-colors",
                        active
                          ? "bg-indigo-600 text-white"
                          : "text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
                      )}
                    >
                      <item.Icon size={18} />
                      {item.label}
                    </Link>
                  );
                })}
              </nav>

              <div className="mt-auto border-t border-slate-200 pt-4 dark:border-slate-800">
                <p className="truncate text-xs text-slate-500 mb-2">{user.email}</p>
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full justify-center text-rose-600 dark:text-rose-400"
                  onClick={logout}
                  icon={<IconLogout size={14} />}
                >
                  Đăng xuất
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Main Content Viewport */}
        <main className="mx-auto w-full max-w-7xl flex-1 space-y-6 p-4 sm:p-6 md:p-8">
          {children}
        </main>
      </div>
    </div>
  );
}
