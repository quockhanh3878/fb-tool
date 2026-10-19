"use client";
import { useEffect, useState } from "react";

import {
  IconCheck,
  IconCopy,
  IconExternalLink,
  IconLogout,
  IconSettings,
  IconSparkles,
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
import type { AppSettings, NotificationRecipient } from "@/lib/types";

export default function SettingsPage() {
  const { user, refreshUser, logout } = useAuth();
  const toast = useToast();
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [linkCode, setLinkCode] = useState<{ link_code: string; instructions: string } | null>(null);

  // Chỉ tồn tại ở chế độ desktop (RUN_MODE=desktop) — SaaS trả 404, ẩn hẳn thẻ.
  const [appSettings, setAppSettings] = useState<AppSettings | null>(null);
  const [openaiKey, setOpenaiKey] = useState("");
  const [telegramToken, setTelegramToken] = useState("");
  const [discordWebhook, setDiscordWebhook] = useState("");
  const [discordBotToken, setDiscordBotToken] = useState("");
  const [savingAppSettings, setSavingAppSettings] = useState(false);
  const [recipients, setRecipients] = useState<NotificationRecipient[]>([]);
  const [recipientId, setRecipientId] = useState("");
  const [recipientName, setRecipientName] = useState("");
  const [recipientBusy, setRecipientBusy] = useState(false);
  const [discordTestBusy, setDiscordTestBusy] = useState(false);
  const [discordLinkCode, setDiscordLinkCode] = useState<{ code: string; expires_at: string } | null>(null);

  useEffect(() => {
    api
      .appSettings()
      .then(setAppSettings)
      .catch(() => setAppSettings(null));
    api.discordRecipients().then(setRecipients).catch(() => setRecipients([]));
  }, []);

  async function saveAppSettings() {
    setError("");
    setSavingAppSettings(true);
    try {
      const payload: { openai_api_key?: string; telegram_bot_token?: string; discord_webhook_url?: string; discord_bot_token?: string } = {};
      if (openaiKey.trim()) payload.openai_api_key = openaiKey.trim();
      if (telegramToken.trim()) payload.telegram_bot_token = telegramToken.trim();
      if (discordWebhook.trim()) payload.discord_webhook_url = discordWebhook.trim();
      if (discordBotToken.trim()) payload.discord_bot_token = discordBotToken.trim();
      const result = await api.updateAppSettings(payload);
      setAppSettings(result);
      setOpenaiKey("");
      setTelegramToken("");
      setDiscordWebhook("");
      setDiscordBotToken("");
      toast.success("Đã lưu cấu hình hệ thống", "Thành công");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lưu cấu hình thất bại");
    } finally {
      setSavingAppSettings(false);
    }
  }

  async function addRecipient() {
    if (!recipientId.trim()) return;
    setRecipientBusy(true);
    try {
      const recipient = await api.createDiscordRecipient({
        channel: "discord_webhook",
        recipient_id: recipientId.trim(),
        display_name: recipientName.trim(),
        event_types: ["lead", "customer_reply", "post_author_reply", "error"],
      });
      setRecipients((current) => [...current, recipient]);
      setRecipientId("");
      setRecipientName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thêm được người nhận");
    } finally {
      setRecipientBusy(false);
    }
  }

  async function removeRecipient(id: string) {
    try {
      await api.deleteDiscordRecipient(id);
      setRecipients((current) => current.filter((item) => item.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không xoá được người nhận");
    }
  }

  async function sendDiscordTest() {
    setDiscordTestBusy(true);
    try {
      await api.sendDiscordTest();
      toast.success("Đã gửi tin thử tới Discord", "Thành công");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gửi tin thử thất bại");
    } finally {
      setDiscordTestBusy(false);
    }
  }

  async function createDiscordCode() {
    try {
      setDiscordLinkCode(await api.createDiscordLinkCode());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tạo được mã Discord");
    }
  }

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

      {/* ── CẤU HÌNH HỆ THỐNG (CHỈ CHẾ ĐỘ DESKTOP) ────────────────────────── */}
      {appSettings && (
        <Card
          title={
            <div className="flex items-center gap-2">
              <IconSparkles size={17} className="text-amber-500" />
              <span>Cấu hình OpenAI, Telegram &amp; Discord</span>
            </div>
          }
          action={
            <div className="flex flex-wrap justify-end gap-2">
              <Button size="sm" variant="outline" onClick={sendDiscordTest} loading={discordTestBusy} disabled={discordTestBusy || !appSettings.discord_webhook_url_set}>
                Gửi thử Discord
              </Button>
              <Button size="sm" onClick={saveAppSettings} loading={savingAppSettings} disabled={savingAppSettings}>
                Lưu cấu hình
              </Button>
            </div>
          }
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label={`OpenAI API Key ${appSettings.openai_api_key_set ? "(đã cấu hình)" : "(chưa cấu hình)"}`}
            >
              <Input
                type="password"
                value={openaiKey}
                placeholder={appSettings.openai_api_key_set ? "••••••••••••••••" : "sk-..."}
                onChange={(e) => setOpenaiKey(e.target.value)}
              />
            </Field>
            <Field
              label={`Discord Webhook ${appSettings.discord_webhook_url_set ? "(đã cấu hình)" : "(chưa cấu hình)"}`}
            >
              <Input
                type="password"
                value={discordWebhook}
                placeholder={appSettings.discord_webhook_url_set ? "••••••••••••" : "https://discord.com/api/webhooks/..."}
                onChange={(e) => setDiscordWebhook(e.target.value)}
              />
            </Field>
            <Field
              label={`Discord Bot Token ${appSettings.discord_bot_token_set ? "(đã cấu hình)" : "(chưa cấu hình)"}`}
            >
              <Input
                type="password"
                value={discordBotToken}
                placeholder={appSettings.discord_bot_token_set ? "••••••••••••" : "Dán token bot Discord"}
                onChange={(e) => setDiscordBotToken(e.target.value)}
              />
            </Field>
            <Field
              label={`Telegram Bot Token ${appSettings.telegram_bot_token_set ? "(đã cấu hình)" : "(chưa cấu hình)"}`}
            >
              <Input
                type="password"
                value={telegramToken}
                placeholder={appSettings.telegram_bot_token_set ? "••••••••••••••••" : "123456:ABC-..."}
                onChange={(e) => setTelegramToken(e.target.value)}
              />
            </Field>
          </div>
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
            Để trống ô nào thì giữ nguyên giá trị đang lưu của ô đó. Áp dụng ngay không cần khởi động lại app.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Button size="sm" variant="ghost" onClick={createDiscordCode}>Tạo mã đăng ký bot Discord</Button>
            {discordLinkCode && <code className="rounded bg-slate-100 px-2 py-1 text-xs dark:bg-slate-800">{discordLinkCode.code}</code>}
            {discordLinkCode && <span className="text-xs text-slate-500">Hết hạn {fmtDate(discordLinkCode.expires_at)}</span>}
          </div>
        </Card>
      )}

      {appSettings && (
        <Card title="Người nhận cảnh báo Discord">
          <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
            <Input value={recipientName} placeholder="Tên hiển thị" onChange={(e) => setRecipientName(e.target.value)} />
            <Input value={recipientId} placeholder="Discord user ID" onChange={(e) => setRecipientId(e.target.value)} />
            <Button size="sm" onClick={addRecipient} loading={recipientBusy} disabled={!recipientId.trim()}>Thêm</Button>
          </div>
          <div className="mt-4 space-y-2">
            {!recipients.length && <p className="text-xs text-slate-500">Chưa có người nhận. Có thể dùng ID tay hoặc mã đăng ký bot Discord.</p>}
            {recipients.map((recipient) => (
              <div key={recipient.id} className="flex items-center justify-between rounded-xl border border-slate-200 p-3 text-xs dark:border-slate-800">
                <div>
                  <p className="font-semibold text-slate-800 dark:text-slate-200">{recipient.display_name || recipient.recipient_id}</p>
                  <p className="text-slate-500">{recipient.channel} · {recipient.source} · {recipient.is_active ? "Đang bật" : "Đã tắt"}</p>
                </div>
                <Button size="sm" variant="ghost" onClick={() => removeRecipient(recipient.id)}>Xoá</Button>
              </div>
            ))}
          </div>
        </Card>
      )}

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
