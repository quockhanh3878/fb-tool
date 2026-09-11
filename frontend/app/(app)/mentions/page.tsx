// plan: docs/plans/phase2_dashboard_detail.md
"use client";
import { useState } from "react";

import {
  IconBell,
  IconCheck,
  IconExternalLink,
  IconTrash,
} from "@/components/icons";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorNote,
  Field,
  Select,
  Spinner,
  cx,
  fmtDate,
  useAsync,
  useToast,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { Mention } from "@/lib/types";

const STATUSES = [
  { value: "", label: "Tất cả trạng thái" },
  { value: "new", label: "Chưa đọc" },
  { value: "read", label: "Đã đọc" },
  { value: "archived", label: "Đã lưu trữ" },
];

const PAGE_SIZE = 30;

export default function MentionsPage() {
  const campaigns = useAsync(() => api.campaigns());
  const toast = useToast();
  const [campaignId, setCampaignId] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);

  const mentions = useAsync(
    () =>
      api.mentions({
        campaign_id: campaignId || undefined,
        status: status || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
    [campaignId, status, offset],
  );

  async function act(fn: () => Promise<unknown>, done: string) {
    try {
      await fn();
      toast.info(done);
      mentions.reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Thao tác thất bại");
    }
  }

  const campaignName = (id: string | null) =>
    campaigns.data?.find((c) => c.id === id)?.name ?? "—";

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
              <IconBell size={18} />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-2xl">
              Hộp thư Nhắc tới
            </h1>
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Bài nhóm Scout quét được có nhắc tên thương hiệu / dịch vụ. Cấu hình từ khóa
            thương hiệu trong tab Cấu hình của từng chiến dịch.
          </p>
        </div>
      </header>

      <Card>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Chiến dịch">
            <Select
              value={campaignId}
              onChange={(e) => {
                setCampaignId(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">Tất cả chiến dịch</option>
              {campaigns.data?.map((campaign) => (
                <option key={campaign.id} value={campaign.id}>
                  {campaign.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Trạng thái">
            <Select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setOffset(0);
              }}
            >
              {STATUSES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </Card>

      <ErrorNote>{mentions.error}</ErrorNote>
      {mentions.loading && <Spinner label="Đang tải hộp thư…" />}

      {!mentions.loading && !mentions.data?.items.length && (
        <Empty icon={<IconBell size={24} />}>
          Chưa có lượt nhắc nào. Thêm từ khóa thương hiệu vào chiến dịch để Scout bắt đầu
          theo dõi.
        </Empty>
      )}

      <div className="space-y-3">
        {mentions.data?.items.map((mention) => (
          <MentionCard
            key={mention.id}
            mention={mention}
            campaignName={campaignName(mention.campaign_id)}
            onRead={() => act(() => api.markMentionRead(mention.id), "Đã đánh dấu đã đọc")}
            onArchive={() => act(() => api.archiveMention(mention.id), "Đã lưu trữ")}
            onDelete={() => act(() => api.deleteMention(mention.id), "Đã xóa lượt nhắc")}
          />
        ))}
      </div>

      {!!mentions.data && mentions.data.total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-xs text-slate-500">
          <Button
            size="sm"
            variant="outline"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Trước
          </Button>
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, mentions.data.total)} /{" "}
            {mentions.data.total}
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={offset + PAGE_SIZE >= mentions.data.total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Sau
          </Button>
        </div>
      )}
    </div>
  );
}

function MentionCard({
  mention,
  campaignName,
  onRead,
  onArchive,
  onDelete,
}: {
  mention: Mention;
  campaignName: string;
  onRead: () => void;
  onArchive: () => void;
  onDelete: () => void;
}) {
  const unread = mention.status === "new";
  return (
    <div
      className={cx(
        "rounded-2xl border p-5 shadow-xs transition-colors",
        unread
          ? "border-indigo-200 bg-indigo-50/40 dark:border-indigo-900/60 dark:bg-indigo-950/20"
          : "border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900/90",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 text-xs font-bold text-white">
            {mention.author_name?.[0]?.toUpperCase() || "FB"}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-slate-900 dark:text-white">
                {mention.author_name || "Thành viên Facebook"}
              </span>
              <Badge value={mention.status} />
            </div>
            <div className="mt-0.5 text-[11px] text-slate-400">
              {campaignName} · Quét lúc {fmtDate(mention.discovered_at)}
            </div>
          </div>
        </div>
        {mention.post_url && (
          <a
            href={mention.post_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:border-slate-800 dark:hover:bg-slate-800"
            title="Mở bài viết gốc trên Facebook"
          >
            <IconExternalLink size={15} />
          </a>
        )}
      </div>

      <div className="py-3.5">
        <p className="whitespace-pre-line text-sm leading-relaxed text-slate-800 dark:text-slate-200">
          {mention.content_text}
        </p>
        {!!mention.matched_keywords.length && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-semibold text-slate-500">Khớp từ khóa:</span>
            {mention.matched_keywords.map((kw) => (
              <span
                key={kw}
                className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800 dark:bg-amber-950/60 dark:text-amber-300"
              >
                {kw}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 pt-3 dark:border-slate-800">
        {unread && (
          <Button size="sm" variant="ghost" icon={<IconCheck size={14} />} onClick={onRead}>
            Đã đọc
          </Button>
        )}
        {mention.status !== "archived" && (
          <Button size="sm" variant="outline" onClick={onArchive}>
            Lưu trữ
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          className="text-rose-600 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-950/30"
          icon={<IconTrash size={14} />}
          onClick={onDelete}
        >
          Xóa
        </Button>
      </div>
    </div>
  );
}
