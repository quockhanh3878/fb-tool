"use client";
import { useState } from "react";

import {
  IconCheck,
  IconCopy,
  IconCreditCard,
  IconFacebook,
  IconShieldCheck,
  IconSparkles,
  IconUsers,
  IconX,
  IconZap,
} from "@/components/icons";
import {
  Badge,
  Button,
  Card,
  ErrorNote,
  Modal,
  Progress,
  Spinner,
  Stat,
  cx,
  fmtDate,
  fmtVnd,
  useAsync,
  useToast,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { PaymentIntent } from "@/lib/types";

export default function BillingPage() {
  const { user, refreshUser } = useAuth();
  const toast = useToast();
  const plans = useAsync(() => api.plans());
  const usage = useAsync(() => api.usage());
  const [intent, setIntent] = useState<PaymentIntent | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const currentPlan = user?.subscription?.plan ?? "starter";

  async function startSubscribe(plan: string) {
    setError("");
    try {
      setIntent(await api.subscribe(plan, 1));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tạo được yêu cầu thanh toán");
    }
  }

  async function confirm() {
    if (!intent) return;
    setBusy(true);
    setError("");
    try {
      await api.confirmPayment(intent.plan, intent.months);
      setIntent(null);
      await refreshUser();
      usage.reload();
      toast.success("Kích hoạt gói cước thành công! Cảm ơn bạn.", "Thành công");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kích hoạt thất bại");
    } finally {
      setBusy(false);
    }
  }

  function copyText(text: string, label: string) {
    navigator.clipboard.writeText(text);
    toast.info(`Đã sao chép ${label} vào bộ nhớ tạm`);
  }

  return (
    <div className="space-y-6">
      {/* ── HEADER ─────────────────────────────────────────────────────── */}
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
              <IconCreditCard size={18} />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-2xl">
              Gói dịch vụ & Hạn mức
            </h1>
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Hạn mức số lượng group theo dõi, tài khoản clone và trần comment mỗi ngày phụ thuộc vào gói cước của bạn.
          </p>
        </div>
      </header>

      <ErrorNote>{error}</ErrorNote>

      {usage.loading && <Spinner label="Đang kiểm tra thông tin gói cước…" />}

      {/* ── CURRENT PLAN STATS ──────────────────────────────────────────── */}
      {usage.data && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Stat
            label="Gói hiện tại"
            value={usage.data.plan.toUpperCase()}
            hint={usage.data.is_active ? "Đang có hiệu lực" : "Đã hết hạn sử dụng"}
            tone={usage.data.is_active ? "good" : "bad"}
            icon={<IconSparkles size={18} />}
          />
          <Stat
            label="Ngày hết hạn"
            value={fmtDate(usage.data.expires_at)}
            hint={usage.data.is_active ? "Tự động cộng dồn khi gia hạn" : "Vui lòng gia hạn gói"}
            icon={<IconCreditCard size={18} />}
          />
          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs dark:border-slate-800 dark:bg-slate-900/90">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Group theo dõi
              </span>
              <IconFacebook size={16} className="text-blue-500" />
            </div>
            <p className="mt-2 text-2xl font-bold tracking-tight tabular-nums">
              {usage.data.groups_used}
              <span className="text-sm font-normal text-slate-400">/{usage.data.groups_limit}</span>
            </p>
            <div className="mt-3">
              <Progress
                percent={(usage.data.groups_used / Math.max(1, usage.data.groups_limit)) * 100}
                tone="primary"
              />
            </div>
          </div>
          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs dark:border-slate-800 dark:bg-slate-900/90">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Clone hoạt động
              </span>
              <IconUsers size={16} className="text-indigo-500" />
            </div>
            <p className="mt-2 text-2xl font-bold tracking-tight tabular-nums">
              {usage.data.clones_used}
              <span className="text-sm font-normal text-slate-400">/{usage.data.clones_limit}</span>
            </p>
            <div className="mt-3">
              <Progress
                percent={(usage.data.clones_used / Math.max(1, usage.data.clones_limit)) * 100}
                tone="emerald"
              />
            </div>
          </div>
        </div>
      )}

      {/* ── PRICING CARDS ──────────────────────────────────────────────── */}
      {plans.loading && <Spinner label="Đang tải bảng giá dịch vụ…" />}
      <div className="grid gap-6 md:grid-cols-3">
        {plans.data?.map((plan) => {
          const isCurrent = plan.plan === currentPlan;
          const isPro = plan.plan.toLowerCase().includes("pro") || plan.plan.toLowerCase().includes("chuyên");

          return (
            <div
              key={plan.plan}
              className={cx(
                "relative flex flex-col justify-between rounded-3xl border bg-white p-6 shadow-sm transition-all duration-200 dark:bg-slate-900",
                isPro
                  ? "border-indigo-500 shadow-indigo-500/10 shadow-lg ring-2 ring-indigo-500/20 dark:border-indigo-500"
                  : isCurrent
                    ? "border-slate-800 dark:border-slate-200"
                    : "border-slate-200/90 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700",
              )}
            >
              {isPro && (
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 rounded-full bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-0.5 text-[11px] font-bold text-white shadow-md">
                  ★ Phổ biến nhất
                </div>
              )}

              <div>
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                    {plan.display_name}
                  </h2>
                  {isCurrent && <Badge value="active">Đang sử dụng</Badge>}
                </div>

                <div className="mt-4 flex items-baseline gap-1">
                  <span className="text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
                    {fmtVnd(plan.price_vnd)}
                  </span>
                  <span className="text-xs text-slate-500">/tháng</span>
                </div>

                <ul className="mt-6 space-y-3 text-xs text-slate-600 dark:text-slate-300">
                  <li className="flex items-center gap-2.5">
                    <div className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400">
                      <IconCheck size={11} />
                    </div>
                    <span>
                      Tối đa <b>{plan.max_groups} group</b> Facebook cùng lúc
                    </span>
                  </li>
                  <li className="flex items-center gap-2.5">
                    <div className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400">
                      <IconCheck size={11} />
                    </div>
                    <span>
                      Quản lý <b>{plan.max_clones} tài khoản clone</b>
                    </span>
                  </li>
                  <li className="flex items-center gap-2.5">
                    <div className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400">
                      <IconCheck size={11} />
                    </div>
                    <span>
                      Giới hạn <b>{plan.max_comments_per_day} comment/ngày</b>
                    </span>
                  </li>
                  <li className="flex items-center gap-2.5">
                    {plan.ai_comments_enabled ? (
                      <div className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400">
                        <IconCheck size={11} />
                      </div>
                    ) : (
                      <div className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-400 dark:bg-slate-800">
                        <IconX size={11} />
                      </div>
                    )}
                    <span>Bình luận AI thông minh theo ngữ cảnh</span>
                  </li>
                  <li className="flex items-center gap-2.5">
                    {plan.bump_enabled ? (
                      <div className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400">
                        <IconCheck size={11} />
                      </div>
                    ) : (
                      <div className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-400 dark:bg-slate-800">
                        <IconX size={11} />
                      </div>
                    )}
                    <span>Tự động bump bài theo lịch hẹn</span>
                  </li>
                </ul>
              </div>

              <div className="mt-8">
                <Button
                  className="w-full"
                  variant={isPro ? "primary" : isCurrent ? "ghost" : "subtle"}
                  onClick={() => startSubscribe(plan.plan)}
                >
                  {isCurrent ? "Gia hạn gói này" : "Nâng cấp gói này"}
                </Button>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── PAYMENT MODAL ──────────────────────────────────────────────── */}
      <Modal
        open={!!intent}
        title={
          <div className="flex items-center gap-2">
            <IconCreditCard size={18} className="text-indigo-600" />
            <span>Thanh toán gói dịch vụ: {intent?.plan.toUpperCase()}</span>
          </div>
        }
        onClose={() => setIntent(null)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setIntent(null)}>
              Để sau
            </Button>
            <Button onClick={confirm} disabled={busy} loading={busy}>
              Tôi đã chuyển khoản
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="rounded-2xl border border-indigo-100 bg-indigo-50/60 p-4 dark:border-indigo-900/60 dark:bg-indigo-950/30">
            <div className="flex justify-between items-center text-sm">
              <span className="text-slate-600 dark:text-slate-400">Gói đăng ký:</span>
              <span className="font-bold text-slate-900 dark:text-white">
                {intent?.plan.toUpperCase()} ({intent?.months} tháng)
              </span>
            </div>
            <div className="mt-2 flex justify-between items-center text-sm">
              <span className="text-slate-600 dark:text-slate-400">Số tiền cần thanh toán:</span>
              <span className="text-xl font-extrabold text-indigo-600 dark:text-indigo-400">
                {fmtVnd(intent?.amount_vnd ?? 0)}
              </span>
            </div>
          </div>

          <div>
            <span className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Mã đối soát chuyển khoản (Bắt buộc ghi vào nội dung chuyển tiền):
            </span>
            <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 p-3 font-mono text-sm font-bold text-slate-900 dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-100">
              <span>{intent?.reference_code}</span>
              <button
                type="button"
                onClick={() => copyText(intent?.reference_code || "", "mã đối soát")}
                className="flex items-center gap-1 text-xs font-sans text-indigo-600 hover:text-indigo-700 dark:text-indigo-400"
              >
                <IconCopy size={14} />
                Sao chép
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200/80 bg-white p-3.5 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-300 leading-relaxed">
            <p className="font-semibold text-slate-800 dark:text-slate-200 mb-1">Hướng dẫn thanh toán:</p>
            <p>{intent?.instructions}</p>
            <p className="mt-2 text-slate-400 text-[11px]">
              * Thời gian còn lại của gói cũ sẽ được hệ thống tự động cộng dồn vào hạn mới.
            </p>
          </div>
        </div>
      </Modal>
    </div>
  );
}
