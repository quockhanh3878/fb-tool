"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ThemeToggle } from "@/components/ThemeToggle";
import {
  IconCheck,
  IconEye,
  IconEyeOff,
  IconHeartPulse,
  IconLayers,
  IconShieldCheck,
  IconSparkles,
} from "@/components/icons";
import { Button, ErrorNote, Field, Input, useToast } from "@/components/ui";
import { api, tokens } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const { refreshUser } = useAuth();
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      tokens.save(await api.login(email, password));
      await refreshUser();
      toast.success("Đăng nhập thành công!", "Chào mừng trở lại");
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Đăng nhập thất bại");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center p-4 sm:p-6 lg:p-8 overflow-hidden bg-slate-50 dark:bg-slate-950">
      {/* Background Glow Mesh */}
      <div className="pointer-events-none absolute -top-40 -right-40 h-96 w-96 rounded-full bg-indigo-500/15 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 -left-40 h-96 w-96 rounded-full bg-violet-500/15 blur-3xl" />

      {/* Theme Toggle Button top-right */}
      <div className="absolute top-5 right-5 z-20">
        <ThemeToggle />
      </div>

      <div className="relative z-10 w-full max-w-4xl overflow-hidden rounded-3xl border border-slate-200/80 bg-white/95 shadow-2xl backdrop-blur-md grid lg:grid-cols-5 dark:border-slate-800/80 dark:bg-slate-900/95">
        {/* Left Side: Brand & Feature Highlights */}
        <div className="relative hidden flex-col justify-between bg-gradient-to-br from-indigo-900 via-indigo-950 to-slate-950 p-8 text-white lg:col-span-2 lg:flex">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-500 to-violet-400 text-white shadow-lg shadow-indigo-500/30">
                <IconSparkles size={20} />
              </div>
              <span className="text-xl font-bold tracking-tight">CommHunter AI</span>
            </div>

            <p className="mt-3 text-xs text-indigo-200 leading-relaxed">
              Nền tảng tự động hóa tìm kiếm đơn hàng, giám sát bài viết và tương tác thông minh cho các Freelancer & Agency.
            </p>

            <div className="mt-8 space-y-4">
              <div className="flex items-start gap-3 text-xs text-slate-300">
                <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-500/20 text-indigo-400">
                  <IconCheck size={12} />
                </div>
                <span>Quét lead 24/7 theo từ khóa & bộ lọc AI</span>
              </div>
              <div className="flex items-start gap-3 text-xs text-slate-300">
                <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400">
                  <IconShieldCheck size={12} />
                </div>
                <span>Hệ thống chống ban 5 lớp & xoay vòng proxy</span>
              </div>
              <div className="flex items-start gap-3 text-xs text-slate-300">
                <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-violet-500/20 text-violet-400">
                  <IconSparkles size={12} />
                </div>
                <span>Spintax AI sinh hàng nghìn biến thể độc nhất</span>
              </div>
            </div>
          </div>

          <div className="mt-12 rounded-2xl bg-white/5 p-4 border border-white/10 backdrop-blur-xs">
            <p className="text-xs font-semibold text-indigo-300">Chế độ Bán Tự Động (Semi-Auto)</p>
            <p className="mt-1 text-[11px] text-slate-400 leading-relaxed">
              Duyệt ứng tuyển qua Telegram chỉ với 1 cú chạm trước khi clone bình luận vào group.
            </p>
          </div>
        </div>

        {/* Right Side: Login Form */}
        <div className="p-6 sm:p-10 lg:col-span-3 flex flex-col justify-center">
          <div className="mb-6">
            <div className="flex items-center gap-2 lg:hidden mb-4">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white">
                <IconSparkles size={18} />
              </div>
              <span className="font-bold text-lg">CommHunter AI</span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Đăng nhập tài khoản
            </h1>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              Nhập email và mật khẩu của bạn để truy cập bảng điều khiển.
            </p>
          </div>

          <form onSubmit={submit} className="space-y-4">
            <ErrorNote>{error}</ErrorNote>

            <Field label="Địa chỉ Email">
              <Input
                type="email"
                required
                placeholder="name@company.com"
                value={email}
                autoComplete="email"
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>

            <Field label="Mật khẩu">
              <div className="relative">
                <Input
                  type={showPassword ? "text" : "password"}
                  required
                  placeholder="••••••••"
                  value={password}
                  autoComplete="current-password"
                  onChange={(e) => setPassword(e.target.value)}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                  tabIndex={-1}
                  aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                >
                  {showPassword ? <IconEyeOff size={16} /> : <IconEye size={16} />}
                </button>
              </div>
            </Field>

            <Button
              type="submit"
              size="lg"
              loading={busy}
              disabled={busy || !email || !password}
              className="w-full mt-2"
            >
              {busy ? "Đang xử lý…" : "Đăng nhập ngay"}
            </Button>

            <div className="pt-4 text-center">
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Chưa có tài khoản?{" "}
                <Link
                  href="/register"
                  className="font-semibold text-indigo-600 hover:text-indigo-500 hover:underline dark:text-indigo-400"
                >
                  Đăng ký dùng thử miễn phí 7 ngày
                </Link>
              </p>
            </div>
          </form>
        </div>
      </div>
    </main>
  );
}
