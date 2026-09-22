// plan: docs/plans/phase2_dashboard_detail.md
"use client";

import { useState } from "react";

import { IconCheck, IconExternalLink, IconUsers } from "@/components/icons";
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
import type { Lead } from "@/lib/types";

const PAGE_SIZE = 30;

export default function LeadsPage() {
  const campaigns = useAsync(() => api.campaigns());
  const toast = useToast();
  const [campaignId, setCampaignId] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const leads = useAsync(
    () => api.leads({ campaign_id: campaignId || undefined, status: status || undefined, limit: PAGE_SIZE, offset }),
    [campaignId, status, offset],
  );

  async function act(fn: () => Promise<unknown>, message: string) {
    try {
      await fn();
      toast.info(message);
      leads.reload();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Thao tác thất bại");
    }
  }

  const campaignName = (id: string) => campaigns.data?.find((item) => item.id === id)?.name ?? "—";

  return (
    <div className="space-y-6">
      <header>
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
            <IconUsers size={18} />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-2xl">Săn lead qua comment</h1>
        </div>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          Mỗi lead giữ link bài gốc, link comment nếu Scout bóc được, và trạng thái đã đọc.
        </p>
      </header>

      <Card>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Chiến dịch">
            <Select value={campaignId} onChange={(event) => { setCampaignId(event.target.value); setOffset(0); }}>
              <option value="">Tất cả chiến dịch</option>
              {campaigns.data?.map((campaign) => <option key={campaign.id} value={campaign.id}>{campaign.name}</option>)}
            </Select>
          </Field>
          <Field label="Trạng thái">
            <Select value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0); }}>
              <option value="">Tất cả trạng thái</option>
              <option value="new">Chưa đọc</option>
              <option value="read">Đã đọc</option>
              <option value="archived">Đã lưu trữ</option>
            </Select>
          </Field>
        </div>
      </Card>

      <ErrorNote>{leads.error}</ErrorNote>
      {leads.loading && <Spinner label="Đang tải danh sách lead…" />}
      {!leads.loading && !leads.data?.items.length && (
        <Empty icon={<IconUsers size={24} />}>Chưa có lead nào khớp từ khóa comment.</Empty>
      )}
      <div className="space-y-3">
        {leads.data?.items.map((lead) => (
          <LeadCard
            key={lead.id}
            lead={lead}
            campaignName={campaignName(lead.campaign_id)}
            onRead={() => act(() => api.markLeadRead(lead.id), "Đã đánh dấu lead đã đọc")}
            onArchive={() => act(() => api.archiveLead(lead.id), "Đã lưu trữ lead")}
          />
        ))}
      </div>
      {!!leads.data && leads.data.total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-xs text-slate-500">
          <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Trước</Button>
          <span>{offset + 1}–{Math.min(offset + PAGE_SIZE, leads.data.total)} / {leads.data.total}</span>
          <Button size="sm" variant="outline" disabled={offset + PAGE_SIZE >= leads.data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Sau</Button>
        </div>
      )}
    </div>
  );
}

function LeadCard({ lead, campaignName, onRead, onArchive }: { lead: Lead; campaignName: string; onRead: () => void; onArchive: () => void }) {
  const unread = lead.status === "new";
  return (
    <div className={cx("rounded-2xl border p-5 shadow-xs", unread ? "border-indigo-200 bg-indigo-50/40 dark:border-indigo-900/60 dark:bg-indigo-950/20" : "border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900/90")}>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-3 dark:border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-slate-900 dark:text-white">{lead.author_name || "Thành viên Facebook"}</span>
            <Badge value={lead.status} />
          </div>
          <div className="mt-0.5 text-[11px] text-slate-400">{campaignName} · Phát hiện lúc {fmtDate(lead.discovered_at)}</div>
        </div>
        <div className="flex gap-2">
          {!!lead.post_url && <a href={lead.post_url} target="_blank" rel="noopener noreferrer" className="flex h-8 items-center gap-1 rounded-lg border border-slate-200 px-2 text-xs text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-300" title="Mở bài gốc"><IconExternalLink size={14} /> Bài gốc</a>}
          {!!lead.comment_url && <a href={lead.comment_url} target="_blank" rel="noopener noreferrer" className="flex h-8 items-center gap-1 rounded-lg border border-slate-200 px-2 text-xs text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-300" title="Mở comment"><IconExternalLink size={14} /> Comment</a>}
        </div>
      </div>
      <p className="whitespace-pre-line py-3.5 text-sm leading-relaxed text-slate-800 dark:text-slate-200">{lead.comment_text}</p>
      {!!lead.matched_keywords.length && <div className="flex flex-wrap gap-1.5">{lead.matched_keywords.map((keyword) => <span key={keyword} className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800 dark:bg-amber-950/60 dark:text-amber-300">{keyword}</span>)}</div>}
      <div className="flex justify-end gap-2 border-t border-slate-100 pt-3 dark:border-slate-800">
        {unread && <Button size="sm" variant="ghost" icon={<IconCheck size={14} />} onClick={onRead}>Đã đọc</Button>}
        {lead.status !== "archived" && <Button size="sm" variant="outline" onClick={onArchive}>Lưu trữ</Button>}
      </div>
    </div>
  );
}
