"use client";
/**
 * Bộ thành phần giao diện CommHunter AI — Thiết kế hiện đại, mượt mà, chuẩn SaaS.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  IconAlertCircle,
  IconAlertTriangle,
  IconCheck,
  IconInfo,
  IconRefresh,
  IconX,
} from "./icons";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

// ── TOAST NOTIFICATIONS SYSTEM ──────────────────────────────────────────────
interface Toast {
  id: string;
  type: "success" | "error" | "info" | "warning";
  message: string;
  title?: string;
}

interface ToastContextType {
  toast: {
    success: (message: string, title?: string) => void;
    error: (message: string, title?: string) => void;
    info: (message: string, title?: string) => void;
    warning: (message: string, title?: string) => void;
  };
}

const ToastContext = createContext<ToastContextType | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback(
    (type: Toast["type"], message: string, title?: string) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      setToasts((prev) => [...prev, { id, type, message, title }]);
      setTimeout(() => {
        removeToast(id);
      }, 4000);
    },
    [removeToast],
  );

  const toastMethods = useMemo(
    () => ({
      success: (msg: string, title?: string) => addToast("success", msg, title),
      error: (msg: string, title?: string) => addToast("error", msg, title),
      info: (msg: string, title?: string) => addToast("info", msg, title),
      warning: (msg: string, title?: string) => addToast("warning", msg, title),
    }),
    [addToast],
  );

  return (
    <ToastContext.Provider value={{ toast: toastMethods }}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed bottom-5 right-5 z-50 flex max-w-sm flex-col gap-2.5 sm:max-w-md"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cx(
              "pointer-events-auto flex items-start gap-3 rounded-xl border p-3.5 shadow-lg backdrop-blur-md transition-all duration-300",
              t.type === "success" &&
                "border-emerald-500/30 bg-white/95 text-emerald-950 dark:bg-slate-900/95 dark:text-emerald-200",
              t.type === "error" &&
                "border-rose-500/30 bg-white/95 text-rose-950 dark:bg-slate-900/95 dark:text-rose-200",
              t.type === "warning" &&
                "border-amber-500/30 bg-white/95 text-amber-950 dark:bg-slate-900/95 dark:text-amber-200",
              t.type === "info" &&
                "border-sky-500/30 bg-white/95 text-sky-950 dark:bg-slate-900/95 dark:text-sky-200",
            )}
          >
            <div className="mt-0.5 shrink-0">
              {t.type === "success" && <IconCheck size={18} className="text-emerald-500" />}
              {t.type === "error" && <IconAlertCircle size={18} className="text-rose-500" />}
              {t.type === "warning" && <IconAlertTriangle size={18} className="text-amber-500" />}
              {t.type === "info" && <IconInfo size={18} className="text-sky-500" />}
            </div>
            <div className="flex-1 text-sm">
              {t.title && <p className="font-semibold">{t.title}</p>}
              <p className={cx("leading-snug", !t.title && "font-medium")}>{t.message}</p>
            </div>
            <button
              onClick={() => removeToast(t.id)}
              className="shrink-0 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
              aria-label="Đóng"
            >
              <IconX size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // Fallback nếu render ngoài provider
    return {
      success: (msg: string) => console.log("[Toast Success]", msg),
      error: (msg: string) => console.error("[Toast Error]", msg),
      info: (msg: string) => console.info("[Toast Info]", msg),
      warning: (msg: string) => console.warn("[Toast Warning]", msg),
    };
  }
  return ctx.toast;
}

// ── CARD ────────────────────────────────────────────────────────────────────
export function Card({
  title,
  action,
  children,
  className,
  headerClassName,
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  headerClassName?: string;
}) {
  return (
    <section
      className={cx(
        "rounded-2xl border border-slate-200/80 bg-white/90 shadow-xs backdrop-blur-xs transition-all duration-200",
        "dark:border-slate-800/80 dark:bg-slate-900/90 dark:shadow-none",
        className,
      )}
    >
      {(title || action) && (
        <header
          className={cx(
            "flex items-center justify-between gap-3 border-b border-slate-200/70 px-5 py-3.5 dark:border-slate-800/70",
            headerClassName,
          )}
        >
          <div className="text-sm font-semibold tracking-tight text-slate-900 dark:text-slate-100">
            {title}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

// ── STAT CARD ───────────────────────────────────────────────────────────────
export function Stat({
  label,
  value,
  hint,
  tone = "default",
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "good" | "warn" | "bad";
  icon?: ReactNode;
}) {
  const tones = {
    default: "text-slate-900 dark:text-slate-50",
    good: "text-emerald-600 dark:text-emerald-400",
    warn: "text-amber-600 dark:text-amber-400",
    bad: "text-rose-600 dark:text-rose-400",
  };

  const badgeBg = {
    default: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
    good: "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-400",
    warn: "bg-amber-50 text-amber-600 dark:bg-amber-950/60 dark:text-amber-400",
    bad: "bg-rose-50 text-rose-600 dark:bg-rose-950/60 dark:text-rose-400",
  };

  return (
    <div className="relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs transition-all duration-200 hover:border-slate-300 hover:shadow-sm dark:border-slate-800/80 dark:bg-slate-900/90 dark:hover:border-slate-700">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          {label}
        </p>
        {icon && (
          <div className={cx("flex h-8 w-8 items-center justify-center rounded-xl", badgeBg[tone])}>
            {icon}
          </div>
        )}
      </div>
      <p className={cx("mt-2 text-2xl font-bold tracking-tight tabular-nums sm:text-3xl", tones[tone])}>
        {value}
      </p>
      {hint && <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
    </div>
  );
}

// ── BADGE ───────────────────────────────────────────────────────────────────
const BADGE_TONES: Record<string, string> = {
  // Trạng thái clone
  active: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/80 dark:text-emerald-300 border-emerald-300/50 dark:border-emerald-800/50",
  warming_up: "bg-sky-100 text-sky-800 dark:bg-sky-950/80 dark:text-sky-300 border-sky-300/50 dark:border-sky-800/50",
  onboarding: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border-slate-300/50 dark:border-slate-700/50",
  cooldown: "bg-amber-100 text-amber-800 dark:bg-amber-950/80 dark:text-amber-300 border-amber-300/50 dark:border-amber-800/50",
  checkpoint: "bg-orange-100 text-orange-800 dark:bg-orange-950/80 dark:text-orange-300 border-orange-300/50 dark:border-orange-800/50",
  shadowbanned: "bg-purple-100 text-purple-800 dark:bg-purple-950/80 dark:text-purple-300 border-purple-300/50 dark:border-purple-800/50",
  banned: "bg-rose-100 text-rose-800 dark:bg-rose-950/80 dark:text-rose-300 border-rose-300/50 dark:border-rose-800/50",
  // Trạng thái bài viết / comment
  new: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border-slate-300/50 dark:border-slate-700/50",
  analyzing: "bg-sky-100 text-sky-800 dark:bg-sky-950/80 dark:text-sky-300 border-sky-300/50 dark:border-sky-800/50",
  matched: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950/80 dark:text-indigo-300 border-indigo-300/50 dark:border-indigo-800/50",
  notified: "bg-blue-100 text-blue-800 dark:bg-blue-950/80 dark:text-blue-300 border-blue-300/50 dark:border-blue-800/50",
  queued: "bg-blue-100 text-blue-800 dark:bg-blue-950/80 dark:text-blue-300 border-blue-300/50 dark:border-blue-800/50",
  in_progress: "bg-sky-100 text-sky-800 dark:bg-sky-950/80 dark:text-sky-300 border-sky-300/50 dark:border-sky-800/50",
  commented: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/80 dark:text-emerald-300 border-emerald-300/50 dark:border-emerald-800/50",
  success: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/80 dark:text-emerald-300 border-emerald-300/50 dark:border-emerald-800/50",
  skipped: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 border-slate-300/50 dark:border-slate-700/50",
  failed: "bg-rose-100 text-rose-800 dark:bg-rose-950/80 dark:text-rose-300 border-rose-300/50 dark:border-rose-800/50",
  // Proxy / group
  available: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/80 dark:text-emerald-300 border-emerald-300/50 dark:border-emerald-800/50",
  assigned: "bg-blue-100 text-blue-800 dark:bg-blue-950/80 dark:text-blue-300 border-blue-300/50 dark:border-blue-800/50",
  blacklisted: "bg-rose-100 text-rose-800 dark:bg-rose-950/80 dark:text-rose-300 border-rose-300/50 dark:border-rose-800/50",
  paused: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 border-slate-300/50 dark:border-slate-700/50",
  blocked: "bg-rose-100 text-rose-800 dark:bg-rose-950/80 dark:text-rose-300 border-rose-300/50 dark:border-rose-800/50",
  pending_join: "bg-amber-100 text-amber-800 dark:bg-amber-950/80 dark:text-amber-300 border-amber-300/50 dark:border-amber-800/50",
  // Roles
  scout: "bg-cyan-100 text-cyan-800 dark:bg-cyan-950/80 dark:text-cyan-300 border-cyan-300/50 dark:border-cyan-800/50",
  shooter: "bg-violet-100 text-violet-800 dark:bg-violet-950/80 dark:text-violet-300 border-violet-300/50 dark:border-violet-800/50",
  poster: "bg-amber-100 text-amber-800 dark:bg-amber-950/80 dark:text-amber-300 border-amber-300/50 dark:border-amber-800/50",
  both: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950/80 dark:text-indigo-300 border-indigo-300/50 dark:border-indigo-800/50",
  all: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/80 dark:text-emerald-300 border-emerald-300/50 dark:border-emerald-800/50",
  // Publishing
  draft: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border-slate-300/50 dark:border-slate-700/50",
  scheduled: "bg-blue-100 text-blue-800 dark:bg-blue-950/80 dark:text-blue-300 border-blue-300/50 dark:border-blue-800/50",
  publishing: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950/80 dark:text-indigo-300 border-indigo-300/50 dark:border-indigo-800/50",
  published: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/80 dark:text-emerald-300 border-emerald-300/50 dark:border-emerald-800/50",
  partially_published: "bg-amber-100 text-amber-800 dark:bg-amber-950/80 dark:text-amber-300 border-amber-300/50 dark:border-amber-800/50",
};

export const VI_LABEL: Record<string, string> = {
  onboarding: "Chờ cookie",
  warming_up: "Đang ủ ấm",
  active: "Đang chạy",
  cooldown: "Đang nghỉ",
  checkpoint: "Dính checkpoint",
  shadowbanned: "Nghi shadowban",
  banned: "Bị khóa",
  new: "Mới",
  read: "Đã đọc",
  archived: "Đã lưu trữ",
  analyzing: "Đang lọc",
  matched: "Phù hợp",
  notified: "Đã báo",
  queued: "Trong hàng đợi",
  in_progress: "Đang xử lý",
  commented: "Đã comment",
  success: "Thành công",
  skipped: "Bỏ qua",
  failed: "Thất bại",
  available: "Rảnh",
  assigned: "Đang dùng",
  blacklisted: "Đã loại",
  paused: "Tạm dừng",
  blocked: "Bị chặn",
  pending_join: "Chờ duyệt",
  semi_auto: "Bán tự động",
  full_auto: "Tự động hoàn toàn",
  scout: "Quét bài",
  shooter: "Cmt bài",
  poster: "Đăng bài",
  both: "Quét & Cmt",
  all: "Đa nhiệm",
  draft: "Bản nháp",
  scheduled: "Lên lịch",
  publishing: "Đang đăng",
  published: "Đã đăng",
  partially_published: "Đăng 1 phần",
};

export function Badge({
  value,
  children,
  dot,
}: {
  value: string;
  children?: ReactNode;
  dot?: boolean;
}) {
  const isPulsing = ["active", "warming_up", "in_progress", "analyzing"].includes(value);

  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold tracking-wide",
        BADGE_TONES[value] ??
          "border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300",
      )}
    >
      {(dot ?? isPulsing) && (
        <span className="relative flex h-1.5 w-1.5">
          {isPulsing && (
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-75" />
          )}
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
        </span>
      )}
      {children ?? VI_LABEL[value] ?? value}
    </span>
  );
}

// ── BUTTON ──────────────────────────────────────────────────────────────────
type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger" | "subtle" | "outline";
  size?: "xs" | "sm" | "md" | "lg";
  loading?: boolean;
  icon?: ReactNode;
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  const variants = {
    primary:
      "bg-slate-900 text-white shadow-xs hover:bg-slate-800 active:scale-[0.98] dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white",
    ghost:
      "border border-slate-300/80 text-slate-700 hover:bg-slate-100 active:scale-[0.98] dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800",
    subtle:
      "bg-slate-100 text-slate-700 hover:bg-slate-200 active:scale-[0.98] dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700",
    outline:
      "border border-indigo-500/40 text-indigo-600 hover:bg-indigo-50 active:scale-[0.98] dark:border-indigo-400/40 dark:text-indigo-400 dark:hover:bg-indigo-950/40",
    danger:
      "bg-rose-600 text-white shadow-xs hover:bg-rose-500 active:scale-[0.98] dark:bg-rose-700 dark:hover:bg-rose-600",
  };

  const sizes = {
    xs: "px-2 py-0.5 text-xs rounded-md gap-1",
    sm: "px-3 py-1.5 text-xs rounded-lg gap-1.5",
    md: "px-4 py-2 text-sm rounded-xl gap-2",
    lg: "px-5 py-2.5 text-base rounded-xl gap-2.5",
  };

  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cx(
        "inline-flex cursor-pointer items-center justify-center font-medium transition-all duration-150 disabled:cursor-not-allowed disabled:opacity-50",
        sizes[size],
        variants[variant],
        className,
      )}
    >
      {loading ? (
        <IconRefresh size={size === "xs" || size === "sm" ? 14 : 16} className="animate-spin" />
      ) : (
        icon
      )}
      {children}
    </button>
  );
}

// ── FORM CONTROLS ───────────────────────────────────────────────────────────
export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cx("block", className)}>
      <span className="mb-1.5 block text-xs font-semibold tracking-wide text-slate-700 dark:text-slate-300">
        {label}
      </span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500 dark:text-slate-400">{hint}</span>}
    </label>
  );
}

const CONTROL =
  "w-full rounded-xl border border-slate-300/90 bg-white px-3.5 py-2 text-sm text-slate-900 outline-none transition-all placeholder:text-slate-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-700/80 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-600 dark:focus:border-indigo-400 dark:focus:ring-indigo-400/20";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(CONTROL, props.className)} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx(CONTROL, "min-h-24 leading-relaxed", props.className)} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cx(CONTROL, "cursor-pointer", props.className)} />;
}

// ── MODAL ───────────────────────────────────────────────────────────────────
export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
  maxWidth = "max-w-2xl",
}: {
  open: boolean;
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  maxWidth?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-slate-950/60 p-4 backdrop-blur-sm">
      <div
        className="fixed inset-0"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className={cx(
          "relative z-10 w-full overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-2xl transition-all dark:border-slate-800 dark:bg-slate-900",
          maxWidth,
        )}
      >
        <header className="flex items-center justify-between border-b border-slate-200/80 px-6 py-4 dark:border-slate-800">
          <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            aria-label="Đóng"
          >
            <IconX size={16} />
          </button>
        </header>
        <div className="max-h-[70vh] space-y-4 overflow-y-auto p-6">{children}</div>
        {footer && (
          <footer className="flex justify-end gap-2.5 border-t border-slate-200/80 bg-slate-50/50 px-6 py-3.5 dark:border-slate-800 dark:bg-slate-900/50">
            {footer}
          </footer>
        )}
      </div>
    </div>
  );
}

// ── EMPTY STATE ─────────────────────────────────────────────────────────────
export function Empty({
  children,
  icon,
  action,
}: {
  children: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300/90 bg-slate-50/50 px-6 py-12 text-center dark:border-slate-800 dark:bg-slate-900/40">
      {icon && (
        <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-slate-400 shadow-xs dark:bg-slate-800 dark:text-slate-500">
          {icon}
        </div>
      )}
      <div className="max-w-sm text-sm text-slate-500 dark:text-slate-400">{children}</div>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

// ── SKELETON & SPINNER ──────────────────────────────────────────────────────
export function Spinner({ label = "Đang tải dữ liệu…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-slate-400">
      <IconRefresh size={24} className="animate-spin text-indigo-500" />
      <p className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">{label}</p>
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={cx(
        "skeleton-shimmer rounded-xl bg-slate-200/70 dark:bg-slate-800/70",
        className,
      )}
    />
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  if (!children) return null;
  return (
    <div className="flex items-start gap-2.5 rounded-xl border border-rose-200 bg-rose-50/80 p-3.5 text-sm text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-300">
      <IconAlertCircle size={18} className="shrink-0 text-rose-500" />
      <div className="flex-1 leading-relaxed">{children}</div>
    </div>
  );
}

export function Progress({
  percent,
  label,
  tone = "primary",
}: {
  percent: number;
  label?: string;
  tone?: "primary" | "emerald" | "amber" | "rose";
}) {
  const value = Math.max(0, Math.min(100, percent));
  const toneClasses = {
    primary: "bg-indigo-600 dark:bg-indigo-500",
    emerald: "bg-emerald-500 dark:bg-emerald-400",
    amber: "bg-amber-500 dark:bg-amber-400",
    rose: "bg-rose-500 dark:bg-rose-400",
  };

  return (
    <div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
        <div
          className={cx("h-full rounded-full transition-all duration-300", toneClasses[tone])}
          style={{ width: `${value}%` }}
        />
      </div>
      {label && <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">{label}</p>}
    </div>
  );
}

// ── BAR CHART CÓ TOOLTIP TƯƠNG TÁC ──────────────────────────────────────────
export function BarChart({
  data,
  height = 160,
}: {
  data: { label: string; values: { value: number; color: string; name: string }[] }[];
  height?: number;
}) {
  const [activeIdx, setActiveIdx] = useState<number | null>(null);
  const max = Math.max(1, ...data.flatMap((d) => d.values.map((v) => v.value)));

  return (
    <div className="relative pt-6">
      <div className="flex items-end gap-2.5" style={{ height }}>
        {data.map((column, idx) => {
          const isHovered = activeIdx === idx;
          return (
            <div
              key={column.label}
              className="relative flex flex-1 flex-col items-center gap-2 group cursor-pointer"
              onMouseEnter={() => setActiveIdx(idx)}
              onMouseLeave={() => setActiveIdx(null)}
            >
              {/* Tooltip khi hover */}
              {isHovered && (
                <div className="pointer-events-none absolute -top-16 z-20 whitespace-nowrap rounded-xl border border-slate-200 bg-white/95 px-2.5 py-1.5 text-xs shadow-xl backdrop-blur-md dark:border-slate-800 dark:bg-slate-900/95">
                  <p className="font-semibold text-slate-900 dark:text-slate-100">{column.label}</p>
                  <div className="flex items-center gap-2 mt-0.5 text-[11px]">
                    {column.values.map((bar) => (
                      <span key={bar.name} className="flex items-center gap-1">
                        <span className={cx("inline-block h-2 w-2 rounded-full", bar.color)} />
                        {bar.name}: <b className="tabular-nums">{bar.value}</b>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex h-full w-full items-end justify-center gap-1">
                {column.values.map((bar) => (
                  <div
                    key={bar.name}
                    className={cx(
                      "w-full rounded-t-md transition-all duration-200",
                      bar.color,
                      isHovered ? "opacity-100 scale-x-105" : "opacity-85 group-hover:opacity-95",
                    )}
                    style={{
                      height: `${(bar.value / max) * 100}%`,
                      minHeight: bar.value > 0 ? 4 : 1,
                    }}
                  />
                ))}
              </div>
              <span
                className={cx(
                  "text-[11px] tabular-nums transition-colors",
                  isHovered ? "font-semibold text-slate-900 dark:text-slate-100" : "text-slate-400",
                )}
              >
                {column.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── HOOK ASYNC DÙNG CHUNG ───────────────────────────────────────────────────
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    loader()
      .then((result) => alive && (setData(result), setError("")))
      .catch((err) => alive && setError(err?.message ?? "Lỗi không xác định"))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return { data, error, loading, reload: () => setNonce((n) => n + 1), setData };
}

export const fmtDate = (value?: string | null) =>
  value
    ? new Date(value).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" })
    : "—";

export const fmtVnd = (value: number) => `${value.toLocaleString("vi-VN")}đ`;
