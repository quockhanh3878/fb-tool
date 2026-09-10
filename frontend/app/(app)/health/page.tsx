"use client";
import { useState } from "react";

import { DiagnosisPanel, IssueList, ScoreRing } from "@/components/AccountHealth";
import {
  IconAlertTriangle,
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
  Stat,
  fmtDate,
  useAsync,
  useToast,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { CloneDiagnosis } from "@/lib/types";

export default function HealthPage() {
  const summary = useAsync(() => api.healthSummary());
  const diagnostics = useAsync(() => api.healthDiagnostics());
  const overview = useAsync(() => api.healthOverview());
  const alerts = useAsync(() => api.alerts());
  const proxies = useAsync(() => api.proxies());
  const pool = useAsync(() => api.proxyOverview());

  const [proxyForm, setProxyForm] = useState({ address: "", type: "residential", country: "VN" });
  const [proxyError, setProxyError] = useState("");
  const [detail, setDetail] = useState<CloneDiagnosis | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkNote, setCheckNote] = useState("");

  const byClone = new Map((diagnostics.data ?? []).map((item) => [item.clone_id, item]));

  function reloadHealth() {
    summary.reload();
    diagnostics.reload();
    overview.reload();
    alerts.reload();
  }

  const toast = useToast();

  /** Kiểm tra toàn bộ clone: vừa chấm điểm vừa hạ trạng thái clone có cookie hỏng. */
  async function checkAll() {
    setChecking(true);
    setCheckNote("");
    try {
      const result = await api.checkAllClones();
      const bad = result.summary.critical_count;
      setCheckNote(
        result.transitioned.length
          ? `Đã kiểm tra ${result.reports.length} clone. ${result.transitioned.length} clone bị chuyển sang checkpoint vì cookie hỏng: ${result.transitioned.join(", ")}.`
          : `Đã kiểm tra ${result.reports.length} clone — không clone nào phải hạ trạng thái.`,
      );
      toast.info(`Đã kiểm tra ${result.reports.length} clone. ${result.summary.ready_count} clone sẵn sàng.`);
      reloadHealth();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Kiểm tra thất bại";
      setCheckNote(msg);
      toast.error(msg);
    } finally {
      setChecking(false);
    }
  }

  async function addProxy() {
    setProxyError("");
    try {
      await api.addProxy(proxyForm);
      setProxyForm({ address: "", type: "residential", country: "VN" });
      toast.success("Đã thêm proxy vào pool thành công!", "Thành công");
      proxies.reload();
      pool.reload();
    } catch (err) {
      setProxyError(err instanceof Error ? err.message : "Không thêm được proxy");
    }
  }

  const stats = summary.data;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300">
              <IconHeartPulse size={18} />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-2xl">
              Sức khỏe Tài khoản & Proxy
            </h1>
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Hệ thống tự động phát hiện checkpoint, cookie hết hạn, shadowban và tự xoay proxy chết khi bắn comment.
          </p>
        </div>

        <Button
          onClick={checkAll}
          disabled={checking}
          loading={checking}
          icon={<IconRefresh size={14} />}
          size="sm"
        >
          {checking ? "Đang kiểm tra…" : "Kiểm tra toàn bộ"}
        </Button>
      </header>

      {checkNote && (
        <div className="flex items-start gap-2.5 rounded-xl border border-indigo-200/80 bg-indigo-50/70 p-3.5 text-xs text-indigo-950 dark:border-indigo-900/60 dark:bg-indigo-950/40 dark:text-indigo-300">
          <IconShieldCheck size={17} className="text-indigo-600 dark:text-indigo-400 shrink-0 mt-0.5" />
          <p className="leading-relaxed">{checkNote}</p>
        </div>
      )}

      <ErrorNote>{summary.error}</ErrorNote>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Điểm sức khỏe TB"
          value={`${stats?.average_score ?? 0}/100`}
          tone={stats?.grade ?? "default"}
          hint="Điểm trung bình toàn bộ clone"
          icon={<IconHeartPulse size={18} />}
        />
        <Stat
          label="Clone sẵn sàng"
          value={`${stats?.ready_count ?? 0}/${stats?.clone_count ?? 0}`}
          tone={stats && stats.ready_count === stats.clone_count ? "good" : "warn"}
          hint="Đang bật, cookie tốt, còn quota"
          icon={<IconUsers size={18} />}
        />
        <Stat
          label="Còn bắn được hôm nay"
          value={stats?.capacity_left ?? 0}
          tone={stats?.capacity_left ? "good" : "bad"}
          hint={`Đã dùng ${stats?.capacity_used ?? 0}/${stats?.capacity_total ?? 0} lượt`}
          icon={<IconShieldCheck size={18} />}
        />
        <Stat
          label="Vấn đề nghiêm trọng"
          value={stats?.critical_count ?? 0}
          tone={stats?.critical_count ? "bad" : "good"}
          hint={`${stats?.warning_count ?? 0} cảnh báo · ${stats?.unacknowledged_alerts ?? 0} chưa xử lý`}
          icon={<IconAlertTriangle size={18} />}
        />
      </div>

      {!!stats?.top_issues.length && (
        <Card title="Việc cần làm">
          <p className="mb-3 text-sm text-slate-600 dark:text-slate-400">
            Gộp theo loại vấn đề, nặng trước. Xử lý từ trên xuống là nhanh nhất.
          </p>
          <IssueList issues={stats.top_issues} />
        </Card>
      )}

      <Card title="Tình trạng từng clone">
        <ErrorNote>{overview.error}</ErrorNote>
        {overview.loading && <Spinner />}
        {!overview.loading && !overview.data?.length && <Empty>Chưa có clone nào.</Empty>}
        <div className="space-y-3">
          {overview.data?.map((clone) => {
            const report = byClone.get(clone.id);
            const worst = report?.issues[0];
            return (
              <div
                key={clone.id}
                className="rounded-lg border border-slate-200 p-3 dark:border-slate-800"
              >
                <div className="flex items-start gap-3">
                  {report && <ScoreRing score={report.score} grade={report.grade} size="sm" />}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="flex items-center gap-2 text-sm font-medium">
                        {clone.display_name}
                        <Badge value={clone.status} />
                        {report?.ready === false && (
                          <span className="text-xs text-slate-500">chưa nhận việc được</span>
                        )}
                      </span>
                      <span className="text-xs text-slate-500">
                        {clone.daily_comment_count}/{clone.daily_comment_limit} comment ·{" "}
                        {clone.consecutive_failures} lỗi liên tiếp
                      </span>
                    </div>

                    {worst && (
                      <p className="mt-1 truncate text-xs text-slate-500">
                        {worst.message}
                        {report && report.issues.length > 1 && ` (+${report.issues.length - 1})`}
                      </p>
                    )}
                  </div>
                </div>

                {clone.status === "warming_up" && (
                  <div className="mt-2">
                    <Progress
                      percent={clone.warmup.percent}
                      label={`Ủ ấm ngày ${clone.warmup.day}/${clone.warmup.total_days} — tiếp theo: ${clone.warmup.next_step}`}
                    />
                  </div>
                )}

                <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-500">
                  <span>Proxy: {clone.proxy_address || "chưa gán"}</span>
                  {clone.cooldown_until && <span>Nghỉ đến {fmtDate(clone.cooldown_until)}</span>}
                </div>

                <div className="mt-2 flex flex-wrap gap-2">
                  {report && (
                    <Button size="sm" variant="subtle" onClick={() => setDetail(report)}>
                      Chẩn đoán
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={async () => {
                      try {
                        await api.rotateProxy(clone.id, "manual");
                        proxies.reload();
                        reloadHealth();
                      } catch (err) {
                        alert(err instanceof Error ? err.message : "Không xoay được proxy");
                      }
                    }}
                  >
                    Xoay proxy
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={async () => {
                      try {
                        setDetail(await api.checkSession(clone.id));
                        reloadHealth();
                      } catch (err) {
                        alert(err instanceof Error ? err.message : "Kiểm tra thất bại");
                      }
                    }}
                  >
                    Kiểm tra phiên
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <Card
        title={`Cảnh báo (${alerts.data?.length ?? 0})`}
        action={
          !!alerts.data?.length && (
            <Button
              size="sm"
              variant="subtle"
              onClick={async () => {
                await api.ackAllAlerts();
                reloadHealth();
              }}
            >
              Đánh dấu đã xử lý tất cả
            </Button>
          )
        }
      >
        {alerts.loading && <Spinner />}
        {!alerts.loading && !alerts.data?.length && <Empty>Không có cảnh báo nào.</Empty>}
        <ul className="space-y-2">
          {alerts.data?.map((event) => (
            <li
              key={event.id}
              className="flex flex-wrap items-start justify-between gap-2 rounded-lg border border-slate-200 p-3 dark:border-slate-800"
            >
              <div>
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <Badge value={event.to_state ?? event.event_type} />
                  <span>{fmtDate(event.created_at)}</span>
                </div>
                <p className="mt-1 text-sm">{event.details}</p>
              </div>
              <Button
                size="sm"
                variant="subtle"
                onClick={async () => {
                  await api.ackAlert(event.id);
                  reloadHealth();
                }}
              >
                Đã xử lý
              </Button>
            </li>
          ))}
        </ul>
      </Card>

      <Card title={`Kho proxy (${proxies.data?.length ?? 0})`}>
        <ErrorNote>{proxyError}</ErrorNote>
        <div className="grid gap-3 sm:grid-cols-[2fr_1fr_1fr_auto] sm:items-end">
          <Field label="Địa chỉ proxy">
            <Input
              value={proxyForm.address}
              placeholder="socks5://user:pass@host:port"
              onChange={(e) => setProxyForm({ ...proxyForm, address: e.target.value })}
            />
          </Field>
          <Field label="Loại">
            <Select
              value={proxyForm.type}
              onChange={(e) => setProxyForm({ ...proxyForm, type: e.target.value })}
            >
              <option value="residential">Dân cư (an toàn nhất)</option>
              <option value="mobile">4G/di động</option>
              <option value="datacenter">Datacenter</option>
            </Select>
          </Field>
          <Field label="Quốc gia">
            <Input
              value={proxyForm.country}
              onChange={(e) => setProxyForm({ ...proxyForm, country: e.target.value })}
            />
          </Field>
          <Button onClick={addProxy} disabled={!proxyForm.address.trim()}>
            Thêm
          </Button>
        </div>

        {!proxies.data?.length ? (
          <div className="mt-4">
            <Empty>Kho proxy trống — clone sẽ chạy bằng IP máy chủ.</Empty>
          </div>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Địa chỉ</th>
                  <th>Loại</th>
                  <th>Trạng thái</th>
                  <th>Khỏe?</th>
                  <th>Kiểm tra cuối</th>
                </tr>
              </thead>
              <tbody>
                {proxies.data.map((proxy) => (
                  <tr key={proxy.id}>
                    <td className="font-mono text-xs">{proxy.address}</td>
                    <td>
                      {proxy.type} · {proxy.country}
                    </td>
                    <td>
                      <Badge value={proxy.status} />
                    </td>
                    <td>
                      {proxy.is_healthy ? (
                        <span className="inline-flex items-center gap-1 font-semibold text-emerald-600 dark:text-emerald-400">
                          <IconCheck size={14} />
                          Tốt
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 font-semibold text-rose-600 dark:text-rose-400">
                          <IconAlertTriangle size={14} />
                          Lỗi
                        </span>
                      )}
                    </td>
                    <td className="text-xs text-slate-500">{fmtDate(proxy.last_health_check)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal
        open={!!detail}
        title={`Chẩn đoán sức khỏe: ${detail?.display_name ?? ""}`}
        onClose={() => setDetail(null)}
      >
        {detail && (
          <DiagnosisPanel
            report={detail}
            onRecheck={async () => {
              setDetail(await api.checkSession(detail.clone_id));
              reloadHealth();
            }}
          />
        )}
      </Modal>
    </div>
  );
}
