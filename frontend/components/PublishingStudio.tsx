"use client";
import { useMemo, useState } from "react";

import {
  IconCheck,
  IconClock,
  IconExternalLink,
  IconFacebook,
  IconFilter,
  IconPlay,
  IconPlus,
  IconPosts,
  IconRefresh,
  IconSparkles,
  IconTrash,
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
  Select,
  Spinner,
  Textarea,
  cx,
  fmtDate,
  useAsync,
  useToast,
} from "@/components/ui";
import { api } from "@/lib/api";
import { countVariants, renderSpintax } from "@/lib/spintax";
import type { PostPublish, PostPublishTarget } from "@/lib/types";

const PUBLISH_STATUSES = [
  { value: "", label: "Tất cả trạng thái" },
  { value: "scheduled", label: "Đã lên lịch" },
  { value: "publishing", label: "Đang đăng" },
  { value: "published", label: "Đã đăng thành công" },
  { value: "partially_published", label: "Đăng một phần" },
  { value: "failed", label: "Thất bại" },
];

export function PublishingStudio() {
  const toast = useToast();
  const [campaignId, setCampaignId] = useState("");
  const [status, setStatus] = useState("");
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [publishingId, setPublishingId] = useState<string | null>(null);

  const campaigns = useAsync(() => api.campaigns());
  const clones = useAsync(() => api.clones());
  const publishList = useAsync(
    () =>
      api.publishingPosts({
        campaign_id: campaignId || undefined,
        status: status || undefined,
      }),
    [campaignId, status],
  );

  // Chỉ lọc các clone có vai trò Poster hoặc All (đa nhiệm)
  const posterClones = useMemo(() => {
    return (clones.data ?? []).filter(
      (c) => c.role === "poster" || c.role === "all",
    );
  }, [clones.data]);

  async function handlePublishNow(postId: string) {
    setPublishingId(postId);
    try {
      await api.publishPostNow(postId);
      toast.success("Đã đăng bài thành công vào nhóm mục tiêu!", "Thành công");
      publishList.reload();
      clones.reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Đăng bài thất bại");
    } finally {
      setPublishingId(null);
    }
  }

  async function handleDelete(postId: string) {
    if (!confirm("Bạn có chắc muốn xoá bài đăng này?")) return;
    try {
      await api.deletePublishingPost(postId);
      toast.info("Đã xoá bài đăng.");
      publishList.reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không xoá được bài đăng");
    }
  }

  return (
    <div className="space-y-6">
      {/* ── BANNER PHÂN VAI TRÒ CLONE ──────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-200/80 bg-gradient-to-r from-amber-50/90 via-orange-50/70 to-amber-50/90 p-4 text-xs dark:border-amber-900/50 dark:from-amber-950/30 dark:via-orange-950/20 dark:to-amber-950/30">
        <div className="flex items-start gap-2.5 max-w-2xl">
          <span className="text-xl">📢</span>
          <div>
            <h2 className="font-semibold text-amber-950 dark:text-amber-200">
              Phân công nhiệm vụ chuyên biệt: Đăng bài tự động (Poster)
            </h2>
            <p className="mt-0.5 text-amber-800 dark:text-amber-300/90 leading-relaxed">
              Các bài đăng ở đây sẽ được thực thi bởi các nick có vai trò <strong>Đăng bài (Poster)</strong> hoặc <strong>Đa nhiệm (All)</strong>. Nick quét bài (Scout) và nick cmt (Shooter) sẽ không bị dùng để đăng bài, giúp tài khoản luôn an toàn.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={() => setCreateModalOpen(true)}
            icon={<IconPlus size={15} />}
          >
            Soạn bài đăng mới
          </Button>
        </div>
      </div>

      {/* ── BỘ LỌC ─────────────────────────────────────────────────────── */}
      <Card
        title={
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <IconFilter size={15} />
            <span>Bộ lọc bài đăng</span>
          </div>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Chiến dịch">
            <Select
              value={campaignId}
              onChange={(e) => setCampaignId(e.target.value)}
            >
              <option value="">Tất cả chiến dịch</option>
              {campaigns.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Trạng thái">
            <Select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              {PUBLISH_STATUSES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </Card>

      <ErrorNote>{publishList.error}</ErrorNote>
      {publishList.loading && <Spinner label="Đang tải danh sách bài đăng…" />}

      {!publishList.loading && !publishList.data?.items.length && (
        <Empty
          icon={<IconPosts size={24} />}
          action={
            <Button
              size="sm"
              onClick={() => setCreateModalOpen(true)}
              icon={<IconPlus size={15} />}
            >
              Soạn bài đăng đầu tiên
            </Button>
          }
        >
          Chưa có bài đăng nhóm nào. Hãy tạo bài viết mới với mẫu Spintax để nick Poster tự động xuất bản vào các nhóm mục tiêu.
        </Empty>
      )}

      {/* ── DANH SÁCH BÀI ĐĂNG ─────────────────────────────────────────── */}
      <div className="space-y-4">
        {publishList.data?.items.map((post) => (
          <PublishCard
            key={post.id}
            post={post}
            posterClones={posterClones}
            isPublishing={publishingId === post.id}
            onPublishNow={() => handlePublishNow(post.id)}
            onDelete={() => handleDelete(post.id)}
          />
        ))}
      </div>

      {/* ── MODAL SOẠN BÀI MỚI ─────────────────────────────────────────── */}
      <CreatePublishModal
        open={createModalOpen}
        posterClones={posterClones}
        campaigns={campaigns.data ?? []}
        onClose={() => setCreateModalOpen(false)}
        onCreated={() => {
          setCreateModalOpen(false);
          toast.success("Đã lên lịch bài đăng mới thành công!", "Thành công");
          publishList.reload();
        }}
      />
    </div>
  );
}

function PublishCard({
  post,
  posterClones,
  isPublishing,
  onPublishNow,
  onDelete,
}: {
  post: PostPublish;
  posterClones: Array<{ id: string; display_name: string; role: string }>;
  isPublishing: boolean;
  onPublishNow: () => void;
  onDelete: () => void;
}) {
  const [showResults, setShowResults] = useState(false);
  const assignedClone = posterClones.find((c) => c.id === post.clone_account_id);

  const isCompleted = post.status === "published" || post.status === "partially_published";
  const canPublish = post.status === "scheduled" || post.status === "failed" || post.status === "draft";

  return (
    <Card
      title={
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-slate-900 dark:text-white">
            {post.title || "Bài đăng nhóm không tiêu đề"}
          </span>
          <Badge value={post.status} />
          {assignedClone ? (
            <Badge value={assignedClone.role}>
              Nick: {assignedClone.display_name}
            </Badge>
          ) : (
            <Badge value="poster">Tự động chọn clone</Badge>
          )}
        </div>
      }
      action={
        <div className="flex items-center gap-1.5">
          {canPublish && (
            <Button
              size="xs"
              variant="outline"
              loading={isPublishing}
              disabled={isPublishing}
              onClick={onPublishNow}
              icon={<IconPlay size={12} />}
            >
              Đăng ngay
            </Button>
          )}
          <Button
            size="xs"
            variant="ghost"
            className="text-rose-600 hover:text-rose-700 dark:text-rose-400"
            onClick={onDelete}
            icon={<IconTrash size={12} />}
          >
            Xoá
          </Button>
        </div>
      }
    >
      <div className="space-y-3 text-xs">
        {/* Nội dung Spintax mẫu */}
        <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3 text-slate-800 font-mono leading-relaxed dark:border-slate-800 dark:bg-slate-800/40 dark:text-slate-200 whitespace-pre-line">
          {post.content_template}
        </div>

        {/* Thông tin nhóm mục tiêu & thời gian */}
        <div className="flex flex-wrap items-center justify-between gap-2 text-slate-500">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-medium text-slate-700 dark:text-slate-300">
              Nhóm đăng ({post.target_groups?.length || 0}):
            </span>
            {post.target_groups?.map((g, idx) => (
              <span
                key={idx}
                className="rounded-md bg-slate-100 px-2 py-0.5 text-slate-600 dark:bg-slate-800 dark:text-slate-400 font-sans"
              >
                {g.group_name || `Group #${g.group_id}`}
              </span>
            ))}
          </div>

          <div className="flex items-center gap-2">
            {post.published_at ? (
              <span>Đã đăng: {fmtDate(post.published_at)}</span>
            ) : post.scheduled_at ? (
              <span>Lịch đăng: {fmtDate(post.scheduled_at)}</span>
            ) : (
              <span>Tạo lúc: {fmtDate(post.created_at)}</span>
            )}
          </div>
        </div>

        {/* Báo lỗi nếu có */}
        {post.error_message && (
          <div className="rounded-lg border border-rose-200 bg-rose-50/70 p-2.5 text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-300">
            <strong>Lỗi thực thi:</strong> {post.error_message}
          </div>
        )}

        {/* Kết quả sau khi đăng */}
        {isCompleted && post.publish_results && post.publish_results.length > 0 && (
          <div className="border-t border-slate-100 pt-2 dark:border-slate-800">
            <button
              type="button"
              onClick={() => setShowResults(!showResults)}
              className="text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 font-medium inline-flex items-center gap-1 cursor-pointer"
            >
              {showResults ? "Ẩn danh sách link bài đăng" : `Xem link bài đã đăng (${post.publish_results.length} nhóm)`}
            </button>

            {showResults && (
              <ul className="mt-2 space-y-1.5">
                {post.publish_results.map((res, i) => (
                  <li
                    key={i}
                    className="flex items-center justify-between rounded-lg bg-slate-50 p-2 text-slate-700 dark:bg-slate-800/60 dark:text-slate-300"
                  >
                    <span>{res.group_name || "Nhóm Facebook"}</span>
                    {res.post_url ? (
                      <a
                        href={res.post_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-indigo-600 hover:underline dark:text-indigo-400 font-medium"
                      >
                        <span>Mở bài viết</span>
                        <IconExternalLink size={12} />
                      </a>
                    ) : (
                      <span className="text-slate-400">
                        {res.status === "failed"
                          ? `Đăng lỗi${res.error ? `: ${res.error}` : ""}`
                          : res.status === "skipped_quota"
                            ? "Bỏ qua — hết hạn mức ngày"
                            : res.status === "published_no_url"
                              ? "Đã đăng, chưa lấy được link"
                              : "Không có link"}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

function CreatePublishModal({
  open,
  posterClones,
  campaigns,
  onClose,
  onCreated,
}: {
  open: boolean;
  posterClones: Array<{ id: string; display_name: string; role: string; daily_post_count?: number; daily_post_limit?: number; status: string }>;
  campaigns: Array<{ id: string; name: string }>;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [campaignId, setCampaignId] = useState("");
  const [cloneId, setCloneId] = useState("");
  const [template, setTemplate] = useState("");
  const [groupUrl, setGroupUrl] = useState("");
  const [groupName, setGroupName] = useState("");
  const [targetGroups, setTargetGroups] = useState<PostPublishTarget[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [previewSample, setPreviewSample] = useState("");

  const campaignGroups = useAsync(
    () => (campaignId ? api.groups(campaignId) : Promise.resolve([])),
    [campaignId],
  );

  function addTargetGroup() {
    if (!groupName.trim() && !groupUrl.trim()) return;
    const newGroup: PostPublishTarget = {
      group_id: `g_${Date.now()}`,
      group_name: groupName.trim() || "Nhóm Facebook",
      group_url: groupUrl.trim(),
    };
    setTargetGroups([...targetGroups, newGroup]);
    setGroupName("");
    setGroupUrl("");
  }

  function handlePickCampaignGroup(group: { id: string; group_name: string; group_url: string }) {
    if (targetGroups.some((g) => g.group_url === group.group_url)) return;
    setTargetGroups([
      ...targetGroups,
      { group_id: group.id, group_name: group.group_name, group_url: group.group_url },
    ]);
  }

  function generateSample() {
    if (!template.trim()) return;
    try {
      setPreviewSample(renderSpintax(template));
    } catch {
      setPreviewSample(template);
    }
  }

  async function submit() {
    if (!template.trim()) {
      setError("Vui lòng nhập nội dung kịch bản bài đăng.");
      return;
    }
    if (targetGroups.length === 0) {
      setError("Vui lòng thêm ít nhất một nhóm mục tiêu để đăng bài.");
      return;
    }

    setBusy(true);
    setError("");
    try {
      await api.createPublishingPost({
        campaign_id: campaignId || null,
        clone_account_id: cloneId || null,
        title: title.trim() || "Bài đăng tự động",
        content_template: template.trim(),
        target_groups: targetGroups,
      });
      setTitle("");
      setTemplate("");
      setTargetGroups([]);
      setPreviewSample("");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tạo bài đăng thất bại");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Soạn bài đăng Seeding mới vào Nhóm"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Huỷ bỏ
          </Button>
          <Button onClick={submit} disabled={busy} loading={busy}>
            Xác nhận & Lên lịch đăng
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <ErrorNote>{error}</ErrorNote>

        <Field label="Tiêu đề gợi nhớ">
          <Input
            value={title}
            placeholder="VD: Bài tuyển CTV bán hàng, Giới thiệu dịch vụ..."
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Chiến dịch liên kết (tuỳ chọn)">
            <Select
              value={campaignId}
              onChange={(e) => setCampaignId(e.target.value)}
            >
              <option value="">Không gán chiến dịch</option>
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field
            label="Chọn nick Poster chuyên trách"
            hint="Chỉ các nick có role 'poster' hoặc 'all' mới xuất hiện ở đây."
          >
            <Select value={cloneId} onChange={(e) => setCloneId(e.target.value)}>
              <option value="">Tự động chọn nick Poster khả dụng</option>
              {posterClones.map((clone) => (
                <option key={clone.id} value={clone.id}>
                  {clone.display_name} ({clone.role} - Đã đăng: {clone.daily_post_count || 0}/{clone.daily_post_limit || 5})
                </option>
              ))}
            </Select>
          </Field>
        </div>

        {posterClones.length === 0 && (
          <div className="rounded-xl border border-amber-200 bg-amber-50/80 p-3 text-xs text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
            <strong>⚠️ Chưa có nick Đăng bài (Poster):</strong> Bạn hãy vào mục{" "}
            <a href="/clones" className="underline font-semibold">Tài khoản Clone</a> để tạo nick với vai trò <strong>Đăng bài (Poster)</strong> hoặc chuyển vai trò cho nick hiện có.
          </div>
        )}

        {/* Nội dung Spintax */}
        <div>
          <Field
            label="Nội dung bài viết (Hỗ trợ Spintax)"
            hint="Sử dụng cú pháp {Lựa chọn 1|Lựa chọn 2} để mỗi lần đăng là một bài viết độc nhất, chống bị Facebook đánh spam."
          >
            <Textarea
              value={template}
              placeholder="{Chào cả nhà|Hello mọi người}! Bên mình đang tuyển {cộng tác viên|đối tác}..."
              className="min-h-28 font-mono text-xs"
              onChange={(e) => {
                setTemplate(e.target.value);
                setPreviewSample("");
              }}
            />
          </Field>

          <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
            <span>
              Tổng số biến thể khả thi: <strong>{countVariants(template)}</strong>
            </span>
            <button
              type="button"
              onClick={generateSample}
              disabled={!template.trim()}
              className="inline-flex items-center gap-1 text-indigo-600 hover:underline dark:text-indigo-400 font-medium cursor-pointer"
            >
              <IconSparkles size={13} />
              <span>Xem thử biến thể ngẫu nhiên</span>
            </button>
          </div>

          {previewSample && (
            <div className="mt-2 rounded-xl border border-indigo-200/80 bg-indigo-50/60 p-3 text-xs text-indigo-950 dark:border-indigo-900/50 dark:bg-indigo-950/30 dark:text-indigo-300">
              <span className="font-semibold block mb-1">Mẫu sinh thử:</span>
              <p className="whitespace-pre-line italic font-sans">{previewSample}</p>
            </div>
          )}
        </div>

        {/* Chọn nhóm mục tiêu */}
        <div>
          <span className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
            Nhóm Facebook mục tiêu đăng bài:
          </span>

          {campaignGroups.data && campaignGroups.data.length > 0 && (
            <div className="mb-2">
              <span className="block text-[11px] text-slate-500 mb-1">
                Lấy nhanh từ danh sách nhóm của chiến dịch:
              </span>
              <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
                {campaignGroups.data.map((g) => (
                  <button
                    key={g.id}
                    type="button"
                    onClick={() => handlePickCampaignGroup(g)}
                    className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 hover:border-indigo-400 hover:bg-indigo-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 cursor-pointer"
                  >
                    + {g.group_name}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="grid gap-2 sm:grid-cols-2">
            <Input
              value={groupName}
              placeholder="Tên nhóm (VD: Hội Khởi Nghiệp)"
              onChange={(e) => setGroupName(e.target.value)}
            />
            <div className="flex gap-1.5">
              <Input
                value={groupUrl}
                placeholder="Link nhóm Facebook (https://...)"
                onChange={(e) => setGroupUrl(e.target.value)}
              />
              <Button size="sm" type="button" onClick={addTargetGroup}>
                Thêm
              </Button>
            </div>
          </div>

          {targetGroups.length > 0 && (
            <div className="mt-2.5 space-y-1 max-h-32 overflow-y-auto rounded-lg border border-slate-100 p-2 dark:border-slate-800">
              {targetGroups.map((g, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between rounded bg-slate-50 px-2.5 py-1 text-xs text-slate-700 dark:bg-slate-800/70 dark:text-slate-300"
                >
                  <span className="truncate">{g.group_name}</span>
                  <button
                    type="button"
                    onClick={() => setTargetGroups(targetGroups.filter((_, i) => i !== index))}
                    className="text-rose-500 hover:text-rose-700 ml-2"
                  >
                    Xoá
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
