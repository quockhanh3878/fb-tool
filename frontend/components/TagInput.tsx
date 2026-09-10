"use client";
/**
 * Ô nhập danh sách dạng thẻ (từ khoá, câu bump…).
 *
 * Thay cho textarea ngăn cách bằng dấu phẩy: người dùng thấy rõ từng mục,
 * xoá được từng cái, và không bao giờ vô tình tạo mục rỗng hay trùng lặp.
 */
import { useState } from "react";

import { cx } from "@/components/ui";

interface Props {
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  /** Cảnh báo nhẹ khi thêm mục đã có (không chặn, chỉ nhắc). */
  tone?: "neutral" | "positive" | "negative";
}

export function TagInput({ value, onChange, placeholder, tone = "neutral" }: Props) {
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState("");

  const tones = {
    neutral: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
    positive: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
    negative: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300",
  };

  function commit(raw: string) {
    // Dán cả cụm "a, b, c" cũng tách ra thành nhiều thẻ.
    const items = raw
      .split(/[,\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (!items.length) return;

    const existing = new Set(value.map((item) => item.toLowerCase()));
    const added: string[] = [];
    const duplicates: string[] = [];
    for (const item of items) {
      if (existing.has(item.toLowerCase())) duplicates.push(item);
      else {
        existing.add(item.toLowerCase());
        added.push(item);
      }
    }
    if (added.length) onChange([...value, ...added]);
    setNote(duplicates.length ? `Đã có sẵn: ${duplicates.join(", ")}` : "");
    setDraft("");
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      commit(draft);
    } else if (event.key === "Backspace" && !draft && value.length) {
      // Backspace ở ô rỗng thì xoá thẻ cuối — thói quen quen thuộc.
      onChange(value.slice(0, -1));
    }
  }

  return (
    <div>
      <div className="flex flex-wrap gap-1.5 rounded-lg border border-slate-300 bg-white p-2 focus-within:border-slate-500 dark:border-slate-700 dark:bg-slate-950">
        {value.map((item, index) => (
          <span
            key={`${item}-${index}`}
            className={cx(
              "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs",
              tones[tone],
            )}
          >
            {item}
            <button
              type="button"
              aria-label={`Xoá ${item}`}
              className="opacity-60 hover:opacity-100"
              onClick={() => onChange(value.filter((_, position) => position !== index))}
            >
              ✕
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          onBlur={() => commit(draft)}
          placeholder={value.length ? "" : placeholder}
          className="min-w-32 flex-1 bg-transparent px-1 text-sm outline-none"
        />
      </div>
      <p className="mt-1 text-xs text-slate-500">
        {note || "Gõ xong nhấn Enter hoặc dấu phẩy để thêm. Dán được cả danh sách."}
      </p>
    </div>
  );
}

/**
 * Danh sách câu nhiều dòng (dùng cho nội dung bump).
 * Khác TagInput ở chỗ mỗi mục là cả một câu nên hiển thị theo hàng, sửa tại chỗ.
 */
export function LineListInput({
  value,
  onChange,
  placeholder,
  renderHint,
}: {
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  /** Chú thích riêng cho từng dòng, ví dụ số biến thể spintax của câu đó. */
  renderHint?: (line: string) => string;
}) {
  const [draft, setDraft] = useState("");

  function add() {
    const text = draft.trim();
    if (!text) return;
    if (value.some((line) => line.trim().toLowerCase() === text.toLowerCase())) {
      setDraft("");
      return;
    }
    onChange([...value, text]);
    setDraft("");
  }

  return (
    <div className="space-y-2">
      {value.map((line, index) => (
        <div key={index} className="flex items-start gap-2">
          <div className="flex-1">
            <input
              value={line}
              onChange={(event) => {
                const next = [...value];
                next[index] = event.target.value;
                onChange(next);
              }}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500 dark:border-slate-700 dark:bg-slate-950"
            />
            {renderHint && <p className="mt-0.5 text-xs text-slate-500">{renderHint(line)}</p>}
          </div>
          <button
            type="button"
            aria-label="Xoá dòng"
            onClick={() => onChange(value.filter((_, position) => position !== index))}
            className="mt-2 text-slate-400 hover:text-rose-500"
          >
            ✕
          </button>
        </div>
      ))}

      <div className="flex gap-2">
        <input
          value={draft}
          placeholder={placeholder}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              add();
            }
          }}
          className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500 dark:border-slate-700 dark:bg-slate-950"
        />
        <button
          type="button"
          onClick={add}
          className="rounded-lg bg-slate-100 px-3 text-sm hover:bg-slate-200 dark:bg-slate-800"
        >
          Thêm
        </button>
      </div>
    </div>
  );
}
