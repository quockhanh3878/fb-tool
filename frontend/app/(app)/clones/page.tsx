"use client";
import { useMemo, useRef, useState } from "react";

import { DiagnosisPanel, ScoreRing } from "@/components/AccountHealth";
import {
  IconCheck,
  IconHeartPulse,
  IconPlus,
  IconRefresh,
  IconShieldCheck,
  IconUsers,
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
  Progress,
  Select,
  Spinner,
  cx,
  fmtDate,
  useAsync,
  useToast,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { Clone, CloneDiagnosis, CloneRole } from "@/lib/types";

/** Chuyển trạng thái cho phép thao tác tay — khớp bảng STATE_TRANSITIONS ở backend. */
const MANUAL_EVENTS: Record<string, { event: string; label: string }[]> = {
  onboarding: [{ event: "cookie_valid", label: "Đánh dấu cookie hợp lệ" }],
  warming_up: [{ event: "warmup_complete", label: "Hoàn tất ủ ấm → cho chạy" }],
  active: [{ event: "quota_reached", label: "Cho nghỉ (cooldown)" }],
  cooldown: [{ event: "cooldown_expired", label: "Đánh thức ngay" }],
  checkpoint: [
    { event: "verification_success", label: "Đã xác minh xong" },
    { event: "verification_failed", label: "Xác minh thất bại → khóa" },
  ],
  shadowbanned: [{ event: "cooldown_expired", label: "Hết nghỉ → chạy lại" }],
};

export default function ClonesPage() {
  const { data, loading, error, reload } = useAsync(() => api.clones());
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [roleFilter, setRoleFilter] = useState<string>("all_roles");
  const [form, setForm] = useState({
    display_name: "",
    role: "shooter" as CloneRole,
    daily_comment_limit: 20,
    daily_post_limit: 5,
    proxy_address: "",
    is_backup: false,
  });
  const [formError, setFormError] = useState("");
  const [timelineFor, setTimelineFor] = useState<Clone | null>(null);
  const [diagnosis, setDiagnosis] = useState<CloneDiagnosis | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkNote, setCheckNote] = useState("");

  const roleCounts = useMemo(() => {
    const counts: Record<string, number> = { scout: 0, shooter: 0, poster: 0, both: 0, all: 0 };
    data?.forEach((c) => {
      if (counts[c.role] !== undefined) counts[c.role]++;
    });
    return counts;
  }, [data]);

  const filteredClones = useMemo(() => {
    if (!data) return [];
    if (roleFilter === "all_roles") return data;
    return data.filter((c) => c.role === roleFilter);
  }, [data, roleFilter]);

  /** Kiểm tra một lượt toàn bộ clone — cùng bộ luật với task chạy nền. */
  async function checkAll() {
    setChecking(true);
    setCheckNote("");
    try {
      const result = await api.checkAllClones();
      const bad = result.summary.critical_count;
      setCheckNote(
        [
          `Đã kiểm tra ${result.reports.length} clone.`,
          `${result.summary.ready_count} clone sẵn sàng, còn bắn được ${result.summary.capacity_left} comment hôm nay.`,
          bad ? `${bad} vấn đề nghiêm trọng cần xử lý.` : "Không có vấn đề nghiêm trọng.",
          result.transitioned.length
            ? `Đã hạ trạng thái vì cookie hỏng: ${result.transitioned.join(", ")}.`
            : "",
        ]
          .filter(Boolean)
          .join(" "),
      );
      toast.info(`Kiểm tra hoàn tất: ${result.summary.ready_count} clone sẵn sàng.`);
      reload();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Kiểm tra thất bại";
      setCheckNote(msg);
      toast.error(msg);
    } finally {
      setChecking(false);
    }
  }

  async function create() {
    setFormError("");
    try {
      await api.createClone({
        display_name: form.display_name,
        role: form.role,
        daily_comment_limit: Number(form.daily_comment_limit),
        daily_post_limit: Number(form.daily_post_limit),
        proxy_address: form.proxy_address || null,
        is_backup: form.is_backup,
      });
      setOpen(false);
      setForm({
        display_name: "",
        role: "shooter",
        daily_comment_limit: 20,
        daily_post_limit: 5,
        proxy_address: "",
        is_backup: false,
      });
      toast.success("Đã thêm tài khoản clone mới thành công!", "Thành công");
      reload();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Không tạo được clone");
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
              <IconUsers size={18} />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-2xl">
              Tài khoản Clone Facebook
            </h1>
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Phân bổ chuyên biệt: nick quét bài săn lead, nick cmt ứng tuyển, nick đăng bài seeding để tối ưu hiệu suất và chống checkpoint chéo.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <Button
            variant="ghost"
            size="sm"
            onClick={checkAll}
            disabled={checking || !data?.length}
            loading={checking}
            icon={<IconRefresh size={14} />}
          >
            {checking ? "Đang quét…" : "Kiểm tra tất cả"}
          </Button>
          <Button size="sm" onClick={() => setOpen(true)} icon={<IconPlus size={15} />}>
            Thêm clone mới
          </Button>
        </div>
      </header>

      {checkNote && (
        <div className="flex items-start gap-2.5 rounded-xl border border-indigo-200/80 bg-indigo-50/70 p-3.5 text-xs text-indigo-950 dark:border-indigo-900/60 dark:bg-indigo-950/40 dark:text-indigo-300">
          <IconShieldCheck size={17} className="text-indigo-600 dark:text-indigo-400 shrink-0 mt-0.5" />
          <p className="leading-relaxed">{checkNote}</p>
        </div>
      )}

      {/* Bộ lọc phân loại nhiệm vụ cho từng nick */}
      {data && data.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 border-b border-slate-200 pb-3 dark:border-slate-800">
          {[
            { id: "all_roles", label: "Tất cả vai trò", count: data.length, icon: "👥" },
            { id: "scout", label: "Quét bài (Scout)", count: roleCounts.scout, icon: "🔍" },
            { id: "shooter", label: "Cmt bài (Shooter)", count: roleCounts.shooter, icon: "💬" },
            { id: "poster", label: "Đăng bài (Poster)", count: roleCounts.poster, icon: "📢" },
            { id: "all", label: "Đa nhiệm (All)", count: roleCounts.all, icon: "⚡" },
            { id: "both", label: "Quét & Cmt", count: roleCounts.both, icon: "🔄" },
          ].map((tab) => {
            const active = roleFilter === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setRoleFilter(tab.id)}
                className={cx(
                  "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer",
                  active
                    ? "bg-indigo-600 text-white shadow-sm dark:bg-indigo-500"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700",
                )}
              >
                <span>{tab.icon}</span>
                <span>{tab.label}</span>
                <span
                  className={cx(
                    "ml-1 rounded-full px-1.5 py-0.2 text-[10px]",
                    active ? "bg-white/20 text-white" : "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300",
                  )}
                >
                  {tab.count}
                </span>
              </button>
            );
          })}
        </div>
      )}

      <ErrorNote>{error}</ErrorNote>
      {loading && <Spinner label="Đang tải danh sách tài khoản clone…" />}
      {!loading && !data?.length && (
        <Empty
          icon={<IconUsers size={24} />}
          action={
            <Button size="sm" onClick={() => setOpen(true)} icon={<IconPlus size={15} />}>
              Thêm clone đầu tiên
            </Button>
          }
        >
          Chưa có tài khoản clone nào. Hãy thêm clone để hệ thống bắt đầu quy trình ủ ấm và sẵn sàng săn lead.
        </Empty>
      )}

      {!loading && data && data.length > 0 && filteredClones.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-200 p-8 text-center text-xs text-slate-500 dark:border-slate-800">
          Không có tài khoản nào thuộc nhóm nhiệm vụ này.
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {filteredClones.map((clone) => (
          <CloneCard
            key={clone.id}
            clone={clone}
            onChanged={reload}
            onTimeline={() => setTimelineFor(clone)}
            onDiagnosis={setDiagnosis}
          />
        ))}
      </div>

      <Modal
        open={open}
        title="Thêm tài khoản Clone mới"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Hủy
            </Button>
            <Button onClick={create} disabled={!form.display_name.trim()}>
              Tạo tài khoản
            </Button>
          </>
        }
      >
        <ErrorNote>{formError}</ErrorNote>
        <Field label="Tên gợi nhớ (Nick)">
          <Input
            value={form.display_name}
            placeholder="VD: Nick 1 - Quét lead hoặc Nick 2 - Cmt..."
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
          />
        </Field>

        <Field label="Vai trò / Nhiệm vụ đảm nhiệm" hint="Mỗi nick nên giữ 1 nhiệm vụ độc lập để giảm thiểu tỷ lệ checkpoint.">
          <Select
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value as CloneRole })}
          >
            <option value="scout">🔍 Quét bài (Scout) — Chỉ do thám & săn lead từ nhóm</option>
            <option value="shooter">💬 Cmt bài (Shooter) — Chuyên ứng tuyển & bình luận</option>
            <option value="poster">📢 Đăng bài (Poster) — Chuyên đăng bài seeding vào nhóm</option>
            <option value="all">⚡ Đa nhiệm (All) — Cả quét bài, cmt bài và đăng bài</option>
            <option value="both">🔄 Quét & Cmt (Both) — Vừa do thám vừa ứng tuyển</option>
          </Select>
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          {["shooter", "both", "all"].includes(form.role) && (
            <Field label="Trần comment/ngày" hint="Tối đa 200 cmt">
              <Input
                type="number"
                min={1}
                max={200}
                value={form.daily_comment_limit}
                onChange={(e) => setForm({ ...form, daily_comment_limit: Number(e.target.value) })}
              />
            </Field>
          )}
          {["poster", "all"].includes(form.role) && (
            <Field label="Trần đăng bài/ngày" hint="Khuyên dùng 3-10 bài">
              <Input
                type="number"
                min={1}
                max={50}
                value={form.daily_post_limit}
                onChange={(e) => setForm({ ...form, daily_post_limit: Number(e.target.value) })}
              />
            </Field>
          )}
        </div>

        <Field label="Proxy riêng (tuỳ chọn)" hint="Bỏ trống để dùng proxy pool chung của hệ thống.">
          <Input
            value={form.proxy_address}
            placeholder="socks5://user:pass@host:port"
            onChange={(e) => setForm({ ...form, proxy_address: e.target.value })}
          />
        </Field>
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input
            type="checkbox"
            checked={form.is_backup}
            onChange={(e) => setForm({ ...form, is_backup: e.target.checked })}
          />
          Dùng làm clone dự phòng (tự động thay thế khi nick cùng vai trò dính checkpoint)
        </label>
      </Modal>

      <TimelineModal clone={timelineFor} onClose={() => setTimelineFor(null)} />

      <Modal
        open={!!diagnosis}
        title={`Chẩn đoán: ${diagnosis?.display_name ?? ""}`}
        onClose={() => setDiagnosis(null)}
      >
        {diagnosis && (
          <DiagnosisPanel
            report={diagnosis}
            onRecheck={async () => {
              setDiagnosis(await api.checkSession(diagnosis.clone_id));
              reload();
            }}
          />
        )}
      </Modal>
    </div>
  );
}

function CloneCard({
  clone,
  onChanged,
  onTimeline,
  onDiagnosis,
}: {
  clone: Clone;
  onChanged: () => void;
  onTimeline: () => void;
  onDiagnosis: (report: CloneDiagnosis) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const events = MANUAL_EVENTS[clone.status] ?? [];

  // Điểm sức khỏe đọc riêng cho từng thẻ: nhẹ, và luôn khớp với backend.
  const health = useAsync(() => api.diagnoseClone(clone.id), [clone.id, clone.status]);

  async function upload(file: File) {
    setError("");
    setMessage("");
    try {
      const result = await api.uploadCookie(clone.id, file);
      const life =
        result.days_left === null
          ? "cookie phiên (file không ghi hạn dùng)"
          : `còn ${result.days_left} ngày`;
      setMessage(
        `Đã nhận ${result.cookie_count} cookie (UID ${result.fb_user_id}), ${life}. ` +
          `Trạng thái: ${result.status}.`,
      );
      onChanged();
      health.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload cookie thất bại");
    }
  }

  async function transition(event: string) {
    setError("");
    try {
      await api.transitionClone(clone.id, event, "Thao tác tay từ dashboard");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chuyển trạng thái thất bại");
    }
  }

  const quotaPercent = (clone.daily_comment_count / Math.max(1, clone.daily_comment_limit)) * 100;

  return (
    <Card
      title={
        <span className="flex flex-wrap items-center gap-1.5">
          <span className="font-semibold text-slate-900 dark:text-white">{clone.display_name}</span>
          <Badge value={clone.role} />
          <Badge value={clone.status} />
          {clone.is_backup && <Badge value="paused">Dự phòng</Badge>}
        </span>
      }
      action={
        health.data ? (
          <ScoreRing score={health.data.score} grade={health.data.grade} size="sm" />
        ) : (
          <Badge value={clone.role} />
        )
      }
    >
      <ErrorNote>{error}</ErrorNote>
      {message && <p className="mb-2 text-sm text-emerald-600">{message}</p>}

      <div className="space-y-3 text-sm">
        {["shooter", "both", "all"].includes(clone.role) && (
          <div>
            <p className="mb-1 flex justify-between text-xs text-slate-500">
              <span>💬 Quota comment hôm nay</span>
              <span>
                {clone.daily_comment_count}/{clone.daily_comment_limit}
              </span>
            </p>
            <Progress percent={quotaPercent} />
          </div>
        )}

        {["poster", "all"].includes(clone.role) && (
          <div>
            <p className="mb-1 flex justify-between text-xs text-slate-500">
              <span>📢 Quota đăng bài hôm nay</span>
              <span>
                {clone.daily_post_count || 0}/{clone.daily_post_limit || 5} bài
              </span>
            </p>
            <Progress
              percent={
                ((clone.daily_post_count || 0) / Math.max(1, clone.daily_post_limit || 5)) * 100
              }
            />
          </div>
        )}

        {clone.role === "scout" && (
          <div className="rounded-lg border border-cyan-200/70 bg-cyan-50/60 p-2.5 text-xs text-cyan-900 dark:border-cyan-900/50 dark:bg-cyan-950/30 dark:text-cyan-300">
            🔍 <strong>Nick chuyên trách do thám:</strong> Tự động quét và phát hiện bài viết tiềm
            năng từ các nhóm mục tiêu mà không tương tác bình luận hay đăng bài.
          </div>
        )}

        {clone.status === "warming_up" && (
          <div>
            <p className="mb-1 text-xs text-slate-500">Tiến trình ủ ấm: ngày {clone.warmup_day}/7</p>
            <Progress percent={(clone.warmup_day / 7) * 100} />
          </div>
        )}

        {health.data?.issues[0] && (
          <p
            className={cx(
              "rounded-lg px-3 py-2 text-xs",
              health.data.issues[0].severity === "critical"
                ? "bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-300"
                : "bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300",
            )}
          >
            {health.data.issues[0].message}
            {health.data.issues.length > 1 && ` (+${health.data.issues.length - 1} mục khác)`}
          </p>
        )}

        <dl className="grid grid-cols-2 gap-1 text-xs text-slate-500">
          <dt>Cookie</dt>
          <dd className="text-right">{describeCookieShort(health.data, clone.has_cookies)}</dd>
          <dt>Proxy</dt>
          <dd className="truncate text-right">{clone.proxy_address || "Chưa gán"}</dd>
          <dt>Lỗi liên tiếp</dt>
          <dd className="text-right">{clone.consecutive_failures}</dd>
          <dt>Hoạt động cuối</dt>
          <dd className="text-right">{fmtDate(clone.last_activity_at)}</dd>
          {clone.cooldown_until && (
            <>
              <dt>Nghỉ đến</dt>
              <dd className="text-right">{fmtDate(clone.cooldown_until)}</dd>
            </>
          )}
        </dl>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <input
          ref={fileInput}
          type="file"
          accept=".json,.txt"
          hidden
          onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
        />
        <Button size="sm" variant="ghost" onClick={() => fileInput.current?.click()}>
          Nạp cookie
        </Button>
        <Button
          size="sm"
          variant="subtle"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              onDiagnosis(await api.checkSession(clone.id));
              onChanged();
              health.reload();
            } catch (err) {
              setError(err instanceof Error ? err.message : "Kiểm tra thất bại");
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Đang kiểm tra…" : "Kiểm tra tài khoản"}
        </Button>
        {health.data && (
          <Button size="sm" variant="ghost" onClick={() => onDiagnosis(health.data!)}>
            Chẩn đoán
          </Button>
        )}
        <Button size="sm" variant="subtle" onClick={onTimeline}>
          Nhật ký
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={async () => {
            try {
              await api.assignProxy(clone.id);
              onChanged();
            } catch (err) {
              setError(err instanceof Error ? err.message : "Không gán được proxy");
            }
          }}
        >
          Gán proxy
        </Button>
        <Button
          size="sm"
          variant="danger"
          onClick={async () => {
            if (!confirm(`Xóa clone "${clone.display_name}"?`)) return;
            await api.deleteClone(clone.id);
            onChanged();
          }}
        >
          Xóa
        </Button>
      </div>

      {!!events.length && (
        <div className="mt-3 flex flex-wrap gap-2 border-t border-slate-200 pt-3 dark:border-slate-800">
          {events.map((item) => (
            <Button
              key={item.event}
              size="sm"
              variant="ghost"
              onClick={() => transition(item.event)}
            >
              {item.label}
            </Button>
          ))}
        </div>
      )}
    </Card>
  );
}

/** Một dòng ngắn về cookie: còn hạn bao lâu — thứ quyết định clone sống hay chết. */
function describeCookieShort(report: CloneDiagnosis | null, hasCookies: boolean): string {
  if (!report) return hasCookies ? "Đã nạp" : "Chưa có";
  if (!report.cookie_ok) return "Hỏng / thiếu";
  if (report.cookie_days_left === null) return "Hợp lệ (không rõ hạn)";
  return `Còn ${report.cookie_days_left} ngày`;
}

function TimelineModal({ clone, onClose }: { clone: Clone | null; onClose: () => void }) {
  const timeline = useAsync(
    () => (clone ? api.healthTimeline(clone.id, 50) : Promise.resolve([])),
    [clone?.id ?? ""],
  );

  return (
    <Modal open={!!clone} title={`Nhật ký: ${clone?.display_name ?? ""}`} onClose={onClose}>
      {timeline.loading && <Spinner />}
      {!timeline.loading && !timeline.data?.length && <Empty>Chưa có sự kiện nào.</Empty>}
      <ol className="space-y-2">
        {timeline.data?.map((event) => (
          <li key={event.id} className="border-l-2 border-slate-200 pl-3 dark:border-slate-700">
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <Badge value={event.to_state ?? event.event_type} />
              <span>{fmtDate(event.created_at)}</span>
              {event.from_state && (
                <span>
                  {event.from_state} → {event.to_state}
                </span>
              )}
            </div>
            <p className="text-sm">{event.details}</p>
          </li>
        ))}
      </ol>
    </Modal>
  );
}
