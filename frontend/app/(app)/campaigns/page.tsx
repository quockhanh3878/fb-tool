"use client";
import Link from "next/link";
import { useState } from "react";

import { TagInput } from "@/components/TagInput";
import {
  IconLayers,
  IconPause,
  IconPlay,
  IconPlus,
  IconSettings,
  IconSparkles,
  IconTrash,
  IconZap,
} from "@/components/icons";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorNote,
  Field,
  Input,
  Modal,
  Select,
  Spinner,
  Textarea,
  cx,
  fmtDate,
  useAsync,
  useToast,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { Campaign } from "@/lib/types";

const EMPTY = {
  name: "",
  mode: "semi_auto" as Campaign["mode"],
  service_name: "",
  service_specialties: "",
  ai_comments_enabled: false,
  ai_filter_prompt: "",
  whitelist_keywords: [] as string[],
  blacklist_keywords: [] as string[],
  max_comments_per_day: 20,
};

export default function CampaignsPage() {
  const { data, loading, error, reload } = useAsync(() => api.campaigns());
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");

  async function create() {
    setBusy(true);
    setFormError("");
    try {
      await api.createCampaign({
        ...form,
        max_comments_per_day: Number(form.max_comments_per_day),
      });
      setOpen(false);
      setForm(EMPTY);
      toast.success("Đã tạo chiến dịch thành công!", "Thành công");
      reload();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Không tạo được chiến dịch");
    } finally {
      setBusy(false);
    }
  }

  async function toggle(campaign: Campaign) {
    try {
      if (campaign.is_active) {
        await api.pauseCampaign(campaign.id);
        toast.info(`Đã tạm dừng chiến dịch "${campaign.name}"`);
      } else {
        await api.activateCampaign(campaign.id);
        toast.success(`Đã kích hoạt chiến dịch "${campaign.name}"`);
      }
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Thao tác thất bại");
    }
  }

  async function remove(campaign: Campaign) {
    if (!confirm(`Xóa chiến dịch "${campaign.name}"? Toàn bộ bài viết đã quét của chiến dịch này cũng sẽ bị xóa.`))
      return;
    try {
      await api.deleteCampaign(campaign.id);
      toast.info(`Đã xóa chiến dịch "${campaign.name}"`);
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Xóa thất bại");
    }
  }

  return (
    <div className="space-y-6">
      {/* ── HEADER ─────────────────────────────────────────────────────── */}
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
              <IconLayers size={18} />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-2xl">
              Quản lý Chiến dịch
            </h1>
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Mỗi chiến dịch tương ứng với một dịch vụ, kịch bản bình luận và danh sách nhóm Facebook riêng biệt.
          </p>
        </div>

        <Button onClick={() => setOpen(true)} icon={<IconPlus size={16} />}>
          Chiến dịch mới
        </Button>
      </header>

      <ErrorNote>{error}</ErrorNote>
      {loading && <Spinner label="Đang tải danh sách chiến dịch…" />}

      {!loading && !data?.length && (
        <Empty
          icon={<IconLayers size={24} />}
          action={
            <div className="flex flex-wrap justify-center gap-2.5">
              <Button onClick={() => setOpen(true)} icon={<IconPlus size={16} />}>
                Tạo chiến dịch mới
              </Button>
              <Link href="/onboarding">
                <Button variant="ghost" icon={<IconSparkles size={16} />}>
                  Chạy hướng dẫn 5 bước (Onboarding)
                </Button>
              </Link>
            </div>
          }
        >
          Chưa có chiến dịch nào hoạt động. Hãy tạo chiến dịch để hệ thống Scout bắt đầu quét và săn lead Facebook.
        </Empty>
      )}

      {/* ── CAMPAIGN CARDS GRID ─────────────────────────────────────────── */}
      <div className="grid gap-4 md:grid-cols-2">
        {data?.map((campaign) => (
          <div
            key={campaign.id}
            className="flex flex-col justify-between rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs transition-all duration-200 hover:border-slate-300 hover:shadow-sm dark:border-slate-800 dark:bg-slate-900/90 dark:hover:border-slate-700"
          >
            <div>
              <div className="flex items-start justify-between gap-2 border-b border-slate-100 pb-3 dark:border-slate-800">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">
                      {campaign.name}
                    </h2>
                    <Badge value={campaign.is_active ? "active" : "paused"} />
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                    {campaign.service_name || "Dịch vụ tự do"}
                  </p>
                </div>
                <Badge value={campaign.mode} />
              </div>

              <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
                <div className="rounded-xl bg-slate-50/80 p-2.5 dark:bg-slate-800/40">
                  <span className="text-slate-400">Ngưỡng lọc AI</span>
                  <p className="mt-1 font-bold text-slate-800 dark:text-slate-200 tabular-nums">
                    ≥ {campaign.min_relevance_score.toFixed(2)} điểm
                  </p>
                </div>
                <div className="rounded-xl bg-slate-50/80 p-2.5 dark:bg-slate-800/40">
                  <span className="text-slate-400">Giới hạn comment</span>
                  <p className="mt-1 font-bold text-slate-800 dark:text-slate-200 tabular-nums">
                    {campaign.max_comments_per_day} comment/ngày
                  </p>
                </div>
              </div>

              {campaign.service_specialties && (
                <div className="mt-3">
                  <span className="text-[11px] font-medium text-slate-400">Thế mạnh / Dịch vụ:</span>
                  <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-300 line-clamp-2">
                    {campaign.service_specialties}
                  </p>
                </div>
              )}
            </div>

            <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-3 dark:border-slate-800">
              <span className="text-[11px] text-slate-400">Tạo: {fmtDate(campaign.created_at)}</span>

              <div className="flex items-center gap-2">
                <Link href={`/campaigns/${campaign.id}`}>
                  <Button size="sm" variant="ghost" icon={<IconSettings size={14} />}>
                    Cấu hình
                  </Button>
                </Link>
                <Button
                  size="sm"
                  variant="subtle"
                  icon={campaign.is_active ? <IconPause size={14} /> : <IconPlay size={14} />}
                  onClick={() => toggle(campaign)}
                >
                  {campaign.is_active ? "Tạm dừng" : "Kích hoạt"}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-rose-600 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-950/30"
                  icon={<IconTrash size={14} />}
                  onClick={() => remove(campaign)}
                >
                  Xóa
                </Button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* ── MODAL CREATE CAMPAIGN ───────────────────────────────────────── */}
      <Modal
        open={open}
        title={
          <div className="flex items-center gap-2">
            <IconSparkles size={18} className="text-indigo-600" />
            <span>Tạo chiến dịch mới</span>
          </div>
        }
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Hủy
            </Button>
            <Button onClick={create} disabled={busy || !form.name.trim()} loading={busy}>
              Tạo chiến dịch
            </Button>
          </>
        }
      >
        <ErrorNote>{formError}</ErrorNote>
        <Field label="Tên chiến dịch *" hint="Ví dụ: Tìm khách viết tiểu thuyết / Nhận dịch truyện">
          <Input
            value={form.name}
            placeholder="Nhập tên chiến dịch…"
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Chế độ vận hành"
            hint="Bán tự động: bạn duyệt qua Telegram hoặc Web trước khi bắn comment."
          >
            <Select
              value={form.mode}
              onChange={(e) => setForm({ ...form, mode: e.target.value as Campaign["mode"] })}
            >
              <option value="semi_auto">Bán tự động (Khuyến nghị)</option>
              <option value="full_auto">Tự động hoàn toàn (Full-Auto)</option>
            </Select>
          </Field>
          <Field label="Trần comment/ngày" hint="Tối đa số lượt comment an toàn cho chiến dịch.">
            <Input
              type="number"
              min={1}
              max={100}
              value={form.max_comments_per_day}
              onChange={(e) =>
                setForm({ ...form, max_comments_per_day: Number(e.target.value) })
              }
            />
          </Field>
        </div>

        <Field label="Tên dịch vụ bạn cung cấp">
          <Input
            placeholder="Ví dụ: Dịch vụ viết truyện, thiết kế banner, viết bài PR…"
            value={form.service_name}
            onChange={(e) => setForm({ ...form, service_name: e.target.value })}
          />
        </Field>

        <Field label="Thế mạnh / chuyên môn" hint="Thông tin định vị dịch vụ để đưa vào comment ứng tuyển.">
          <Input
            placeholder="Ví dụ: 3 năm kinh nghiệm, nhận comm giá mềm, bàn giao đúng hạn…"
            value={form.service_specialties}
            onChange={(e) => setForm({ ...form, service_specialties: e.target.value })}
          />
        </Field>

        <div className="rounded-xl border border-slate-200/90 bg-slate-50/70 p-3.5 dark:border-slate-800 dark:bg-slate-800/40">
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
              checked={form.ai_comments_enabled}
              onChange={(e) => setForm({ ...form, ai_comments_enabled: e.target.checked })}
            />
            <div>
              <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                Tự động sinh comment bằng AI (Tùy chọn — Mặc định TẮT)
              </span>
              <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                Hiện tại chưa cần thiết: khi tắt, hệ thống chỉ sử dụng kho kịch bản Spintax xoay vòng do bạn thiết lập, hoàn toàn không cần OpenAI API key và không tốn chi phí token.
              </p>
            </div>
          </label>
        </div>

        <Field label="Tiêu chí lọc cho AI">
          <Textarea
            value={form.ai_filter_prompt}
            placeholder="Ví dụ: Chỉ duyệt bài viết tìm người viết truyện hoặc tuyển cộng tác viên có ngân sách rõ ràng. Bỏ qua các bài pass đồ hoặc quảng cáo lớp học."
            onChange={(e) => setForm({ ...form, ai_filter_prompt: e.target.value })}
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Từ khóa ưu tiên (Whitelist)" hint="Gõ từ khóa rồi nhấn Enter">
            <TagInput
              value={form.whitelist_keywords}
              tone="positive"
              placeholder="tìm comm, cần viết, tuyển tác giả…"
              onChange={(whitelist_keywords) => setForm({ ...form, whitelist_keywords })}
            />
          </Field>
          <Field label="Từ khóa loại trừ (Blacklist)" hint="Gõ từ khóa rồi nhấn Enter">
            <TagInput
              value={form.blacklist_keywords}
              tone="negative"
              placeholder="đã tìm được, đã đủ, share link…"
              onChange={(blacklist_keywords) => setForm({ ...form, blacklist_keywords })}
            />
          </Field>
        </div>
      </Modal>
    </div>
  );
}
