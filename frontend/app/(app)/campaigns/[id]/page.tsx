"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { RotationBadge, SpintaxEditor, VariantExplorer } from "@/components/SpintaxEditor";
import { LineListInput, TagInput } from "@/components/TagInput";
import {
  IconArrowRight,
  IconFacebook,
  IconPause,
  IconPlay,
  IconRefresh,
  IconSearch,
  IconSettings,
  IconShieldCheck,
  IconSparkles,
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
  Stat,
  Textarea,
  cx,
  fmtDate,
  useAsync,
  useToast,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { countVariants, similarity } from "@/lib/spintax";
import type { Campaign, Script } from "@/lib/types";

const TABS = [
  { key: "settings", label: "Cấu hình chung", Icon: IconSettings },
  { key: "groups", label: "Group Facebook", Icon: IconFacebook },
  { key: "scripts", label: "Kịch bản comment", Icon: IconSparkles },
  { key: "bumps", label: "Lịch bump tự động", Icon: IconZap },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [tab, setTab] = useState<TabKey>("settings");
  const campaign = useAsync(() => api.campaign(id), [id]);
  const toast = useToast();

  if (campaign.loading) return <Spinner label="Đang nạp chi tiết chiến dịch…" />;
  if (campaign.error) return <ErrorNote>{campaign.error}</ErrorNote>;
  const data = campaign.data!;

  async function toggleStatus() {
    try {
      if (data.is_active) {
        await api.pauseCampaign(id);
        toast.info("Đã tạm dừng chiến dịch");
      } else {
        await api.activateCampaign(id);
        toast.success("Đã kích hoạt chiến dịch");
      }
      campaign.reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Thao tác thất bại");
    }
  }

  return (
    <div className="space-y-6">
      {/* ── HEADER BREADCRUMB ────────────────────────────────────────────── */}
      <header className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200/80 bg-white/90 p-5 shadow-xs backdrop-blur-md dark:border-slate-800/80 dark:bg-slate-900/90">
        <div>
          <Link
            href="/campaigns"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-indigo-600 dark:hover:text-indigo-400"
          >
            ← Danh sách chiến dịch
          </Link>
          <div className="mt-1 flex items-center gap-3">
            <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-2xl">
              {data.name}
            </h1>
            <Badge value={data.is_active ? "active" : "paused"} />
            <Badge value={data.mode} />
          </div>
        </div>

        <Button
          variant={data.is_active ? "ghost" : "primary"}
          size="sm"
          icon={data.is_active ? <IconPause size={14} /> : <IconPlay size={14} />}
          onClick={toggleStatus}
        >
          {data.is_active ? "Tạm dừng chiến dịch" : "Kích hoạt chiến dịch"}
        </Button>
      </header>

      {/* ── MODERN PILL TABS ─────────────────────────────────────────────── */}
      <nav className="flex flex-wrap gap-1.5 rounded-2xl border border-slate-200/80 bg-slate-100/70 p-1.5 dark:border-slate-800/80 dark:bg-slate-900/60">
        {TABS.map((item) => {
          const active = tab === item.key;
          return (
            <button
              key={item.key}
              onClick={() => setTab(item.key)}
              className={cx(
                "flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold transition-all duration-150",
                active
                  ? "bg-white text-indigo-600 shadow-xs dark:bg-slate-800 dark:text-indigo-400"
                  : "text-slate-600 hover:bg-white/50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/50 dark:hover:text-slate-200",
              )}
            >
              <item.Icon size={16} />
              {item.label}
            </button>
          );
        })}
      </nav>

      {tab === "settings" && <SettingsTab campaign={data} onSaved={campaign.reload} />}
      {tab === "groups" && <GroupsTab campaignId={id} />}
      {tab === "scripts" && <ScriptsTab campaign={data} />}
      {tab === "bumps" && <BumpsTab campaignId={id} />}
    </div>
  );
}

// ── Tab: cấu hình ──────────────────────────────────────────────────────────
function SettingsTab({ campaign, onSaved }: { campaign: Campaign; onSaved: () => void }) {
  const [form, setForm] = useState({
    ...campaign,
  });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function save() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api.updateCampaign(campaign.id, {
        name: form.name,
        mode: form.mode,
        service_name: form.service_name,
        service_specialties: form.service_specialties,
        service_strengths: form.service_strengths,
        landing_page_note: form.landing_page_note,
        ai_filter_prompt: form.ai_filter_prompt,
        mention_keywords: form.mention_keywords ?? [],
        whitelist_keywords: form.whitelist_keywords,
        blacklist_keywords: form.blacklist_keywords,
        min_relevance_score: Number(form.min_relevance_score),
        max_competitor_comments: Number(form.max_competitor_comments),
        max_comments_per_day: Number(form.max_comments_per_day),
        delay_min_seconds: Number(form.delay_min_seconds),
        delay_max_seconds: Number(form.delay_max_seconds),
      });
      setMessage("Đã lưu.");
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lưu thất bại");
    } finally {
      setBusy(false);
    }
  }

  const set = (key: keyof typeof form) => (event: { target: { value: string } }) =>
    setForm({ ...form, [key]: event.target.value });

  return (
    <Card
      title="Cấu hình chiến dịch"
      action={
        <Button size="sm" onClick={save} disabled={busy}>
          {busy ? "Đang lưu…" : "Lưu"}
        </Button>
      }
    >
      <ErrorNote>{error}</ErrorNote>
      {message && <p className="mb-3 text-sm text-emerald-600">{message}</p>}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Tên chiến dịch">
          <Input value={form.name} onChange={set("name")} />
        </Field>
        <Field label="Chế độ">
          <Select value={form.mode} onChange={set("mode")}>
            <option value="semi_auto">Bán tự động</option>
            <option value="full_auto">Tự động hoàn toàn</option>
          </Select>
        </Field>
        <Field label="Tên dịch vụ">
          <Input value={form.service_name} onChange={set("service_name")} />
        </Field>
        <Field label="Chuyên môn">
          <Input value={form.service_specialties} onChange={set("service_specialties")} />
        </Field>
        <Field label="Thế mạnh">
          <Input value={form.service_strengths} onChange={set("service_strengths")} />
        </Field>
        <Field label="Ghi chú trang bán hàng" hint="Không được chèn link vào comment.">
          <Input value={form.landing_page_note} onChange={set("landing_page_note")} />
        </Field>
      </div>

      <div className="mt-4">
        <Field label="Tiêu chí lọc cho AI">
          <Textarea value={form.ai_filter_prompt} onChange={set("ai_filter_prompt")} />
        </Field>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field
          label="Từ khóa ưu tiên"
          hint="Bài chứa một trong các từ này mới được đưa lên AI chấm điểm — lọc miễn phí trước khi tốn tiền."
        >
          <TagInput
            value={form.whitelist_keywords}
            tone="positive"
            placeholder="tìm comm, cần viết…"
            onChange={(whitelist_keywords) => setForm({ ...form, whitelist_keywords })}
          />
        </Field>
        <Field label="Từ khóa loại trừ" hint="Bài chứa từ này bị loại ngay, không cần hỏi AI.">
          <TagInput
            value={form.blacklist_keywords}
            tone="negative"
            placeholder="đã tìm được, đã đủ người…"
            onChange={(blacklist_keywords) => setForm({ ...form, blacklist_keywords })}
          />
        </Field>
      </div>

      <div className="mt-4">
        <Field
          label="Từ khóa nhắc tới thương hiệu"
          hint="Scout gom bài nhắc tới các từ này vào Hộp thư Nhắc tới để anh Ber phản hồi tay. Bỏ trống thì tắt tính năng."
        >
          <TagInput
            value={form.mention_keywords ?? []}
            tone="positive"
            placeholder="tên shop, tên dịch vụ, fanpage…"
            onChange={(mention_keywords) => setForm({ ...form, mention_keywords })}
          />
        </Field>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Ngưỡng phù hợp (0–1)">
          <Input
            type="number"
            step="0.05"
            min={0}
            max={1}
            value={form.min_relevance_score}
            onChange={set("min_relevance_score")}
          />
        </Field>
        <Field label="Trần comment đối thủ" hint="Bài đông comment quá thì bỏ, tránh chen chân.">
          <Input
            type="number"
            min={0}
            value={form.max_competitor_comments}
            onChange={set("max_competitor_comments")}
          />
        </Field>
        <Field label="Trần comment/ngày">
          <Input
            type="number"
            min={1}
            value={form.max_comments_per_day}
            onChange={set("max_comments_per_day")}
          />
        </Field>
        <Field label="Giãn cách tối thiểu (giây)">
          <Input
            type="number"
            min={30}
            value={form.delay_min_seconds}
            onChange={set("delay_min_seconds")}
          />
        </Field>
        <Field label="Giãn cách tối đa (giây)">
          <Input
            type="number"
            min={30}
            value={form.delay_max_seconds}
            onChange={set("delay_max_seconds")}
          />
        </Field>
      </div>
    </Card>
  );
}

// ── Tab: group ─────────────────────────────────────────────────────────────
function GroupsTab({ campaignId }: { campaignId: string }) {
  const { data, loading, error, reload } = useAsync(() => api.groups(campaignId), [campaignId]);
  const toast = useToast();
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [interval, setInterval] = useState(10);
  const [formError, setFormError] = useState("");
  const [discovering, setDiscovering] = useState(false);
  const [discoverModalOpen, setDiscoverModalOpen] = useState(false);
  const [discoverResultMsg, setDiscoverResultMsg] = useState("");

  async function add() {
    setFormError("");
    try {
      await api.addGroup(campaignId, {
        group_url: url,
        group_name: name,
        scan_interval_minutes: Number(interval),
      });
      setUrl("");
      setName("");
      reload();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Không thêm được group");
    }
  }

  async function startDiscover() {
    setFormError("");
    setDiscovering(true);
    setDiscoverResultMsg("");
    try {
      const res = await api.discoverGroups(campaignId);
      setDiscoverResultMsg(res.message);
      toast.info(res.message);
      // Tự động reload sau 30s và 75s để cập nhật nhóm mới
      window.setTimeout(reload, 30_000);
      window.setTimeout(reload, 75_000);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Không quét được hồ sơ clone";
      setFormError(msg);
      toast.error(msg);
    } finally {
      setDiscovering(false);
    }
  }

  return (
    <>
      <Card title="Thêm group">
        <ErrorNote>{formError}</ErrorNote>
        <div className="grid gap-3 sm:grid-cols-[2fr_1fr_auto] sm:items-end">
          <Field label="URL group" hint="Dán link group hoặc mã group Facebook.">
            <Input
              value={url}
              placeholder="https://www.facebook.com/groups/..."
              onChange={(e) => setUrl(e.target.value)}
            />
          </Field>
          <Field label="Tên gợi nhớ">
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Button onClick={add} disabled={!url.trim()}>
            Thêm
          </Button>
        </div>
        <div className="mt-3 max-w-48">
          <Field label="Chu kỳ quét (phút)">
            <Input
              type="number"
              min={3}
              max={1440}
              value={interval}
              onChange={(e) => setInterval(Number(e.target.value))}
            />
          </Field>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-3 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDiscoverModalOpen(true)}
              icon={<IconFacebook size={15} />}
            >
              Tự lấy nhóm đã tham gia từ Clone
            </Button>
            <span className="text-xs text-slate-500">
              Cào tự động toàn bộ nhóm nick Scout đã join
            </span>
          </div>
          <Button variant="ghost" size="xs" onClick={reload} icon={<IconRefresh size={13} />}>
            Làm mới danh sách
          </Button>
        </div>
      </Card>

      {/* Modal hướng dẫn & tiến trình cào nhóm tự động */}
      <Modal
        open={discoverModalOpen}
        title="Tự động lấy nhóm Facebook từ Nick Clone Scout"
        onClose={() => setDiscoverModalOpen(false)}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDiscoverModalOpen(false)}>
              Đóng
            </Button>
            <Button
              onClick={startDiscover}
              loading={discovering}
              disabled={discovering}
              icon={<IconSearch size={15} />}
            >
              {discovering ? "Đang gửi lệnh cào…" : "Bắt đầu cào nhóm ngay"}
            </Button>
          </div>
        }
      >
        <div className="space-y-4 text-xs text-slate-600 dark:text-slate-300">
          <div className="rounded-xl border border-indigo-100 bg-indigo-50/70 p-4 dark:border-indigo-950 dark:bg-indigo-950/40">
            <h4 className="font-bold text-indigo-950 dark:text-indigo-200 flex items-center gap-1.5 mb-2">
              <IconShieldCheck size={16} className="text-indigo-600" /> Cách thức hoạt động an toàn:
            </h4>
            <ul className="space-y-1.5 list-disc list-inside leading-relaxed text-indigo-900 dark:text-indigo-300">
              <li>Mở trình duyệt Chrome thật trong nền với hồ sơ của clone đóng vai trò <strong>Scout</strong>.</li>
              <li>Tự động cuộn trang <em>Nhóm của bạn</em> trên Facebook để lấy tối đa 300 nhóm đã tham gia.</li>
              <li>Chỉ đọc dữ liệu — <strong>không tương tác, không đăng bài, không join/rời nhóm</strong>.</li>
              <li>Nhóm mới lấy về sẽ ở trạng thái <strong>Tạm dừng (paused)</strong> để anh Ber chủ động bật nhóm nào muốn theo dõi, bảo vệ hạn mức gói cước.</li>
            </ul>
          </div>

          {discoverResultMsg && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50/80 p-3.5 text-xs text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-300 flex items-start gap-2">
              <IconSparkles size={16} className="shrink-0 text-emerald-600 mt-0.5" />
              <div>
                <p className="font-bold">Đã tiếp nhận yêu cầu cào nhóm!</p>
                <p className="mt-1">{discoverResultMsg}</p>
                <p className="mt-2 text-[11px] text-emerald-700 dark:text-emerald-400">
                  Tiến trình mất khoảng 60–90 giây. Bạn có thể đóng cửa sổ này, hệ thống sẽ tự động cập nhật và gửi tin nhắn tóm tắt qua Telegram khi hoàn thành.
                </p>
              </div>
            </div>
          )}
        </div>
      </Modal>

      <Card title={`Danh sách group (${data?.length ?? 0})`}>
        <ErrorNote>{error}</ErrorNote>
        {loading && <Spinner />}
        {!loading && !data?.length && <Empty>Chưa có group nào.</Empty>}
        {!!data?.length && (
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Group</th>
                  <th>Trạng thái</th>
                  <th>Chu kỳ</th>
                  <th>Quét lần cuối</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.map((group) => (
                  <tr key={group.id}>
                    <td>
                      <a
                        href={group.group_url}
                        target="_blank"
                        rel="noreferrer"
                        className="font-medium underline"
                      >
                        {group.group_name || group.group_key}
                      </a>
                      <p className="text-xs text-slate-500">{group.group_key}</p>
                    </td>
                    <td>
                      <Badge value={group.status} />
                    </td>
                    <td>{group.scan_interval_minutes} phút</td>
                    <td className="text-xs text-slate-500">{fmtDate(group.last_scanned_at)}</td>
                    <td className="text-right">
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={async () => {
                          if (!confirm("Xóa group này khỏi chiến dịch?")) return;
                          await api.deleteGroup(campaignId, group.id);
                          reload();
                        }}
                      >
                        Xóa
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

// ── Tab: kịch bản ──────────────────────────────────────────────────────────
function ScriptsTab({ campaign }: { campaign: Campaign }) {
  const campaignId = campaign.id;
  const { data, loading, error, reload } = useAsync(() => api.scripts(campaignId), [campaignId]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Script | null>(null);
  const [form, setForm] = useState({
    name: "",
    type: "spintax" as Script["type"],
    template_content: "",
    ai_system_prompt: "",
    is_default: false,
    is_active: true,
  });
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  function openNew() {
    setEditing(null);
    setFormError("");
    setForm({
      name: "",
      type: "spintax",
      template_content: "",
      ai_system_prompt: "",
      is_default: !data?.length, // kịch bản đầu tiên mặc định là cái chính
      is_active: true,
    });
    setOpen(true);
  }

  function openEdit(script: Script) {
    setEditing(script);
    setFormError("");
    setForm({
      name: script.name,
      type: script.type,
      template_content: script.template_content,
      ai_system_prompt: script.ai_system_prompt,
      is_default: script.is_default,
      is_active: script.is_active,
    });
    setOpen(true);
  }

  async function save() {
    setSaving(true);
    setFormError("");
    try {
      if (editing) await api.updateScript(campaignId, editing.id, form);
      else await api.createScript(campaignId, form);
      setOpen(false);
      reload();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Lưu kịch bản thất bại");
    } finally {
      setSaving(false);
    }
  }

  // Tổng số biến thể của tất cả kịch bản đang bật — con số quyết định
  // chiến dịch có bị lặp lời hay không.
  const activeScripts = (data ?? []).filter(
    (script) => script.is_active && script.type === "spintax",
  );
  const totalVariants = activeScripts.reduce(
    (sum, script) => sum + countVariants(script.template_content),
    0,
  );
  const daysSafe = totalVariants / Math.max(1, campaign.max_comments_per_day);

  // Hai kịch bản na ná nhau thì xoay vòng cũng vô nghĩa — nhắc người dùng.
  const overlaps: string[] = [];
  for (let i = 0; i < activeScripts.length; i += 1) {
    for (let j = i + 1; j < activeScripts.length; j += 1) {
      if (similarity(activeScripts[i].template_content, activeScripts[j].template_content) >= 0.75) {
        overlaps.push(`«${activeScripts[i].name}» và «${activeScripts[j].name}»`);
      }
    }
  }

  return (
    <>
      <Card title="Sức khỏe nội dung">
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat label="Kịch bản đang bật" value={activeScripts.length} />
          <Stat
            label="Tổng biến thể"
            value={totalVariants.toLocaleString("vi-VN")}
            tone={totalVariants >= 50 ? "good" : totalVariants >= 10 ? "warn" : "bad"}
          />
          <Stat
            label="Ngày chạy chưa phải lặp"
            value={daysSafe >= 100 ? "99+" : daysSafe.toFixed(1)}
            hint={`Theo trần ${campaign.max_comments_per_day} comment/ngày`}
            tone={daysSafe >= 3 ? "good" : daysSafe >= 1 ? "warn" : "bad"}
          />
        </div>

        <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">
          Hệ thống <b>xoay vòng</b> giữa các kịch bản đang bật (ưu tiên cái ít dùng nhất), rồi trong
          mỗi kịch bản lại chọn biến thể <b>khác 30 comment gần nhất</b>. Càng nhiều biến thể, càng
          lâu mới phải nói lại một câu.
        </p>

        {!!overlaps.length && (
          <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
            ⚠️ Các cặp kịch bản sau quá giống nhau, xoay vòng gần như không có tác dụng:{" "}
            {overlaps.join("; ")}.
          </p>
        )}
      </Card>

      <Card
        title={`Kịch bản comment (${data?.length ?? 0})`}
        action={
          <Button size="sm" onClick={openNew}>
            + Kịch bản
          </Button>
        }
      >
        <ErrorNote>{error}</ErrorNote>
        {loading && <Spinner />}
        {!loading && !data?.length && (
          <Empty>
            Chưa có kịch bản. Dùng cú pháp <code>{"{chào bạn|hi bạn}"}</code> để mỗi lần comment một
            khác — đây là tuyến phòng thủ chính trước bộ lọc spam của Facebook.
          </Empty>
        )}

        <ul className="space-y-3">
          {data?.map((script) => (
            <li
              key={script.id}
              className={cx(
                "rounded-lg border p-3",
                script.is_active
                  ? "border-slate-200 dark:border-slate-800"
                  : "border-dashed border-slate-300 opacity-60 dark:border-slate-700",
              )}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{script.name}</span>
                <Badge value={script.type === "spintax" ? "matched" : "analyzing"}>
                  {script.type === "spintax" ? "Spintax" : "AI theo ngữ cảnh"}
                </Badge>
                {script.is_default && <Badge value="active">Mặc định</Badge>}
                {!script.is_active && <Badge value="paused">Đang tắt</Badge>}
                <RotationBadge usage={script.usage_count} lastUsed={script.last_used_at} />
                {script.type === "spintax" && (
                  <span className="text-xs text-slate-500">
                    {countVariants(script.template_content).toLocaleString("vi-VN")} biến thể
                  </span>
                )}
              </div>

              <p className="mt-1 whitespace-pre-wrap font-mono text-sm text-slate-600 dark:text-slate-400">
                {script.template_content || script.ai_system_prompt || "(trống)"}
              </p>

              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Button size="sm" variant="ghost" onClick={() => openEdit(script)}>
                  Sửa nội dung
                </Button>
                <Button
                  size="sm"
                  variant="subtle"
                  onClick={async () => {
                    await api.updateScript(campaignId, script.id, {
                      is_active: !script.is_active,
                    });
                    reload();
                  }}
                >
                  {script.is_active ? "Tắt tạm" : "Bật lại"}
                </Button>
                {!script.is_default && (
                  <Button
                    size="sm"
                    variant="subtle"
                    onClick={async () => {
                      await api.updateScript(campaignId, script.id, { is_default: true });
                      reload();
                    }}
                  >
                    Đặt làm mặc định
                  </Button>
                )}
                {script.type === "spintax" && (
                  <VariantExplorer campaignId={campaignId} scriptId={script.id} />
                )}
                <Button
                  size="sm"
                  variant="danger"
                  onClick={async () => {
                    if (!confirm(`Xóa kịch bản "${script.name}"?`)) return;
                    await api.deleteScript(campaignId, script.id);
                    reload();
                  }}
                >
                  Xóa
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </Card>

      <Modal
        open={open}
        title={editing ? `Sửa: ${editing.name}` : "Kịch bản mới"}
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Hủy
            </Button>
            <Button onClick={save} disabled={saving || !form.name.trim()}>
              {saving ? "Đang lưu…" : "Lưu"}
            </Button>
          </>
        }
      >
        <ErrorNote>{formError}</ErrorNote>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Tên kịch bản">
            <Input
              value={form.name}
              placeholder="Ví dụ: Chào hàng ngắn gọn"
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Loại">
            <Select
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value as Script["type"] })}
            >
              <option value="spintax">Spintax (tự xoay biến thể, không tốn tiền AI)</option>
              <option value="ai_contextual">AI viết theo ngữ cảnh từng bài</option>
            </Select>
          </Field>
        </div>

        {form.type === "spintax" ? (
          <SpintaxEditor
            campaignId={campaignId}
            value={form.template_content}
            maxCommentsPerDay={campaign.max_comments_per_day}
            onChange={(template_content) => setForm({ ...form, template_content })}
          />
        ) : (
          <Field
            label="Chỉ dẫn cho AI"
            hint="AI đọc nội dung bài rồi viết comment bám ngữ cảnh. Mỗi bài một câu khác nhau nên không cần spintax."
          >
            <Textarea
              value={form.ai_system_prompt}
              className="min-h-32"
              placeholder="Ví dụ: viết như một freelancer thân thiện, nêu đúng thể loại khách cần, mời nhắn tin riêng, tuyệt đối không chèn link."
              onChange={(e) => setForm({ ...form, ai_system_prompt: e.target.value })}
            />
          </Field>
        )}

        <div className="flex flex-wrap gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.is_default}
              onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
            />
            Đặt làm kịch bản mặc định
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
            />
            Cho tham gia vòng xoay
          </label>
        </div>
      </Modal>
    </>
  );
}

// ── Tab: bump ──────────────────────────────────────────────────────────────
const HOURS = Array.from({ length: 24 }, (_, hour) => hour);

function BumpsTab({ campaignId }: { campaignId: string }) {
  const { user } = useAuth();
  const { data, loading, error, reload } = useAsync(() => api.bumps(campaignId), [campaignId]);
  const [form, setForm] = useState({
    target_post_url: "",
    hours: [8, 12, 20] as number[],
    messages: [] as string[],
  });
  const [formError, setFormError] = useState("");
  const bumpAllowed = user?.subscription?.bump_enabled ?? false;

  async function create() {
    setFormError("");
    try {
      await api.createBump(campaignId, {
        target_post_url: form.target_post_url,
        cron_schedule: form.hours,
        bump_messages: form.messages,
      });
      setForm({ target_post_url: "", hours: [8, 12, 20], messages: [] });
      reload();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Không tạo được lịch bump");
    }
  }

  return (
    <>
      {!bumpAllowed && (
        <ErrorNote>
          Tính năng Bump chỉ có ở gói Pro trở lên. Bạn vẫn xem được lịch cũ, nhưng tạo mới sẽ bị từ
          chối.
        </ErrorNote>
      )}

      <Card title="Tạo lịch bump">
        <ErrorNote>{formError}</ErrorNote>
        <Field label="URL bài viết cần bump">
          <Input
            value={form.target_post_url}
            placeholder="https://www.facebook.com/groups/.../posts/..."
            onChange={(e) => setForm({ ...form, target_post_url: e.target.value })}
          />
        </Field>
        <div className="mt-3">
          <Field label="Khung giờ bump" hint="Giờ Việt Nam. Mỗi khung giờ chỉ bump đúng một lần.">
            <div className="flex flex-wrap gap-1">
              {HOURS.map((hour) => {
                const picked = form.hours.includes(hour);
                return (
                  <button
                    key={hour}
                    type="button"
                    onClick={() =>
                      setForm({
                        ...form,
                        hours: picked
                          ? form.hours.filter((item) => item !== hour)
                          : [...form.hours, hour].sort((a, b) => a - b),
                      })
                    }
                    className={cx(
                      "w-10 rounded-lg border py-1 text-xs tabular-nums transition",
                      picked
                        ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                        : "border-slate-300 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800",
                    )}
                  >
                    {hour}h
                  </button>
                );
              })}
            </div>
          </Field>
        </div>
        <div className="mt-3">
          <Field
            label="Nội dung bump"
            hint="Mỗi dòng một câu, hệ thống xoay vòng ngẫu nhiên. Dùng spintax {Up|Lên} để mỗi lần một khác."
          >
            <LineListInput
              value={form.messages}
              placeholder="Up bài nhé mọi người"
              onChange={(messages) => setForm({ ...form, messages })}
              renderHint={(line) => {
                const variants = countVariants(line);
                return variants > 1
                  ? `${variants} biến thể — mỗi lần bump một câu khác`
                  : "Chỉ 1 biến thể — thêm {a|b} để tránh lặp lời";
              }}
            />
          </Field>
        </div>

        <p className="mt-2 text-xs text-slate-500">
          Tổng cộng <b>{form.messages.reduce((sum, line) => sum + countVariants(line), 0)}</b> câu
          bump khác nhau trên {form.hours.length} khung giờ mỗi ngày.
        </p>

        <Button
          className="mt-3"
          onClick={create}
          disabled={!form.target_post_url.trim() || !form.messages.length || !form.hours.length}
        >
          Tạo lịch
        </Button>
      </Card>

      <Card title={`Lịch bump (${data?.length ?? 0})`}>
        <ErrorNote>{error}</ErrorNote>
        {loading && <Spinner />}
        {!loading && !data?.length && <Empty>Chưa có lịch bump nào.</Empty>}
        <ul className="space-y-3">
          {data?.map((bump) => (
            <li key={bump.id} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
              <div className="flex flex-wrap items-center gap-2">
                <Badge value={bump.is_active ? "active" : "paused"} />
                <span className="text-xs text-slate-500">
                  Khung giờ: {bump.cron_schedule.join("h, ")}h
                </span>
                <span className="text-xs text-slate-500">
                  Bump gần nhất: {fmtDate(bump.last_bumped_at)}
                </span>
              </div>
              <a
                href={bump.target_post_url}
                target="_blank"
                rel="noreferrer"
                className="mt-1 block truncate text-sm underline"
              >
                {bump.target_post_url}
              </a>
              <ul className="mt-1 list-disc pl-5 text-sm text-slate-600 dark:text-slate-400">
                {bump.bump_messages.map((message, index) => (
                  <li key={index}>{message}</li>
                ))}
              </ul>
              <div className="mt-2 flex gap-2">
                <Button
                  size="sm"
                  variant="subtle"
                  onClick={async () => {
                    await api.updateBump(campaignId, bump.id, { is_active: !bump.is_active });
                    reload();
                  }}
                >
                  {bump.is_active ? "Tạm dừng" : "Bật lại"}
                </Button>
                <Button
                  size="sm"
                  variant="danger"
                  onClick={async () => {
                    if (!confirm("Xóa lịch bump này?")) return;
                    await api.deleteBump(campaignId, bump.id);
                    reload();
                  }}
                >
                  Xóa
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}
