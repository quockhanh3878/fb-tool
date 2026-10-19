"use client";
import { useState } from "react";

import {
  IconCheck,
  IconClock,
  IconCopy,
  IconExternalLink,
  IconFacebook,
  IconFilter,
  IconPosts,
  IconSearch,
  IconSparkles,
  IconUsers,
  IconX,
} from "@/components/icons";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorNote,
  Field,
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
import { countVariants, renderSpintax, similarity } from "@/lib/spintax";
import type { CommentHistory, Post } from "@/lib/types";
import { PublishingStudio } from "@/components/PublishingStudio";
import { DEFAULT_COMMENT_TEXT } from "@/lib/defaults";

const STATUSES = [
  { value: "", label: "Tất cả trạng thái" },
  { value: "notified", label: "Đang chờ duyệt" },
  { value: "need_review", label: "Cần người xem" },
  { value: "matched", label: "Khớp tiêu chí" },
  { value: "commented", label: "Đã bình luận" },
  { value: "skipped", label: "Đã bỏ qua" },
  { value: "new", label: "Mới quét" },
];

const PAGE_SIZE = 20;

export default function PostsPage() {
  const campaigns = useAsync(() => api.campaigns());
  const toast = useToast();
  const [tab, setTab] = useState<"discovery" | "publishing">("discovery");
  const [campaignId, setCampaignId] = useState("");
  const [status, setStatus] = useState("notified");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Post | null>(null);

  const posts = useAsync(
    () =>
      api.posts({
        campaign_id: campaignId || undefined,
        status: status || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
    [campaignId, status, offset],
  );

  const queue = useAsync(() => api.queue());
  const commentHistory = useAsync(() => api.commentHistory({ limit: 30 }), []);

  async function skipPost(post: Post) {
    try {
      await api.skipPost(post.id);
      toast.info(`Đã bỏ qua bài viết của ${post.author_name || "tác giả"}`);
      posts.reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Thao tác thất bại");
    }
  }

  return (
    <div className="space-y-6">
      {/* ── HEADER ─────────────────────────────────────────────────────── */}
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
              <IconPosts size={18} />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-2xl">
              Bài viết & Tương tác Nhóm
            </h1>
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Hỗ trợ phân công đa nick: Nick quét bài (Scout), Nick cmt ứng tuyển (Shooter), Nick đăng bài seeding (Poster).
          </p>
        </div>

        {tab === "discovery" && !!queue.data?.length && (
          <div className="flex items-center gap-2 rounded-xl border border-indigo-200/80 bg-indigo-50/80 px-3.5 py-1.5 text-xs font-semibold text-indigo-900 dark:border-indigo-900/60 dark:bg-indigo-950/40 dark:text-indigo-300">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-indigo-600" />
            </span>
            {queue.data.length} comment đang trong hàng đợi bắn
          </div>
        )}
      </header>

      {/* ── DUAL NAVIGATION TABS ────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 pb-3 dark:border-slate-800">
        <button
          type="button"
          onClick={() => setTab("discovery")}
          className={cx(
            "inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold transition-all cursor-pointer",
            tab === "discovery"
              ? "bg-indigo-600 text-white shadow-sm dark:bg-indigo-500"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700",
          )}
        >
          <IconSearch size={15} />
          <span>Săn lead & Ứng tuyển (Scout & Shooter)</span>
          {posts.data?.total !== undefined && (
            <span
              className={cx(
                "rounded-full px-2 py-0.5 text-[10px]",
                tab === "discovery"
                  ? "bg-white/20 text-white"
                  : "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300",
              )}
            >
              {posts.data.total} bài
            </span>
          )}
        </button>

        <button
          type="button"
          onClick={() => setTab("publishing")}
          className={cx(
            "inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold transition-all cursor-pointer",
            tab === "publishing"
              ? "bg-indigo-600 text-white shadow-sm dark:bg-indigo-500"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700",
          )}
        >
          <IconPosts size={15} />
          <span>Quản lý Đăng bài Seeding (Poster)</span>
          <span
            className={cx(
              "rounded-full px-2 py-0.5 text-[10px]",
              tab === "publishing"
                ? "bg-white/20 text-white"
                : "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
            )}
          >
            Mới
          </span>
        </button>
      </div>

      {tab === "publishing" ? (
        <PublishingStudio />
      ) : (
        <>
          {/* ── FILTER BAR ─────────────────────────────────────────────────── */}
          <Card
        title={
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <IconFilter size={15} />
            <span>Bộ lọc dữ liệu</span>
          </div>
        }
      >
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
          <Field label="Trạng thái bài viết">
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

      <ErrorNote>{posts.error}</ErrorNote>
      {posts.loading && <Spinner label="Đang lọc danh sách bài viết…" />}

      {!posts.loading && !posts.data?.items.length && (
        <Empty
          icon={<IconSearch size={24} />}
          action={
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setStatus("");
                setCampaignId("");
              }}
            >
              Xóa bộ lọc
            </Button>
          }
        >
          Không tìm thấy bài viết nào phù hợp với bộ lọc hiện tại.
        </Empty>
      )}

      {/* ── POSTS FEED ─────────────────────────────────────────────────── */}
      <div className="space-y-4">
        {posts.data?.items.map((post) => {
          const isHighMatch = post.ai_relevance_score >= 0.8;
          return (
            <div
              key={post.id}
              className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-xs transition-all duration-200 hover:border-slate-300 hover:shadow-sm dark:border-slate-800 dark:bg-slate-900/90 dark:hover:border-slate-700"
            >
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3.5 dark:border-slate-800">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 text-xs font-bold text-white shadow-xs">
                    {post.author_name?.[0]?.toUpperCase() || "FB"}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-slate-900 dark:text-white">
                        {post.author_name || "Thành viên Facebook"}
                      </span>
                      <Badge value={post.status} />
                    </div>
                    <div className="flex items-center gap-2 mt-0.5 text-[11px] text-slate-400">
                      <span>Quét lúc: {fmtDate(post.discovered_at)}</span>
                      <span>·</span>
                      <span>{post.existing_comment_count} comment trên bài</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span
                    className={cx(
                      "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold",
                      isHighMatch
                        ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/80 dark:text-emerald-300"
                        : "bg-indigo-100 text-indigo-800 dark:bg-indigo-950/80 dark:text-indigo-300",
                    )}
                  >
                    <IconSparkles size={13} />
                    Điểm AI: {post.ai_relevance_score.toFixed(2)}
                  </span>

                  {post.post_url && (
                    <a
                      href={post.post_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:border-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                      title="Mở bài viết gốc trên Facebook"
                    >
                      <IconExternalLink size={15} />
                    </a>
                  )}
                </div>
              </div>

              <div className="py-4">
                <p className="whitespace-pre-line text-sm text-slate-800 dark:text-slate-200 leading-relaxed font-normal">
                  {post.content_text}
                </p>

                {post.ai_reason && (
                  <div className="mt-3 flex items-start gap-2.5 rounded-xl border border-indigo-100 bg-indigo-50/50 p-3 text-xs text-indigo-950 dark:border-indigo-950/60 dark:bg-indigo-950/30 dark:text-indigo-200">
                    <IconSparkles size={16} className="shrink-0 text-indigo-500 mt-0.5" />
                    <div>
                      <span className="font-bold">Lý do AI chọn: </span>
                      <span>{post.ai_reason}</span>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3 dark:border-slate-800">
                <div className="text-xs text-slate-400">
                  {post.status === "commented" && (
                    <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                      ✓ Đã bình luận ứng tuyển
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    icon={<IconCheck size={14} />}
                    onClick={() => setSelected(post)}
                  >
                    Ứng tuyển bài này
                  </Button>
                  {post.status !== "skipped" && (
                    <Button
                      size="sm"
                      variant="ghost"
                      icon={<IconX size={14} />}
                      onClick={() => skipPost(post)}
                    >
                      Bỏ qua
                    </Button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── QUEUE SECTION ──────────────────────────────────────────────── */}
      {!!queue.data?.length && (
        <Card
          title={
            <div className="flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-indigo-600" />
              </span>
              <span>Hàng đợi comment đang chờ bắn ({queue.data.length})</span>
            </div>
          }
        >
          <ul className="space-y-3">
            {queue.data.map((action) => (
              <li
                key={action.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50/60 p-3.5 text-xs dark:border-slate-800/80 dark:bg-slate-800/40"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <Badge value={action.status} />
                    {action.scheduled_at && (
                      <span className="text-[11px] text-slate-400">
                        Lịch bắn: {fmtDate(action.scheduled_at)}
                      </span>
                    )}
                  </div>
                  <p className="mt-1.5 font-mono text-slate-700 dark:text-slate-300">
                    “{action.comment_content}”
                  </p>
                  {action.error_message && (
                    <p className="mt-1 text-rose-500">{action.error_message}</p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <CommentHistoryCard items={commentHistory.data?.items ?? []} error={commentHistory.error} loading={commentHistory.loading} />

      {/* ── APPLY MODAL ────────────────────────────────────────────────── */}
      <ApplyModal
        post={selected}
        recentComments={queue.data?.map((action) => action.comment_content) ?? []}
        onClose={() => setSelected(null)}
        onDone={() => {
          setSelected(null);
          toast.success("Đã đưa bình luận ứng tuyển vào hàng đợi bắn!", "Thành công");
          posts.reload();
          queue.reload();
        }}
      />
        </>
      )}
    </div>
  );
}

function CommentHistoryCard({
  items,
  error,
  loading,
}: {
  items: CommentHistory[];
  error: string | null;
  loading: boolean;
}) {
  return (
    <Card title="Lịch sử comment đã xử lý">
      <ErrorNote>{error}</ErrorNote>
      {loading && <Spinner label="Đang tải lịch sử comment…" />}
      {!loading && !items.length && (
        <p className="text-xs text-slate-500 dark:text-slate-400">Chưa có lượt comment nào được lưu.</p>
      )}
      {!!items.length && (
        <div className="space-y-2">
          {items.map((item) => (
            <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50/60 p-3 text-xs dark:border-slate-800 dark:bg-slate-800/40">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge value={item.status} />
                  <span className="truncate font-medium text-slate-800 dark:text-slate-200">{item.comment_content}</span>
                </div>
                <div className="mt-1 text-[11px] text-slate-400">Xử lý lúc: {fmtDate(item.executed_at || item.scheduled_at)}</div>
                {item.error_message && <div className="mt-1 text-rose-500">{item.error_message}</div>}
              </div>
              <div className="flex shrink-0 gap-2">
                {item.post_url && <a href={item.post_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-slate-600 hover:underline dark:text-slate-300">Bài gốc <IconExternalLink size={12} /></a>}
                {item.comment_url && <a href={item.comment_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-indigo-600 hover:underline dark:text-indigo-400">Comment <IconExternalLink size={12} /></a>}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function ApplyModal({
  post,
  recentComments,
  onClose,
  onDone,
}: {
  post: Post | null;
  recentComments: string[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [text, setText] = useState(DEFAULT_COMMENT_TEXT);
  const [cloneId, setCloneId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const clones = useAsync(() => api.clones(), [post?.id ?? ""]);
  const scripts = useAsync(
    () => (post ? api.scripts(post.campaign_id) : Promise.resolve([])),
    [post?.campaign_id ?? ""],
  );

  const clash = text.trim()
    ? recentComments.find((old) => similarity(text, old) >= 0.82)
    : undefined;

  const usableScripts = (scripts.data ?? []).filter(
    (script) => script.type === "spintax" && script.template_content.trim(),
  );

  if (!post) return null;

  function pullFromScript(template: string) {
    for (let attempt = 0; attempt < 25; attempt += 1) {
      const candidate = renderSpintax(template);
      if (candidate && !recentComments.some((old) => similarity(candidate, old) >= 0.82)) {
        setText(candidate);
        return;
      }
    }
    setText(renderSpintax(template));
  }

  async function submit() {
    setBusy(true);
    setError("");
    try {
      await api.applyPost(post!.id, {
        comment_text: text.trim() || undefined,
        clone_id: cloneId || undefined,
      });
      setText(DEFAULT_COMMENT_TEXT);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không đưa được vào hàng đợi");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={!!post}
      title={
        <div className="flex items-center gap-2">
          <IconCheck size={18} className="text-emerald-500" />
          <span>Ứng tuyển bài của {post.author_name || "khách hàng"}</span>
        </div>
      }
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Hủy bỏ
          </Button>
          <Button onClick={submit} disabled={busy} loading={busy}>
            Xác nhận & Đưa vào hàng đợi
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="max-h-36 overflow-y-auto rounded-xl border border-slate-200/80 bg-slate-50/70 p-3.5 text-xs text-slate-700 leading-relaxed dark:border-slate-800 dark:bg-slate-800/40 dark:text-slate-300 whitespace-pre-line">
          {post.content_text}
        </div>

        <ErrorNote>{error}</ErrorNote>

        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
              Lấy nhanh kịch bản ứng tuyển:
            </span>
            <button
              type="button"
              onClick={() => setText(DEFAULT_COMMENT_TEXT)}
              className="inline-flex items-center gap-1 text-[11px] text-indigo-600 hover:underline dark:text-indigo-400 font-medium cursor-pointer"
            >
              <IconSparkles size={12} />
              <span>Nạp lại mẫu mặc định</span>
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setText(DEFAULT_COMMENT_TEXT)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50/70 px-2.5 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 transition-all dark:border-indigo-800 dark:bg-indigo-950/50 dark:text-indigo-300 dark:hover:bg-indigo-900/60 cursor-pointer"
            >
              <IconSparkles size={13} className="text-indigo-500" />
              Mẫu CMT Nyatymita (Mặc định)
            </button>
            {usableScripts.map((script) => (
              <button
                key={script.id}
                type="button"
                onClick={() => pullFromScript(script.template_content)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200/90 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:border-indigo-400 hover:bg-indigo-50/50 hover:text-indigo-700 transition-all dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 cursor-pointer"
              >
                <IconSparkles size={13} className="text-indigo-500" />
                {script.name}
                <span className="text-[10px] text-slate-400">
                  ({countVariants(script.template_content)} biến thể)
                </span>
              </button>
            ))}
          </div>
        </div>

        <Field
          label="Nội dung bình luận ứng tuyển"
          hint="Để trống nếu muốn AI tự sinh theo kịch bản. Chú ý: TUYỆT ĐỐI KHÔNG chứa đường link (URL) để tránh bị ăn gậy spam."
        >
          <Textarea
            value={text}
            placeholder="Nhập nội dung bình luận hoặc bấm lấy câu từ kịch bản bên trên…"
            className="min-h-28"
            onChange={(e) => setText(e.target.value)}
          />
        </Field>

        <div className="flex flex-wrap items-center justify-between text-xs text-slate-500">
          <span>{text.trim().split(/\s+/).filter(Boolean).length} từ</span>
          {containsLinkLike(text) && (
            <span className="font-semibold text-rose-600 dark:text-rose-400">
              ⛔ Phát hiện có dấu hiệu liên kết web — sẽ bị từ chối khi lưu!
            </span>
          )}
        </div>

        {clash && (
          <div className="rounded-xl border border-amber-200 bg-amber-50/80 p-3 text-xs text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
            <span className="font-bold">⚠️ Cảnh báo:</span> Câu này trùng hơn 82% với comment vừa gửi gần đây:
            <p className="mt-1 italic font-mono">“{clash}”</p>
            <p className="mt-1 text-[11px] text-amber-700 dark:text-amber-300">
              Hãy sửa vài chữ hoặc bấm lại nút kịch bản để bốc một biến thể khác an toàn hơn.
            </p>
          </div>
        )}

        <Field
          label="Tài khoản clone thực hiện"
          hint="Chỉ các nick có vai trò 'shooter', 'both', hoặc 'all' mới thực hiện bình luận ứng tuyển (Scout/Poster được miễn trừ)."
        >
          <Select value={cloneId} onChange={(e) => setCloneId(e.target.value)}>
            <option value="">Tự động luân chuyển clone Shooter tối ưu</option>
            {clones.data
              ?.filter(
                (clone) =>
                  clone.status === "active" &&
                  ["shooter", "both", "all"].includes(clone.role),
              )
              .map((clone) => (
                <option key={clone.id} value={clone.id}>
                  {clone.display_name} ({clone.role} - Hôm nay: {clone.daily_comment_count}/{clone.daily_comment_limit})
                </option>
              ))}
          </Select>
        </Field>
      </div>
    </Modal>
  );
}

function containsLinkLike(text: string): boolean {
  return /(https?:\/\/|www\.|\b[\w-]+\.(com|net|vn|org|io|xyz|shop|me)\b)/i.test(text);
}
