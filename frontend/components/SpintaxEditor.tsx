"use client";
/**
 * Trình soạn thảo comment xoay.
 *
 * Ba việc nó làm cho người dùng:
 *   1. Gõ nhanh  — thanh công cụ bọc nhóm xoay, thêm lựa chọn, chèn mẫu sẵn.
 *   2. Thấy ngay — số biến thể, số nhóm và câu mẫu cập nhật tức thì khi gõ.
 *   3. Không trùng — cảnh báo từ server (link, câu quá ngắn, lựa chọn lặp)
 *      cùng chỉ số "chạy được bao nhiêu ngày mới phải lặp lại".
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Badge, Button, Empty, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { bracesBalanced, countVariants, parseGroups, sampleVariants, tokenize } from "@/lib/spintax";
import type { LintReport } from "@/lib/types";

/** Mẫu chèn nhanh — toàn câu đã bỏ link, đúng luật chống spam của backend. */
const SNIPPETS: { label: string; text: string }[] = [
  { label: "Lời chào", text: "{Chào bạn|Hi bạn|Chào bạn nhé}" },
  { label: "Nhận việc", text: "{mình nhận|bên mình nhận|mình đang nhận}" },
  { label: "Mời nhắn tin", text: "{bạn inbox mình nhé|bạn nhắn riêng cho mình nhé|bạn cứ nhắn mình nha}" },
  { label: "Mời xem mẫu", text: "{mình gửi bạn vài mẫu tham khảo|mình có sẵn mẫu để bạn xem thử}" },
  { label: "Kết câu", text: "{ạ|nhé|nha}" },
];

interface Props {
  campaignId: string;
  value: string;
  onChange: (value: string) => void;
  /** Trần comment/ngày của chiến dịch — để quy ra "bao nhiêu ngày không lặp". */
  maxCommentsPerDay?: number;
}

export function SpintaxEditor({ campaignId, value, onChange, maxCommentsPerDay = 20 }: Props) {
  const textarea = useRef<HTMLTextAreaElement>(null);
  const [seed, setSeed] = useState(() => Date.now());
  const [lint, setLint] = useState<LintReport | null>(null);
  const [linting, setLinting] = useState(false);

  // ── Thống kê tức thì (thuần client, không chờ mạng) ──────────────────
  const balanced = bracesBalanced(value);
  const groups = useMemo(() => (balanced ? parseGroups(value) : []), [value, balanced]);
  const variants = useMemo(() => (balanced ? countVariants(value) : 0), [value, balanced]);
  const samples = useMemo(
    () => (balanced ? sampleVariants(value, 4, seed) : []),
    [value, balanced, seed],
  );
  const daysWithoutRepeat = variants / Math.max(1, maxCommentsPerDay);

  // ── Cảnh báo lấy từ server (một nguồn sự thật duy nhất) ──────────────
  useEffect(() => {
    if (!value.trim()) {
      setLint(null);
      return;
    }
    let alive = true;
    setLinting(true);
    const timer = setTimeout(() => {
      api
        .lintDraft(campaignId, value)
        .then((report) => alive && setLint(report))
        .catch(() => alive && setLint(null))
        .finally(() => alive && setLinting(false));
    }, 400);
    return () => {
      alive = false;
      clearTimeout(timer);
      setLinting(false);
    };
  }, [value, campaignId]);

  // ── Thao tác trên vùng chọn ──────────────────────────────────────────
  const applyEdit = useCallback(
    (next: string, caret: number) => {
      onChange(next);
      requestAnimationFrame(() => {
        const node = textarea.current;
        if (!node) return;
        node.focus();
        node.setSelectionRange(caret, caret);
      });
    },
    [onChange],
  );

  /** Bọc đoạn đang bôi đen thành một nhóm xoay, sẵn chỗ gõ lựa chọn thứ hai. */
  function wrapSelection() {
    const node = textarea.current;
    if (!node) return;
    const { selectionStart: start, selectionEnd: end } = node;
    const picked = value.slice(start, end).trim();
    if (!picked) {
      const insert = "{lựa chọn A|lựa chọn B}";
      applyEdit(value.slice(0, start) + insert + value.slice(end), start + 1);
      return;
    }
    const insert = `{${picked}|}`;
    // Con trỏ nhảy đúng sau dấu | để gõ tiếp phương án thứ hai.
    applyEdit(value.slice(0, start) + insert + value.slice(end), start + picked.length + 2);
  }

  /** Thêm một lựa chọn nữa vào nhóm đang đứng trong. */
  function addAlternative() {
    const node = textarea.current;
    if (!node) return;
    const caret = node.selectionStart;
    const open = value.lastIndexOf("{", caret - 1);
    const close = value.indexOf("}", caret);
    if (open === -1 || close === -1) {
      applyEdit(value.slice(0, caret) + "{A|B}" + value.slice(caret), caret + 1);
      return;
    }
    applyEdit(value.slice(0, close) + "|" + value.slice(close), close + 1);
  }

  function insertSnippet(text: string) {
    const node = textarea.current;
    const caret = node ? node.selectionStart : value.length;
    const needsSpace = caret > 0 && !/\s$/.test(value.slice(0, caret));
    const insert = (needsSpace ? " " : "") + text;
    applyEdit(value.slice(0, caret) + insert + value.slice(caret), caret + insert.length);
  }

  const errors = lint?.issues.filter((issue) => issue.level === "error") ?? [];
  const warnings = lint?.issues.filter((issue) => issue.level === "warning") ?? [];

  const diversityTone =
    variants >= 50 ? "good" : variants >= 10 ? "warn" : variants > 0 ? "bad" : "muted";

  return (
    <div className="space-y-3">
      {/* Thanh công cụ */}
      <div className="flex flex-wrap items-center gap-1.5">
        <Button size="sm" variant="ghost" type="button" onClick={wrapSelection}>
          {"{ } Bọc thành nhóm xoay"}
        </Button>
        <Button size="sm" variant="ghost" type="button" onClick={addAlternative}>
          | Thêm lựa chọn
        </Button>
        <span className="mx-1 h-4 w-px bg-slate-300 dark:bg-slate-700" />
        {SNIPPETS.map((snippet) => (
          <Button
            key={snippet.label}
            size="sm"
            variant="subtle"
            type="button"
            title={snippet.text}
            onClick={() => insertSnippet(snippet.text)}
          >
            + {snippet.label}
          </Button>
        ))}
      </div>

      <textarea
        ref={textarea}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        spellCheck={false}
        placeholder="Ví dụ: {Chào bạn|Hi bạn}, {mình nhận|bên mình nhận} viết thể loại này, bạn inbox mình nhé"
        className={cx(
          "min-h-36 w-full rounded-lg border bg-white px-3 py-2 font-mono text-sm leading-relaxed text-slate-900 outline-none transition dark:bg-slate-950 dark:text-slate-100",
          balanced
            ? "border-slate-300 focus:border-slate-500 dark:border-slate-700"
            : "border-rose-400 focus:border-rose-500",
        )}
      />

      {/* Dải chỉ số */}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Metric label="Nhóm xoay" value={groups.length} />
        <Metric label="Biến thể" value={variants.toLocaleString("vi-VN")} tone={diversityTone} />
        <Metric
          label="Ngày chưa phải lặp"
          value={daysWithoutRepeat >= 100 ? "99+" : daysWithoutRepeat.toFixed(1)}
          tone={daysWithoutRepeat >= 3 ? "good" : daysWithoutRepeat >= 1 ? "warn" : "bad"}
        />
        {lint && (
          <Metric label="Số từ" value={`${lint.shortest_words}–${lint.longest_words}`} />
        )}
        {linting && <span className="text-slate-400">đang kiểm tra…</span>}
      </div>

      {!balanced && (
        <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
          Ngoặc đang lệch — mỗi nhóm xoay cần đủ một dấu {"{"} và một dấu {"}"}.
        </p>
      )}

      {/* Lỗi & cảnh báo từ server */}
      {!!errors.length && (
        <ul className="space-y-1 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
          {errors.map((issue, index) => (
            <li key={index}>⛔ {issue.message}</li>
          ))}
        </ul>
      )}
      {!!warnings.length && (
        <ul className="space-y-1 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
          {warnings.map((issue, index) => (
            <li key={index}>⚠️ {issue.message}</li>
          ))}
        </ul>
      )}
      {lint?.ok && !warnings.length && (
        <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
          ✅ Mẫu hợp lệ, không có link, các biến thể đủ dài.
        </p>
      )}

      {/* Cấu trúc nhóm */}
      {!!groups.length && (
        <details className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-800">
          <summary className="cursor-pointer text-xs font-medium text-slate-600 dark:text-slate-400">
            Cấu trúc {groups.length} nhóm xoay
          </summary>
          <ul className="mt-2 space-y-1.5">
            {groups.map((options, index) => (
              <li key={index} className="flex flex-wrap items-center gap-1">
                <span className="mr-1 text-xs text-slate-400">#{index + 1}</span>
                {options.map((option, position) => (
                  <span
                    key={position}
                    className={cx(
                      "rounded px-1.5 py-0.5 text-xs",
                      option.trim()
                        ? "bg-slate-100 dark:bg-slate-800"
                        : "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
                    )}
                  >
                    {option.trim() || "(rỗng)"}
                  </span>
                ))}
              </li>
            ))}
          </ul>
        </details>
      )}

      {/* Xem trước */}
      <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
            Xem trước — mỗi lần bắn sẽ ra một câu khác nhau
          </span>
          <Button size="sm" variant="subtle" type="button" onClick={() => setSeed(Date.now())}>
            ⟳ Sinh lại
          </Button>
        </div>
        {!samples.length ? (
          <Empty>Gõ mẫu vào ô trên để xem trước.</Empty>
        ) : (
          <ul className="space-y-1.5">
            {samples.map((sample, index) => (
              <li
                key={index}
                className="rounded bg-slate-50 px-3 py-2 text-sm dark:bg-slate-800/60"
              >
                {sample}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  tone = "muted",
}: {
  label: string;
  value: string | number;
  tone?: "good" | "warn" | "bad" | "muted";
}) {
  const tones = {
    good: "text-emerald-700 bg-emerald-50 dark:text-emerald-300 dark:bg-emerald-950/50",
    warn: "text-amber-700 bg-amber-50 dark:text-amber-300 dark:bg-amber-950/50",
    bad: "text-rose-700 bg-rose-50 dark:text-rose-300 dark:bg-rose-950/50",
    muted: "text-slate-600 bg-slate-100 dark:text-slate-300 dark:bg-slate-800",
  };
  return (
    <span className={cx("rounded-full px-2.5 py-1 font-medium", tones[tone])}>
      {label}: <span className="tabular-nums">{value}</span>
    </span>
  );
}

/** Xem toàn bộ biến thể của một kịch bản đã lưu (gọi server, có phân trang cứng). */
export function VariantExplorer({
  campaignId,
  scriptId,
}: {
  campaignId: string;
  scriptId: string;
}) {
  const [state, setState] = useState<{
    variants: string[];
    total: number;
    truncated: boolean;
  } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setBusy(true);
    setError("");
    try {
      const result = await api.expandScript(campaignId, scriptId);
      setState({
        variants: result.variants,
        total: result.total_variants,
        truncated: result.truncated,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không liệt kê được biến thể");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <Button size="sm" variant="subtle" type="button" onClick={load} disabled={busy}>
        {busy ? "Đang liệt kê…" : "Xem tất cả biến thể"}
      </Button>
      {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}
      {state && (
        <div className="mt-3">
          <p className="mb-2 text-xs text-slate-500">
            {state.total.toLocaleString("vi-VN")} biến thể
            {state.truncated && <> — hiển thị {state.variants.length} câu đầu</>}
          </p>
          <ol className="max-h-72 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2 dark:border-slate-800">
            {state.variants.map((variant, index) => (
              <li key={index} className="flex gap-2 text-sm">
                <span className="w-8 shrink-0 text-right text-xs text-slate-400">{index + 1}</span>
                <span>{variant}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

/** Nhãn nhỏ hiển thị vòng xoay của một kịch bản trong danh sách. */
export function RotationBadge({ usage, lastUsed }: { usage: number; lastUsed: string | null }) {
  return (
    <Badge value={usage > 0 ? "assigned" : "available"}>
      {usage > 0 ? `đã dùng ${usage} lần` : "chưa dùng"}
      {lastUsed ? ` · ${new Date(lastUsed).toLocaleDateString("vi-VN")}` : ""}
    </Badge>
  );
}
