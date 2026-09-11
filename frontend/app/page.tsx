"use client";
import Link from "next/link";
import { useEffect, useState } from "react";

import { ThemeToggle } from "@/components/ThemeToggle";
import {
  IconArrowRight,
  IconCheck,
  IconClock,
  IconDashboard,
  IconExternalLink,
  IconFacebook,
  IconHeartPulse,
  IconLayers,
  IconPosts,
  IconSearch,
  IconShieldCheck,
  IconSparkles,
  IconTelegram,
  IconUsers,
  IconZap,
} from "@/components/icons";
import { Badge, Button, cx } from "@/components/ui";
import { tokens } from "@/lib/api";

export default function LandingPage() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    setIsLoggedIn(Boolean(tokens.access()));
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 transition-colors dark:bg-slate-950 dark:text-slate-100">
      {/* ── TOP NOTIFICATION BAR (NẾU ĐÃ ĐĂNG NHẬP) ────────────────────── */}
      {isLoggedIn && (
        <div className="bg-indigo-600 px-4 py-2 text-center text-xs font-semibold text-white">
          <span>Bạn đang đăng nhập tài khoản CommHunter. </span>
          <Link
            href="/dashboard"
            className="underline underline-offset-4 hover:text-indigo-100 ml-1 inline-flex items-center gap-1"
          >
            Vào Dashboard ngay <IconArrowRight size={13} />
          </Link>
        </div>
      )}

      {/* ── HEADER NAVIGATION ─────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/85 backdrop-blur-md dark:border-slate-800/80 dark:bg-slate-950/85">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 text-white shadow-md shadow-indigo-500/25 group-hover:scale-105 transition-transform duration-200">
              <IconSparkles size={20} />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="text-lg font-bold tracking-tight text-slate-900 dark:text-white">
                  CommHunter
                </span>
                <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-bold text-indigo-700 dark:bg-indigo-950/80 dark:text-indigo-300">
                  AI
                </span>
              </div>
              <p className="text-[10px] font-medium text-slate-400">Auto Lead Facebook</p>
            </div>
          </Link>

          {/* Nav Links */}
          <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-slate-600 dark:text-slate-300">
            <a href="#features" className="hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors">
              Tính năng
            </a>
            <a href="#how-it-works" className="hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors">
              Cách hoạt động
            </a>
            <a href="#pricing" className="hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors">
              Bảng giá
            </a>
            <a href="#faq" className="hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors">
              Hỏi đáp
            </a>
          </nav>

          {/* Action Buttons */}
          <div className="flex items-center gap-3">
            <ThemeToggle />
            {isLoggedIn ? (
              <Link href="/dashboard">
                <Button size="sm" icon={<IconDashboard size={15} />}>
                  Vào Dashboard
                </Button>
              </Link>
            ) : (
              <>
                <Link href="/login" className="hidden sm:inline-block">
                  <Button variant="ghost" size="sm">
                    Đăng nhập
                  </Button>
                </Link>
                <Link href="/register">
                  <Button size="sm" icon={<IconArrowRight size={15} />}>
                    Dùng thử ngay
                  </Button>
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* ── HERO SECTION ──────────────────────────────────────────────── */}
      <section className="relative overflow-hidden pt-12 pb-20 md:pt-20 md:pb-28">
        {/* Ambient Gradient Background Glow */}
        <div className="pointer-events-none absolute -top-40 left-1/2 -z-10 h-[500px] w-[800px] -translate-x-1/2 rounded-full bg-gradient-to-tr from-indigo-500/20 to-violet-500/15 blur-3xl" />

        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 text-center">
          {/* Top Pill Badge */}
          <div className="inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50/80 px-4 py-1.5 text-xs font-semibold text-indigo-800 backdrop-blur-xs dark:border-indigo-900/60 dark:bg-indigo-950/50 dark:text-indigo-300">
            <span className="flex h-2 w-2 rounded-full bg-indigo-600 animate-pulse" />
            Nền tảng tự động hóa săn khách Facebook Groups thế hệ mới
          </div>

          {/* Headline */}
          <h1 className="mt-6 text-4xl font-extrabold tracking-tight text-slate-900 sm:text-5xl md:text-6xl dark:text-white">
            Tự động tìm khách & ứng tuyển <br className="hidden sm:inline" />
            <span className="bg-gradient-to-r from-indigo-600 via-violet-600 to-indigo-500 bg-clip-text text-transparent dark:from-indigo-400 dark:via-violet-400 dark:to-indigo-300">
              24/7 trên Facebook Groups
            </span>
          </h1>

          {/* Subtitle */}
          <p className="mx-auto mt-6 max-w-2xl text-base text-slate-600 sm:text-lg dark:text-slate-300 leading-relaxed">
            Thay thế hoàn toàn CTV thủ công bằng hệ thống AI thông minh. Quét hàng trăm nhóm Facebook, lọc bài viết đúng nhu cầu, viết bình luận ứng tuyển tự nhiên và duyệt lệnh một chạm qua Telegram.
          </p>

          {/* Action CTAs */}
          <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
            <Link href={isLoggedIn ? "/dashboard" : "/register"}>
              <Button size="lg" className="shadow-lg shadow-indigo-500/25" icon={<IconArrowRight size={18} />}>
                {isLoggedIn ? "Vào trang quản trị" : "Bắt đầu dùng thử miễn phí"}
              </Button>
            </Link>
            <a href="#pricing">
              <Button variant="ghost" size="lg">
                Xem bảng giá các gói
              </Button>
            </a>
          </div>

          {/* Trust Highlights */}
          <div className="mt-8 flex flex-wrap items-center justify-center gap-6 text-xs text-slate-500 dark:text-slate-400">
            <span className="flex items-center gap-1.5">
              <IconCheck size={14} className="text-emerald-500" /> 100% trình duyệt thật, chống ban nick
            </span>
            <span className="flex items-center gap-1.5">
              <IconCheck size={14} className="text-emerald-500" /> Không cần biết lập trình
            </span>
            <span className="flex items-center gap-1.5">
              <IconCheck size={14} className="text-emerald-500" /> Duyệt bài nhanh qua Telegram
            </span>
          </div>

          {/* ── HERO INTERACTIVE SIMULATION CARD ────────────────────────── */}
          <div className="mt-14 mx-auto max-w-4xl overflow-hidden rounded-2xl border border-slate-200/90 bg-white p-2 shadow-2xl dark:border-slate-800 dark:bg-slate-900/90">
            <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-5 text-left dark:border-slate-800 dark:bg-slate-950/60">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3 dark:border-slate-800">
                <div className="flex items-center gap-2">
                  <span className="flex h-3 w-3 rounded-full bg-rose-500" />
                  <span className="flex h-3 w-3 rounded-full bg-amber-500" />
                  <span className="flex h-3 w-3 rounded-full bg-emerald-500" />
                  <span className="ml-2 text-xs font-semibold text-slate-600 dark:text-slate-400">
                    Live Monitor Radar — Chiến dịch &quot;Dịch vụ Thiết Kế UI/UX & Website&quot;
                  </span>
                </div>
                <Badge value="active">Đang săn lead 24/7</Badge>
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-2">
                {/* Left: Discovered post */}
                <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
                  <div className="flex items-center justify-between text-xs text-slate-400">
                    <span className="font-semibold text-indigo-600 dark:text-indigo-400">
                      Group: Cộng đồng Startup & Kinh Doanh
                    </span>
                    <span>Vừa phát hiện 30 giây trước</span>
                  </div>
                  <h4 className="mt-2 text-sm font-bold text-slate-800 dark:text-slate-100">
                    Nguyễn Văn An: &quot;Mình cần tìm team thiết kế lại landing page bán hàng, yêu cầu hiện đại, chuẩn SEO và load nhanh. Ai làm được inbox mình nhé...&quot;
                  </h4>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span className="rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
                      AI Khớp 96%
                    </span>
                    <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                      Từ khóa: thiết kế, landing page
                    </span>
                  </div>
                </div>

                {/* Right: AI comment suggestion */}
                <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-4 dark:border-indigo-950 dark:bg-indigo-950/20">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-indigo-700 dark:text-indigo-300 flex items-center gap-1">
                      <IconSparkles size={14} /> Kịch bản AI ứng tuyển tự động
                    </span>
                    <span className="rounded-full bg-indigo-200/60 px-2 py-0.5 text-[10px] font-bold text-indigo-800 dark:bg-indigo-900/60 dark:text-indigo-200">
                      Spintax #2
                    </span>
                  </div>
                  <p className="mt-2 text-xs text-slate-700 dark:text-slate-300 italic leading-relaxed">
                    &quot;Chào anh An, bên em chuyên thiết kế landing page bán hàng chuyển đổi cao, tối ưu UX và chuẩn mobile. Em đã gửi portfolio dự án tương tự qua tin nhắn, anh check giúp em nhé!&quot;
                  </p>
                  <div className="mt-3 flex items-center justify-between pt-2 border-t border-indigo-200/60 dark:border-indigo-900/60 text-xs">
                    <span className="text-slate-500 dark:text-slate-400">
                      Nick bắn: <strong className="text-slate-700 dark:text-slate-200">Clone Mai Phương (Shooter)</strong>
                    </span>
                    <span className="text-emerald-600 font-semibold dark:text-emerald-400">
                      Đã đẩy vào hàng đợi
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── CORE FEATURES GRID ────────────────────────────────────────── */}
      <section id="features" className="border-t border-slate-200/80 bg-white py-20 dark:border-slate-800/80 dark:bg-slate-900">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-indigo-600 dark:text-indigo-400">
              Công nghệ tiên tiến
            </h2>
            <p className="mt-2 text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl dark:text-white">
              6 Ưu thế vượt trội của CommHunter AI
            </p>
            <p className="mx-auto mt-4 max-w-2xl text-sm text-slate-500 dark:text-slate-400">
              Được thiết kế chuyên biệt để vận hành liên tục, an toàn và mang lại hiệu quả chuyển đổi cao nhất.
            </p>
          </div>

          <div className="mt-14 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {/* Feature 1 */}
            <div className="rounded-2xl border border-slate-200/80 bg-slate-50/50 p-6 transition-all duration-200 hover:border-indigo-300 hover:shadow-md dark:border-slate-800 dark:bg-slate-950/40 dark:hover:border-indigo-800">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-100 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-400">
                <IconSearch size={22} />
              </div>
              <h3 className="mt-4 text-base font-bold text-slate-900 dark:text-white">
                Quét & Lọc bài thông minh với AI
              </h3>
              <p className="mt-2 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                Sử dụng mô hình ngôn ngữ lớn để đọc hiểu ngữ cảnh bài viết, loại bỏ tin tuyển dụng dạo, tin spam và chỉ giữ lại những bài viết thật sự có nhu cầu thuê dịch vụ.
              </p>
            </div>

            {/* Feature 2 */}
            <div className="rounded-2xl border border-slate-200/80 bg-slate-50/50 p-6 transition-all duration-200 hover:border-indigo-300 hover:shadow-md dark:border-slate-800 dark:bg-slate-950/40 dark:hover:border-indigo-800">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-violet-100 text-violet-600 dark:bg-violet-950 dark:text-violet-400">
                <IconUsers size={22} />
              </div>
              <h3 className="mt-4 text-base font-bold text-slate-900 dark:text-white">
                Phân bổ Đa vai trò Clone (Scout / Shooter / Poster)
              </h3>
              <p className="mt-2 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                Tách biệt hoàn toàn: tài khoản chuyên quét bài (Scout), tài khoản chuyên comment ứng tuyển (Shooter) và tài khoản đăng bài seeding (Poster). Không sợ checkpoint lây chéo.
              </p>
            </div>

            {/* Feature 3 */}
            <div className="rounded-2xl border border-slate-200/80 bg-slate-50/50 p-6 transition-all duration-200 hover:border-indigo-300 hover:shadow-md dark:border-slate-800 dark:bg-slate-950/40 dark:hover:border-indigo-800">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-100 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400">
                <IconShieldCheck size={22} />
              </div>
              <h3 className="mt-4 text-base font-bold text-slate-900 dark:text-white">
                Anti-Ban Engine 3 Lớp Bền Bỉ
              </h3>
              <p className="mt-2 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                Gắn cố định dấu vân tay trình duyệt Chrome thật, tự động ủ ấm tài khoản mới 7 ngày, kiểm tra session định kỳ và điều chỉnh độ giãn thời gian thích ứng tránh thuật toán spam.
              </p>
            </div>

            {/* Feature 4 */}
            <div className="rounded-2xl border border-slate-200/80 bg-slate-50/50 p-6 transition-all duration-200 hover:border-indigo-300 hover:shadow-md dark:border-slate-800 dark:bg-slate-950/40 dark:hover:border-indigo-800">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-sky-100 text-sky-600 dark:bg-sky-950 dark:text-sky-400">
                <IconLayers size={22} />
              </div>
              <h3 className="mt-4 text-base font-bold text-slate-900 dark:text-white">
                Xoay vòng Kịch bản Spintax Chống Lặp
              </h3>
              <p className="mt-2 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                Hệ thống đo độ giống nhau (Jaccard) với 30 comment gần nhất, tự động kiểm lỗi cú pháp tức thì và phân bổ lượt dùng đồng đều giữa các kịch bản để lời lẽ luôn tự nhiên.
              </p>
            </div>

            {/* Feature 5 */}
            <div className="rounded-2xl border border-slate-200/80 bg-slate-50/50 p-6 transition-all duration-200 hover:border-indigo-300 hover:shadow-md dark:border-slate-800 dark:bg-slate-950/40 dark:hover:border-indigo-800">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-100 text-blue-600 dark:bg-blue-950 dark:text-blue-400">
                <IconTelegram size={22} />
              </div>
              <h3 className="mt-4 text-base font-bold text-slate-900 dark:text-white">
                Duyệt Lệnh Một Chạm Qua Telegram
              </h3>
              <p className="mt-2 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                Khi phát hiện lead mới, bot Telegram gửi thông báo kèm nút bấm Duyệt ứng tuyển hoặc Bỏ qua. Bạn có thể chốt khách ngay trên điện thoại khi đang di chuyển.
              </p>
            </div>

            {/* Feature 6 */}
            <div className="rounded-2xl border border-slate-200/80 bg-slate-50/50 p-6 transition-all duration-200 hover:border-indigo-300 hover:shadow-md dark:border-slate-800 dark:bg-slate-950/40 dark:hover:border-indigo-800">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-amber-100 text-amber-600 dark:bg-amber-950 dark:text-amber-400">
                <IconZap size={22} />
              </div>
              <h3 className="mt-4 text-base font-bold text-slate-900 dark:text-white">
                Tự Động Bump Bài & Lấy Nhóm
              </h3>
              <p className="mt-2 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                Lên lịch đẩy bài viết cũ lên đầu trang theo khung giờ vàng và tính năng tự động cào toàn bộ danh sách group đã tham gia từ tài khoản clone chỉ với 1 click.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS SECTION ──────────────────────────────────────── */}
      <section id="how-it-works" className="py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-indigo-600 dark:text-indigo-400">
              Quy trình đơn giản
            </h2>
            <p className="mt-2 text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl dark:text-white">
              Sẵn sàng chạy chỉ sau 4 bước
            </p>
          </div>

          <div className="mt-14 grid gap-8 md:grid-cols-4">
            <div className="relative rounded-2xl border border-slate-200/80 bg-white p-6 shadow-xs dark:border-slate-800 dark:bg-slate-900">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-600 text-sm font-bold text-white">
                1
              </span>
              <h4 className="mt-4 text-sm font-bold text-slate-900 dark:text-white">
                Tạo chiến dịch & Nhóm
              </h4>
              <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                Đặt tên dịch vụ của bạn và thêm danh sách các Facebook Group tiềm năng muốn theo dõi.
              </p>
            </div>

            <div className="relative rounded-2xl border border-slate-200/80 bg-white p-6 shadow-xs dark:border-slate-800 dark:bg-slate-900">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-600 text-sm font-bold text-white">
                2
              </span>
              <h4 className="mt-4 text-sm font-bold text-slate-900 dark:text-white">
                Nạp Cookie Clone
              </h4>
              <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                Nạp file cookie cho tài khoản clone để tự động chạy qua trình duyệt Chrome an toàn.
              </p>
            </div>

            <div className="relative rounded-2xl border border-slate-200/80 bg-white p-6 shadow-xs dark:border-slate-800 dark:bg-slate-900">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-600 text-sm font-bold text-white">
                3
              </span>
              <h4 className="mt-4 text-sm font-bold text-slate-900 dark:text-white">
                Soạn Kịch bản AI
              </h4>
              <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                Tùy chỉnh các câu chào hàng, giới thiệu portfolio dưới dạng Spintax chống trùng lặp.
              </p>
            </div>

            <div className="relative rounded-2xl border border-slate-200/80 bg-white p-6 shadow-xs dark:border-slate-800 dark:bg-slate-900">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-600 text-sm font-bold text-white">
                4
              </span>
              <h4 className="mt-4 text-sm font-bold text-slate-900 dark:text-white">
                Duyệt Lead & Chốt Khách
              </h4>
              <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                Nhận thông báo bài viết mới qua Telegram, duyệt bắn comment tự động và đón khách hàng về inbox.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── PRICING PLANS ─────────────────────────────────────────────── */}
      <section id="pricing" className="border-t border-slate-200/80 bg-slate-100/60 py-20 dark:border-slate-800/80 dark:bg-slate-950/60">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-indigo-600 dark:text-indigo-400">
              Bảng giá dịch vụ
            </h2>
            <p className="mt-2 text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl dark:text-white">
              Lựa chọn gói cước phù hợp nhu cầu
            </p>
            <p className="mx-auto mt-4 max-w-2xl text-sm text-slate-500 dark:text-slate-400">
              Bắt đầu với chi phí tối ưu, nâng cấp linh hoạt khi quy mô kinh doanh mở rộng.
            </p>
          </div>

          <div className="mt-14 grid gap-8 lg:grid-cols-3">
            {/* Starter Plan */}
            <div className="rounded-2xl border border-slate-200/90 bg-white p-7 shadow-xs dark:border-slate-800 dark:bg-slate-900">
              <h3 className="text-lg font-bold text-slate-900 dark:text-white">Gói Starter</h3>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Phù hợp cá nhân bắt đầu tìm khách</p>
              <div className="mt-6 flex items-baseline gap-1">
                <span className="text-3xl font-extrabold text-slate-900 dark:text-white">199.000đ</span>
                <span className="text-xs text-slate-400">/tháng</span>
              </div>
              <ul className="mt-6 space-y-3 text-xs text-slate-600 dark:text-slate-300">
                <li className="flex items-center gap-2">
                  <IconCheck size={15} className="text-emerald-500" /> Tối đa 5 Facebook Group
                </li>
                <li className="flex items-center gap-2">
                  <IconCheck size={15} className="text-emerald-500" /> 1 Tài khoản Clone
                </li>
                <li className="flex items-center gap-2">
                  <IconCheck size={15} className="text-emerald-500" /> 20 Comment / ngày
                </li>
                <li className="flex items-center gap-2">
                  <IconCheck size={15} className="text-emerald-500" /> Kịch bản Spintax chống trùng
                </li>
                <li className="flex items-center gap-2">
                  <IconCheck size={15} className="text-emerald-500" /> Nhận thông báo qua Telegram
                </li>
              </ul>
              <Link href="/register" className="mt-8 block">
                <Button variant="ghost" className="w-full">
                  Chọn gói Starter
                </Button>
              </Link>
            </div>

            {/* Pro Plan (Highlight) */}
            <div className="relative rounded-2xl border-2 border-indigo-600 bg-white p-7 shadow-xl shadow-indigo-500/10 dark:border-indigo-500 dark:bg-slate-900">
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-indigo-600 px-3 py-0.5 text-[11px] font-bold text-white shadow-sm">
                Được ưa chuộng nhất
              </div>
              <h3 className="text-lg font-bold text-slate-900 dark:text-white">Gói Pro</h3>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Cho freelancer & shop dịch vụ chuyên nghiệp</p>
              <div className="mt-6 flex items-baseline gap-1">
                <span className="text-3xl font-extrabold text-indigo-600 dark:text-indigo-400">399.000đ</span>
                <span className="text-xs text-slate-400">/tháng</span>
              </div>
              <ul className="mt-6 space-y-3 text-xs text-slate-600 dark:text-slate-300">
                <li className="flex items-center gap-2">
                  <IconCheck size={15} className="text-indigo-600 dark:text-indigo-400" /> Tối đa 20 Facebook Group
                </li>
                <li className="flex items-center gap-2">
                  <IconCheck size={15} className="text-indigo-600 dark:text-indigo-400" /> 3 Tài khoản Clone (Scout + Shooter)
                </li>
                <li className="flex items-center gap-2">
                  <IconCheck size={15} className="text-indigo-600 dark:text-indigo-400" /> 50 Comment / ngày
                </li>
                <li className="flex items-center gap-2">
                  <IconCheck size={15} className="text-indigo-600 dark:text-indigo-400" /> Tự động Bump bài viết theo lịch
                </li>
                <li className="flex items-center gap-2">
                  <IconCheck size={15} className="text-indigo-600 dark:text-indigo-400" /> AI Filter & Comment Contextual
                </li>
                <li className="flex items-center gap-2">
                  <IconCheck size={15} className="text-indigo-600 dark:text-indigo-400" /> Hỗ trợ Proxy Pool tích hợp
                </li>
              </ul>
              <Link href="/register" className="mt-8 block">
                <Button className="w-full shadow-md shadow-indigo-500/25">
                  Đăng ký gói Pro
                </Button>
              </Link>
            </div>

            {/* Studio Plan */}
            <div className="rounded-2xl border border-slate-200/90 bg-white p-7 shadow-xs dark:border-slate-800 dark:bg-slate-900">
              <h3 className="text-lg font-bold text-slate-900 dark:text-white">Gói Studio</h3>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Dành cho agency & doanh nghiệp lớn</p>
              <div className="mt-6 flex items-baseline gap-1">
                <span className="text-3xl font-extrabold text-slate-900 dark:text-white">799.000đ</span>
                <span className="text-xs text-slate-400">/tháng</span>
              </div>
              <ul className="mt-6 space-y-3 text-xs text-slate-600 dark:text-slate-300">
                <li className="flex items-center gap-2">
                  <IconCheck size={15} className="text-emerald-500" /> Không giới hạn Facebook Group
                </li>
                <li className="flex items-center gap-2">
                  <IconCheck size={15} className="text-emerald-500" /> 10 Tài khoản Clone đa vai trò
                </li>
                <li className="flex items-center gap-2">
                  <IconCheck size={15} className="text-emerald-500" /> 150 Comment / ngày
                </li>
                <li className="flex items-center gap-2">
                  <IconCheck size={15} className="text-emerald-500" /> Đầy đủ tính năng Đăng bài Seeding
                </li>
                <li className="flex items-center gap-2">
                  <IconCheck size={15} className="text-emerald-500" /> Dedicated Proxy & Hỗ trợ ưu tiên 1-1
                </li>
              </ul>
              <Link href="/register" className="mt-8 block">
                <Button variant="ghost" className="w-full">
                  Chọn gói Studio
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ── FAQ SECTION ───────────────────────────────────────────────── */}
      <section id="faq" className="py-20">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
          <div className="text-center">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-indigo-600 dark:text-indigo-400">
              Giải đáp thắc mắc
            </h2>
            <p className="mt-2 text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl dark:text-white">
              Câu hỏi thường gặp
            </p>
          </div>

          <div className="mt-12 space-y-6">
            <div className="rounded-xl border border-slate-200/80 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
              <h4 className="text-sm font-bold text-slate-900 dark:text-white">
                Tài khoản Facebook của tôi có bị khóa khi dùng không?
              </h4>
              <p className="mt-2 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                Hệ thống chạy qua Chrome thật với hồ sơ và vân tay cố định, mô phỏng hành vi gõ phím của người thật, tuân thủ nghiêm ngặt thời gian nghỉ ngơi và giới hạn tần suất. Đồng thời công cụ tách biệt nick quét bài và nick comment nên độ an toàn luôn ở mức tối đa.
              </p>
            </div>

            <div className="rounded-xl border border-slate-200/80 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
              <h4 className="text-sm font-bold text-slate-900 dark:text-white">
                Tôi có cần máy tính luôn mở để tool chạy không?
              </h4>
              <p className="mt-2 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                Không. Hệ thống CommHunter AI chạy trên nền tảng máy chủ đám mây, tự động theo dõi 24/7. Bạn chỉ cần điện thoại có cài ứng dụng Telegram để nhận bài và duyệt lệnh.
              </p>
            </div>

            <div className="rounded-xl border border-slate-200/80 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
              <h4 className="text-sm font-bold text-slate-900 dark:text-white">
                Làm thế nào để lấy cookie Facebook để nạp vào tool?
              </h4>
              <p className="mt-2 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                Trong trang quản trị và luồng Onboarding có hướng dẫn chi tiết từng bước xuất file cookie bằng tiện ích Cookie-Editor miễn phí trên trình duyệt máy tính chỉ trong 30 giây.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── FOOTER & FINAL CTA ────────────────────────────────────────── */}
      <footer className="border-t border-slate-200/80 bg-white py-12 dark:border-slate-800/80 dark:bg-slate-950">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 text-center">
          <h3 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            Bắt đầu tự động hóa săn khách ngay hôm nay
          </h3>
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
            Tiết kiệm hàng chục giờ mỗi tuần, không bỏ lỡ bất kỳ bài đăng tiềm năng nào trên Facebook.
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Link href={isLoggedIn ? "/dashboard" : "/register"}>
              <Button size="md" icon={<IconArrowRight size={16} />}>
                {isLoggedIn ? "Vào Dashboard" : "Tạo tài khoản miễn phí"}
              </Button>
            </Link>
          </div>
          <div className="mt-12 border-t border-slate-100 pt-6 text-xs text-slate-400 dark:border-slate-800">
            &copy; 2026 CommHunter AI. Nền tảng tự động hóa tìm khách hàng và ứng tuyển Facebook Groups.
          </div>
        </div>
      </footer>
    </div>
  );
}
