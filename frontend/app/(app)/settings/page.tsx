"use client";
import { useState } from "react";

import {
  IconCheck,
  IconCopy,
  IconExternalLink,
  IconLogout,
  IconSettings,
  IconTelegram,
  IconUsers,
} from "@/components/icons";
import {
  Badge,
  Button,
  Card,
  ErrorNote,
  Field,
  Input,
  fmtDate,
  useToast,
} from "@/components/ui";
import { API_URL, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function SettingsPage() {
  const { user, refreshUser, logout } = useAuth();
  const toast = useToast();
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [linkCode, setLinkCode] = useState<{ link_code: string; instructions: string } | null>(null);

  async function save() {
    setError("");
    setSaving(true);
    try {
      await api.updateMe({ display_name: displayName });
      await refreshUser();
      toast.success("Đã cập nhật hồ sơ thành công!", "Thành công");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lưu thất bại");
    } finally {
      setSaving(false);
    }
  }

  async function connectTelegram() {
    setError("");
    try {
      const res = await api.connectTelegram();
      setLinkCode(res);
      toast.info("Đã tạo mã liên kết bot Telegram");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tạo được mã liên kết");
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
              <IconSettings size={18} />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-2xl">
              Cài đặt Hệ thống
            </h1>
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Quản lý hồ sơ cá nhân, liên kết bot Telegram để duyệt lead bán tự động và thông tin kết nối API.
          </p>
        </div>
      </header>

      <ErrorNote>{error}</ErrorNote>

      {/* ── PROFILE CARD ────────────────────────────────────────────────── */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <IconUsers size={17} className="text-indigo-500" />
            <span>Thông tin tài khoản</span>
          </div>
        }
        action={
          <Button size="sm" onClick={save} loading={saving} disabled={saving}>
            Lưu thay đổi
          </Button>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Địa chỉ Email (Đăng nhập)">
            <Input value={user?.email ?? ""} disabled className="opacity-75 cursor-not-allowed" />
          </Field>
          <Field label="Tên hiển thị">
            <Input
              value={displayName}
              placeholder="Nhập họ tên của bạn…"
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </Field>
          <Field label="Ngày tham gia">
            <Input
              value={fmtDate(user?.created_at)}
              disabled
              className="opacity-75 cursor-not-allowed"
            />
          </Field>
          <Field label="Gói cước đang kích hoạt">
            <div className="flex items-center gap-2 pt-1">
              <Badge value={user?.subscription?.plan ?? "starter"} />
              <span className="text-xs text-slate-500">
                (Tối đa {user?.subscription?.max_comments_per_day ?? 20} comment/ngày)
              </span>
            </div>
          </Field>
        </div>
      </Card>

      {/* ── TELEGRAM BOT CARD ───────────────────────────────────────────── */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <IconTelegram size={18} className="text-sky-500" />
            <span>Liên kết Bot Telegram (Bán tự động)</span>
          </div>
        }
        action={
          <Button size="sm" variant="ghost" onClick={connectTelegram}>
            {user?.telegram_chat_id ? "Tạo mã kết nối mới" : "Kết nối ngay"}
          </Button>
        }
      >
        {user?.telegram_chat_id ? (
          <div className="rounded-xl border border-emerald-200/80 bg-emerald-50/70 p-4 text-xs text-emerald-950 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300">
            <p className="font-semibold text-sm mb-1">✓ Đã kết nối thành công!</p>
            <p className="leading-relaxed">
              Tài khoản của bạn đã được ghép nối với Telegram Chat ID: <b>{user.telegram_chat_id}</b>.
              Mỗi khi hệ thống Scout tìm thấy lead bài viết mới, bot sẽ gửi thông báo kèm các nút bấm
              <i> Duyệt nhanh / Xem trước / Bỏ qua</i> trực tiếp trên điện thoại của bạn.
            </p>
          </div>
        ) : (
          <div className="rounded-xl border border-slate-200/80 bg-slate-50/60 p-4 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-800/40 dark:text-slate-300">
            <p className="font-semibold text-slate-800 dark:text-slate-200 mb-1">Chưa liên kết Telegram</p>
            <p className="leading-relaxed">
              Ở chế độ Bán Tự Động, liên kết Telegram giúp bạn nhận thông báo và duyệt ứng tuyển khách hàng tiềm năng mọi lúc mọi nơi mà không cần mở máy tính liên tục.
            </p>
          </div>
        )}

        {linkCode && (
          <div className="mt-4 rounded-2xl border border-sky-200 bg-sky-50/80 p-5 dark:border-sky-900/60 dark:bg-sky-950/40">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-sky-950 dark:text-sky-300 uppercase tracking-wide">
                Lệnh liên kết nhanh
              </span>
              <button
                type="button"
                onClick={() => copyText(`/start ${linkCode.link_code}`, "lệnh Telegram")}
                className="inline-flex items-center gap-1 text-xs font-semibold text-sky-700 hover:text-sky-800 dark:text-sky-400"
              >
                <IconCopy size={13} />
                Sao chép lệnh
              </button>
            </div>

            <div className="mt-2 rounded-xl bg-white p-3 font-mono text-base font-bold text-slate-900 shadow-xs dark:bg-slate-900 dark:text-white">
              /start {linkCode.link_code}
            </div>

            <p className="mt-3 text-xs text-sky-900/80 dark:text-sky-300 leading-relaxed">
              {linkCode.instructions}
            </p>
          </div>
        )}
      </Card>

      {/* ── SYSTEM INFO & LOGOUT ────────────────────────────────────────── */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <IconSettings size={17} className="text-slate-500" />
            <span>Thông số kết nối hệ thống</span>
          </div>
        }
      >
        <dl className="grid gap-3 sm:grid-cols-2 text-xs">
          <div className="flex items-center justify-between rounded-xl bg-slate-50/80 p-3 dark:bg-slate-800/40">
            <dt className="text-slate-500">Địa chỉ Backend API</dt>
            <dd className="font-mono font-semibold text-slate-800 dark:text-slate-200">{API_URL}</dd>
          </div>
          <div className="flex items-center justify-between rounded-xl bg-slate-50/80 p-3 dark:bg-slate-800/40">
            <dt className="text-slate-500">Mã định danh User ID</dt>
            <dd className="font-mono text-slate-600 dark:text-slate-400 text-[11px] truncate max-w-[160px]">
              {user?.id}
            </dd>
          </div>
        </dl>

        <div className="mt-6 flex justify-end border-t border-slate-100 pt-4 dark:border-slate-800">
          <Button
            variant="danger"
            size="sm"
            onClick={logout}
            icon={<IconLogout size={14} />}
          >
            Đăng xuất phiên làm việc
          </Button>
        </div>
      </Card>
    </div>
  );
}
