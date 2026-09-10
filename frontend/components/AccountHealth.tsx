"use client";
/**
 * Các mảnh giao diện dùng chung cho việc kiểm tra tài khoản.
 *
 * Nguyên tắc: mọi luật chấm điểm và mọi lời khuyên đều do backend
 * (`services/account_check.py`) quyết định — phía này chỉ tô màu và sắp xếp.
 * Nhờ vậy nút "Kiểm tra" ở trang Clone và bảng ở trang Sức khỏe không bao giờ
 * nói hai điều khác nhau về cùng một clone.
 */
import { Badge, Button, Empty, cx, fmtDate } from "@/components/ui";
import type { CloneDiagnosis, CloneIssue, IssueDigest } from "@/lib/types";

const GRADE_TONE = {
  good: "text-emerald-600 dark:text-emerald-400",
  warn: "text-amber-600 dark:text-amber-400",
  bad: "text-rose-600 dark:text-rose-400",
} as const;

const GRADE_RING = {
  good: "border-emerald-500",
  warn: "border-amber-500",
  bad: "border-rose-500",
} as const;

const SEVERITY_STYLE: Record<CloneIssue["severity"], { icon: string; box: string; label: string }> =
  {
    critical: {
      icon: "⛔",
      box: "border-rose-200 bg-rose-50 dark:border-rose-900 dark:bg-rose-950/40",
      label: "Nghiêm trọng",
    },
    warning: {
      icon: "⚠️",
      box: "border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/40",
      label: "Cảnh báo",
    },
    info: {
      icon: "ℹ️",
      box: "border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/40",
      label: "Thông tin",
    },
  };

/** Vòng điểm sức khỏe — đọc màu nhanh hơn đọc số. */
export function ScoreRing({
  score,
  grade,
  size = "md",
}: {
  score: number;
  grade: CloneDiagnosis["grade"];
  size?: "sm" | "md";
}) {
  return (
    <div
      className={cx(
        "flex shrink-0 flex-col items-center justify-center rounded-full border-4 font-semibold tabular-nums",
        GRADE_RING[grade],
        GRADE_TONE[grade],
        size === "sm" ? "h-12 w-12 text-sm" : "h-16 w-16 text-lg",
      )}
      title={`Điểm sức khỏe ${score}/100`}
    >
      {score}
      {size === "md" && <span className="text-[10px] font-normal text-slate-500">điểm</span>}
    </div>
  );
}

/** Danh sách vấn đề kèm cách xử lý. Rỗng = mọi thứ ổn, nói thẳng như vậy. */
export function IssueList({ issues }: { issues: (CloneIssue | IssueDigest)[] }) {
  if (!issues.length) {
    return (
      <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
        ✅ Không phát hiện vấn đề nào.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {issues.map((issue) => {
        const style = SEVERITY_STYLE[issue.severity];
        const count = (issue as IssueDigest).count;
        return (
          <li key={issue.code} className={cx("rounded-lg border px-3 py-2 text-sm", style.box)}>
            <p className="font-medium">
              {style.icon} {issue.message}
              {count > 1 && (
                <span className="ml-1 font-normal text-slate-500">({count} clone)</span>
              )}
            </p>
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">→ {issue.hint}</p>
          </li>
        );
      })}
    </ul>
  );
}

/** Phiếu chẩn đoán đầy đủ của một clone. */
export function DiagnosisPanel({
  report,
  onRecheck,
  busy,
}: {
  report: CloneDiagnosis;
  onRecheck?: () => void;
  busy?: boolean;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-start gap-4">
        <ScoreRing score={report.score} grade={report.grade} />
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{report.display_name}</span>
            <Badge value={report.status} />
            {report.ready ? (
              <Badge value="active">Sẵn sàng nhận việc</Badge>
            ) : (
              <Badge value="paused">Chưa nhận việc được</Badge>
            )}
          </div>
          <p className="text-xs text-slate-500">
            Quota {report.daily_comment_count}/{report.daily_comment_limit} · {" "}
            {report.consecutive_failures} lỗi liên tiếp · proxy{" "}
            {report.proxy_address ? "đã gán" : "chưa gán"}
          </p>
          <p className="text-xs text-slate-500">{describeCookie(report)}</p>
        </div>
        {onRecheck && (
          <Button size="sm" variant="subtle" onClick={onRecheck} disabled={busy}>
            {busy ? "Đang kiểm tra…" : "Kiểm tra lại"}
          </Button>
        )}
      </div>

      <IssueList issues={report.issues} />

      <p className="text-xs text-slate-400">Kiểm tra lúc {fmtDate(report.checked_at)}</p>
    </div>
  );
}

/**
 * Câu trạng thái cookie.
 *
 * Cookie phiên không mang hạn dùng, nên nói "không rõ hạn" thay vì bịa ra một
 * con số — người dùng cần biết chỗ nào hệ thống không kiểm chứng được.
 */
export function describeCookie(report: CloneDiagnosis): string {
  if (!report.cookie_ok) return "Cookie: không dùng được";
  if (report.cookie_days_left === null) return "Cookie: hợp lệ (cookie phiên, không rõ hạn)";
  if (report.cookie_days_left <= 0) return "Cookie: đã hết hạn";
  return `Cookie: còn ${report.cookie_days_left} ngày (hết hạn ${fmtDate(report.cookie_expires_at)})`;
}

/** Dòng gọn cho danh sách nhiều clone. */
export function DiagnosisRow({
  report,
  onOpen,
}: {
  report: CloneDiagnosis;
  onOpen?: () => void;
}) {
  const worst = report.issues[0];
  return (
    <div className="flex items-center gap-3 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
      <ScoreRing score={report.score} grade={report.grade} size="sm" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-medium">{report.display_name}</span>
          <Badge value={report.status} />
          {!report.ready && <span className="text-xs text-slate-500">chưa nhận việc được</span>}
        </div>
        <p className="mt-0.5 truncate text-xs text-slate-500">
          {worst ? `${SEVERITY_STYLE[worst.severity].icon} ${worst.message}` : "Không có vấn đề nào"}
          {report.issues.length > 1 && ` (+${report.issues.length - 1} mục khác)`}
        </p>
      </div>
      {onOpen && (
        <Button size="sm" variant="ghost" onClick={onOpen}>
          Chi tiết
        </Button>
      )}
    </div>
  );
}

export function NoClones() {
  return <Empty>Chưa có clone nào để kiểm tra.</Empty>;
}
