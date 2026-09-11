"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  IconAlertCircle,
  IconArrowRight,
  IconCheck,
  IconCopy,
  IconDashboard,
  IconExternalLink,
  IconFacebook,
  IconHeartPulse,
  IconLayers,
  IconPlus,
  IconPosts,
  IconRefresh,
  IconSearch,
  IconShieldCheck,
  IconSparkles,
  IconTelegram,
  IconUsers,
  IconZap,
} from "@/components/icons";
import {
  Badge,
  Button,
  Card,
  ErrorNote,
  Field,
  Input,
  Progress,
  Select,
  Textarea,
  cx,
  useToast,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { renderSpintax } from "@/lib/spintax";

interface IndustryPreset {
  id: string;
  name: string;
  campaignName: string;
  filterPrompt: string;
  whitelist: string;
  blacklist: string;
  scriptName: string;
  scriptTemplate: string;
}

const PRESETS: IndustryPreset[] = [
  {
    id: "design_web",
    name: "Thiết kế đồ họa & Website",
    campaignName: "Săn khách Thiết kế UI/UX & Web",
    filterPrompt:
      "Tìm các bài viết có nhu cầu thuê thiết kế logo, banner, giao diện website, landing page hoặc thiết kế ấn phẩm marketing.",
    whitelist: "thiết kế, banner, logo, landing page, figma, photoshop, website, giao diện",
    blacklist: "tuyển dụng fulltime, tuyển nhân viên, miễn phí, 0đ, dạo",
    scriptName: "Chào khách thiết kế & gửi portfolio",
    scriptTemplate:
      "{Chào|Em chào|Hi} {anh/chị|bạn}, bên em chuyên {thiết kế landing page|thiết kế website|làm giao diện} {chuẩn UI/UX|tối ưu chuyển đổi|load nhanh}. Em đã gửi {portfolio|một số dự án tương tự} qua tin nhắn, {anh/chị|bạn} xem qua giúp em nhé!",
  },
  {
    id: "writing_content",
    name: "Viết bài & Sáng tạo nội dung",
    campaignName: "Săn khách Content & Copywriting",
    filterPrompt:
      "Tìm bài viết tìm người viết bài chuẩn SEO, viết content chạy ads, viết kịch bản video ngắn TikTok/Reels.",
    whitelist: "viết bài, content, chuẩn seo, kịch bản, viết lách, copywriting, bài pr",
    blacklist: "tuyển dụng thực tập, không lương, bẫy lừa đảo, ctv nạp tiền",
    scriptName: "Chào khách content",
    scriptTemplate:
      "{Chào|Dạ em chào} {anh/chị|bạn}, em có kinh nghiệm {viết content chuẩn SEO|sáng tạo kịch bản video ngắn|làm nội dung chạy ads} hơn 2 năm. Em đã gửi {bài mẫu|portfolio bài viết} vào inbox rồi ạ, {anh/chị|bạn} kiểm tra giúp em nhé!",
  },
  {
    id: "dev_software",
    name: "Lập trình & Phát triển phần mềm",
    campaignName: "Săn dự án Lập trình & Web App",
    filterPrompt:
      "Tìm bài viết tuyển freelance developer, làm tool tự động hóa, viết bot cào dữ liệu hoặc xây dựng ứng dụng web/mobile.",
    whitelist: "lập trình, viết tool, bot, crawler, react, nodejs, python, phần mềm, outsource",
    blacklist: "tuyển nhân viên văn phòng, đa cấp, làm nhiệm vụ",
    scriptName: "Ứng tuyển dự án dev",
    scriptTemplate:
      "{Chào|Em chào} {anh/chị|bạn}, bên em chuyên nhận {viết tool tự động hóa|xây dựng web app|làm bot crawler}. Dự án này bên em đã có kinh nghiệm làm tương tự, em đã gửi thông tin kỹ thuật qua tin nhắn, {anh/chị|bạn} check giúp em nhé!",
  },
  {
    id: "custom",
    name: "Tùy chỉnh lĩnh vực khác",
    campaignName: "Chiến dịch săn khách Facebook",
    filterPrompt: "Tìm các bài viết có nhu cầu mua dịch vụ hoặc tìm đối tác.",
    whitelist: "cần tìm, cần thuê, ai làm được, tư vấn giúp, báo giá",
    blacklist: "tuyển dụng, đa cấp, lừa đảo",
    scriptName: "Kịch bản chào hàng cơ bản",
    scriptTemplate:
      "{Chào|Em chào} {anh/chị|bạn}, bên em chuyên cung cấp dịch vụ này uy tín, giá hợp lý. Em đã gửi thông tin chi tiết qua inbox, {anh/chị|bạn} check giúp em nhé!",
  },
];

export default function OnboardingPage() {
  const router = useRouter();
  const { user } = useAuth();
  const toast = useToast();

  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Step 1: Chọn gói cước
  const [selectedPlan, setSelectedPlan] = useState<string>(
    user?.subscription?.plan ?? "pro",
  );

  // Step 2: Tạo chiến dịch
  const [selectedPreset, setSelectedPreset] = useState<string>("design_web");
  const [campaignName, setCampaignName] = useState(PRESETS[0].campaignName);
  const [aiPrompt, setAiPrompt] = useState(PRESETS[0].filterPrompt);
  const [whitelist, setWhitelist] = useState(PRESETS[0].whitelist);
  const [blacklist, setBlacklist] = useState(PRESETS[0].blacklist);
  const [mode, setMode] = useState<"semi_auto" | "full_auto">("semi_auto");
  const [createdCampaignId, setCreatedCampaignId] = useState<string>("");

  // Step 3: Nạp clone
  const [cloneName, setCloneName] = useState("Clone Scout 01");
  const [cloneRole, setCloneRole] = useState("scout");
  const [cookieInput, setCookieInput] = useState("");
  const [cloneAdded, setCloneAdded] = useState(false);

  // Step 4: Thêm group
  const [groupUrl, setGroupUrl] = useState("");
  const [groupName, setGroupName] = useState("");
  const [groupsAdded, setGroupsAdded] = useState<string[]>([]);

  // Step 5: Soạn kịch bản & Telegram
  const [scriptTitle, setScriptTitle] = useState(PRESETS[0].scriptName);
  const [scriptContent, setScriptContent] = useState(PRESETS[0].scriptTemplate);
  const [scriptAdded, setScriptAdded] = useState(false);
  const [telegramCode, setTelegramCode] = useState<string>("");

  // Preview spintax
  const [previewSample, setPreviewSample] = useState("");

  useEffect(() => {
    try {
      setPreviewSample(renderSpintax(scriptContent));
    } catch {
      setPreviewSample(scriptContent);
    }
  }, [scriptContent]);

  // Cập nhật form theo preset
  function handlePresetChange(presetId: string) {
    setSelectedPreset(presetId);
    const p = PRESETS.find((x) => x.id === presetId) || PRESETS[0];
    setCampaignName(p.campaignName);
    setAiPrompt(p.filterPrompt);
    setWhitelist(p.whitelist);
    setBlacklist(p.blacklist);
    setScriptTitle(p.scriptName);
    setScriptContent(p.scriptTemplate);
  }

  // ── XỬ LÝ CHUYỂN BƯỚC ─────────────────────────────────────────────────────

  async function handleNextFromStep2() {
    if (!campaignName.trim()) {
      setError("Vui lòng đặt tên cho chiến dịch đầu tiên của bạn");
      return;
    }
    setError("");
    setLoading(true);
    try {
      // Gọi API tạo chiến dịch
      const wl = whitelist
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const bl = blacklist
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);

      const res = await api.createCampaign({
        name: campaignName.trim(),
        mode,
        ai_filter_prompt: aiPrompt,
        whitelist_keywords: wl,
        blacklist_keywords: bl,
        max_comments_per_day: selectedPlan === "starter" ? 20 : 50,
      });

      setCreatedCampaignId(res.id);
      toast.success("Đã tạo chiến dịch đầu tiên thành công!", "Tuyệt vời");
      setStep(3);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tạo được chiến dịch");
    } finally {
      setLoading(false);
    }
  }

  async function handleNextFromStep3() {
    setError("");
    // Nếu người dùng có nhập cookie thì gọi nạp clone
    if (cookieInput.trim()) {
      setLoading(true);
      try {
        const clone = await api.createClone({
          display_name: cloneName || "Clone mới",
          role: cloneRole as any,
          daily_comment_limit: 20,
        });

        const cookieFile = new File([cookieInput.trim()], "cookie.json", {
          type: "application/json",
        });
        await api.uploadCookie(clone.id, cookieFile);
        setCloneAdded(true);
        toast.success("Đã nạp và kích hoạt tài khoản clone thành công!");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Lỗi nạp cookie clone");
        setLoading(false);
        return;
      } finally {
        setLoading(false);
      }
    }
    setStep(4);
  }

  async function handleAddGroup() {
    if (!groupUrl.trim()) return;
    if (!createdCampaignId) {
      toast.warning("Chưa có chiến dịch");
      return;
    }
    setError("");
    setLoading(true);
    try {
      await api.addGroup(createdCampaignId, {
        group_url: groupUrl.trim(),
        group_name: groupName.trim() || groupUrl.trim(),
      });
      setGroupsAdded((prev) => [...prev, groupName.trim() || groupUrl.trim()]);
      setGroupUrl("");
      setGroupName("");
      toast.success("Đã thêm nhóm vào chiến dịch!");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thêm được nhóm");
    } finally {
      setLoading(false);
    }
  }

  async function handleNextFromStep4() {
    setError("");
    setStep(5);
    // Chuẩn bị mã liên kết Telegram
    try {
      const res = await api.connectTelegram();
      setTelegramCode(res.link_code);
    } catch {
      // bỏ qua nếu lỗi
    }
  }

  async function handleCompleteStep5() {
    setError("");
    if (createdCampaignId && scriptContent.trim()) {
      setLoading(true);
      try {
        await api.createScript(createdCampaignId, {
          name: scriptTitle.trim() || "Kịch bản chính",
          template_content: scriptContent.trim(),
          is_active: true,
        });
        setScriptAdded(true);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Lưu kịch bản thất bại");
        setLoading(false);
        return;
      } finally {
        setLoading(false);
      }
    }
    setStep(6); // Màn hình hoàn thành
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 py-4">
      {/* ── HEADER TOP BAR ─────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white shadow-md shadow-indigo-500/25">
              <IconSparkles size={18} />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-2xl">
              Hướng dẫn Thiết lập 5 Bước (Onboarding Wizard)
            </h1>
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Khởi tạo hệ thống tự động hóa săn lead và comment Facebook chỉ trong vài phút.
          </p>
        </div>

        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push("/dashboard")}
          className="text-xs text-slate-500"
        >
          Bỏ qua hướng dẫn → Vào Dashboard
        </Button>
      </div>

      {/* ── PROGRESS STEPPER ───────────────────────────────────────────── */}
      <div className="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <div className="grid grid-cols-5 gap-2">
          {[
            { n: 1, label: "Gói cước" },
            { n: 2, label: "Chiến dịch" },
            { n: 3, label: "Nick Clone" },
            { n: 4, label: "Nhóm FB" },
            { n: 5, label: "Kịch bản & Bot" },
          ].map((s) => {
            const isCurrent = step === s.n;
            const isDone = step > s.n;
            return (
              <div
                key={s.n}
                className={cx(
                  "flex flex-col items-center justify-center rounded-xl p-2 text-center transition-all",
                  isCurrent
                    ? "bg-indigo-50 text-indigo-900 font-bold dark:bg-indigo-950/60 dark:text-indigo-300"
                    : isDone
                      ? "text-emerald-600 dark:text-emerald-400 font-medium"
                      : "text-slate-400",
                )}
              >
                <div
                  className={cx(
                    "flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-all mb-1",
                    isCurrent
                      ? "bg-indigo-600 text-white shadow-sm"
                      : isDone
                        ? "bg-emerald-500 text-white"
                        : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
                  )}
                >
                  {isDone ? <IconCheck size={14} /> : s.n}
                </div>
                <span className="truncate text-[11px]">{s.label}</span>
              </div>
            );
          })}
        </div>
      </div>

      <ErrorNote>{error}</ErrorNote>

      {/* ── STEP 1: CHỌN GÓI CƯỚC ───────────────────────────────────────── */}
      {step === 1 && (
        <Card
          title="Bước 1: Chọn gói cước phù hợp"
          action={
            <Button size="sm" onClick={() => setStep(2)} icon={<IconArrowRight size={15} />}>
              Tiếp tục: Tạo chiến dịch
            </Button>
          }
        >
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-6">
            Mỗi gói cước có hạn mức số nhóm Facebook theo dõi và số lượng comment tự động mỗi ngày. Bạn có thể nâng cấp bất cứ lúc nào.
          </p>

          <div className="grid gap-4 sm:grid-cols-3">
            {/* Starter */}
            <div
              onClick={() => setSelectedPlan("starter")}
              className={cx(
                "cursor-pointer rounded-2xl border p-5 transition-all",
                selectedPlan === "starter"
                  ? "border-indigo-600 bg-indigo-50/40 ring-2 ring-indigo-500/20 dark:border-indigo-500 dark:bg-indigo-950/30"
                  : "border-slate-200/90 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900",
              )}
            >
              <div className="flex items-center justify-between">
                <h4 className="font-bold text-slate-900 dark:text-white">Starter</h4>
                {selectedPlan === "starter" && <IconCheck size={16} className="text-indigo-600" />}
              </div>
              <p className="mt-2 text-xl font-extrabold text-slate-900 dark:text-white">
                199.000đ <span className="text-xs font-normal text-slate-400">/tháng</span>
              </p>
              <ul className="mt-4 space-y-2 text-xs text-slate-600 dark:text-slate-300">
                <li>• 5 Nhóm Facebook</li>
                <li>• 1 Nick Clone</li>
                <li>• 20 Comment / ngày</li>
              </ul>
            </div>

            {/* Pro */}
            <div
              onClick={() => setSelectedPlan("pro")}
              className={cx(
                "cursor-pointer rounded-2xl border p-5 transition-all relative",
                selectedPlan === "pro"
                  ? "border-indigo-600 bg-indigo-50/40 ring-2 ring-indigo-500/20 dark:border-indigo-500 dark:bg-indigo-950/30"
                  : "border-slate-200/90 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900",
              )}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <h4 className="font-bold text-slate-900 dark:text-white">Pro</h4>
                  <span className="rounded bg-indigo-100 px-1.5 py-0.2 text-[9px] font-bold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                    Khuyên dùng
                  </span>
                </div>
                {selectedPlan === "pro" && <IconCheck size={16} className="text-indigo-600" />}
              </div>
              <p className="mt-2 text-xl font-extrabold text-indigo-600 dark:text-indigo-400">
                399.000đ <span className="text-xs font-normal text-slate-400">/tháng</span>
              </p>
              <ul className="mt-4 space-y-2 text-xs text-slate-600 dark:text-slate-300">
                <li>• 20 Nhóm Facebook</li>
                <li>• 3 Nick Clone (Scout + Shooter)</li>
                <li>• 50 Comment / ngày</li>
                <li>• Tự động Bump bài</li>
              </ul>
            </div>

            {/* Studio */}
            <div
              onClick={() => setSelectedPlan("studio")}
              className={cx(
                "cursor-pointer rounded-2xl border p-5 transition-all",
                selectedPlan === "studio"
                  ? "border-indigo-600 bg-indigo-50/40 ring-2 ring-indigo-500/20 dark:border-indigo-500 dark:bg-indigo-950/30"
                  : "border-slate-200/90 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900",
              )}
            >
              <div className="flex items-center justify-between">
                <h4 className="font-bold text-slate-900 dark:text-white">Studio</h4>
                {selectedPlan === "studio" && <IconCheck size={16} className="text-indigo-600" />}
              </div>
              <p className="mt-2 text-xl font-extrabold text-slate-900 dark:text-white">
                799.000đ <span className="text-xs font-normal text-slate-400">/tháng</span>
              </p>
              <ul className="mt-4 space-y-2 text-xs text-slate-600 dark:text-slate-300">
                <li>• Không giới hạn Nhóm</li>
                <li>• 10 Nick Clone</li>
                <li>• 150 Comment / ngày</li>
                <li>• Seeding Poster & Dedicated Proxy</li>
              </ul>
            </div>
          </div>
        </Card>
      )}

      {/* ── STEP 2: TẠO CHIẾN DỊCH ĐẦU TIÊN ───────────────────────────── */}
      {step === 2 && (
        <Card
          title="Bước 2: Tạo chiến dịch đầu tiên"
          action={
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => setStep(1)}>
                Quay lại
              </Button>
              <Button
                size="sm"
                onClick={handleNextFromStep2}
                loading={loading}
                disabled={loading}
                icon={<IconArrowRight size={15} />}
              >
                Tạo chiến dịch & Tiếp tục
              </Button>
            </div>
          }
        >
          <div className="space-y-4">
            {/* Lĩnh vực / Preset selector */}
            <Field label="Chọn lĩnh vực dịch vụ của bạn (Tự động điền gợi ý cấu hình)">
              <div className="grid gap-2 sm:grid-cols-2">
                {PRESETS.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => handlePresetChange(p.id)}
                    className={cx(
                      "flex items-center justify-between rounded-xl border p-3 text-left text-xs font-semibold transition-all cursor-pointer",
                      selectedPreset === p.id
                        ? "border-indigo-600 bg-indigo-50/70 text-indigo-950 dark:border-indigo-500 dark:bg-indigo-950/40 dark:text-indigo-200"
                        : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300",
                    )}
                  >
                    <span>{p.name}</span>
                    {selectedPreset === p.id && <IconCheck size={14} className="text-indigo-600" />}
                  </button>
                ))}
              </div>
            </Field>

            <Field label="Tên chiến dịch">
              <Input
                value={campaignName}
                onChange={(e) => setCampaignName(e.target.value)}
                placeholder="VD: Săn khách Thiết kế Website"
              />
            </Field>

            <Field
              label="Chế độ vận hành"
              hint="Bán tự động: Gửi bài về Telegram để bạn duyệt trước khi bắn comment. Tự động hoàn toàn: AI tự bắn ngay khi thấy bài phù hợp."
            >
              <div className="flex gap-4">
                <label className="flex items-center gap-2 text-xs font-medium cursor-pointer">
                  <input
                    type="radio"
                    name="mode"
                    checked={mode === "semi_auto"}
                    onChange={() => setMode("semi_auto")}
                  />
                  <span>Bán tự động (Khuyên dùng — An toàn nhất)</span>
                </label>
                <label className="flex items-center gap-2 text-xs font-medium cursor-pointer">
                  <input
                    type="radio"
                    name="mode"
                    checked={mode === "full_auto"}
                    onChange={() => setMode("full_auto")}
                  />
                  <span>Tự động hoàn toàn</span>
                </label>
              </div>
            </Field>

            <Field
              label="Hướng dẫn AI lọc bài (Prompt)"
              hint="Mô tả bằng tiếng Việt bài viết thế nào là phù hợp để AI lọc chính xác."
            >
              <Textarea
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                rows={2}
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Từ khóa ưu tiên (Whitelist)" hint="Cách nhau bằng dấu phẩy">
                <Input
                  value={whitelist}
                  onChange={(e) => setWhitelist(e.target.value)}
                  placeholder="thiết kế, website, logo..."
                />
              </Field>

              <Field label="Từ khóa loại trừ (Blacklist)" hint="Cách nhau bằng dấu phẩy">
                <Input
                  value={blacklist}
                  onChange={(e) => setBlacklist(e.target.value)}
                  placeholder="tuyển dụng, đa cấp, lừa đảo..."
                />
              </Field>
            </div>
          </div>
        </Card>
      )}

      {/* ── STEP 3: NẠP TÀI KHOẢN CLONE ─────────────────────────────────── */}
      {step === 3 && (
        <Card
          title="Bước 3: Nạp tài khoản Clone Facebook"
          action={
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => setStep(2)}>
                Quay lại
              </Button>
              <Button
                size="sm"
                onClick={handleNextFromStep3}
                loading={loading}
                disabled={loading}
                icon={<IconArrowRight size={15} />}
              >
                {cookieInput.trim() ? "Nạp cookie & Tiếp tục" : "Bỏ qua bước này"}
              </Button>
            </div>
          }
        >
          <div className="space-y-4">
            <div className="rounded-xl border border-indigo-100 bg-indigo-50/60 p-4 dark:border-indigo-950 dark:bg-indigo-950/30">
              <h4 className="text-xs font-bold text-indigo-900 dark:text-indigo-300 flex items-center gap-1.5">
                <IconShieldCheck size={16} /> Hướng dẫn lấy cookie Facebook 30 giây:
              </h4>
              <ol className="mt-2 space-y-1 text-xs text-indigo-800 dark:text-indigo-200 list-decimal list-inside leading-relaxed">
                <li>Cài tiện ích <strong>Cookie-Editor</strong> trên trình duyệt Chrome/Edge.</li>
                <li>Đăng nhập tài khoản Facebook phụ (clone) của bạn trên trình duyệt.</li>
                <li>Mở tiện ích Cookie-Editor → Chọn <strong>Export</strong> → Chọn <strong>Export as JSON</strong>.</li>
                <li>Dán nội dung vừa copy vào ô bên dưới hoặc kéo thả file.</li>
              </ol>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Tên gợi nhớ của tài khoản clone">
                <Input
                  value={cloneName}
                  onChange={(e) => setCloneName(e.target.value)}
                  placeholder="VD: Nick Clone Mai Phương"
                />
              </Field>

              <Field label="Phân công vai trò">
                <Select value={cloneRole} onChange={(e) => setCloneRole(e.target.value)}>
                  <option value="scout">Nick Quét bài (Scout — Chỉ đọc, an toàn tuyệt đối)</option>
                  <option value="shooter">Nick Bắn comment ứng tuyển (Shooter)</option>
                  <option value="both">Cả hai vai trò (Quét bài & Bắn comment)</option>
                </Select>
              </Field>
            </div>

            <Field
              label="Nội dung Cookie (JSON hoặc Netscape)"
              hint="Hệ thống tự động mã hóa bảo mật chuẩn Fernet trước khi lưu vào cơ sở dữ liệu."
            >
              <Textarea
                value={cookieInput}
                onChange={(e) => setCookieInput(e.target.value)}
                placeholder='[{"name": "c_user", "value": "..."}, {"name": "xs", "value": "..."}]'
                rows={4}
                className="font-mono text-xs"
              />
            </Field>

            {cloneAdded && (
              <div className="rounded-xl bg-emerald-50 p-3 text-xs font-semibold text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300 flex items-center gap-2">
                <IconCheck size={16} /> Đã nạp thành công 1 tài khoản clone vào hệ thống!
              </div>
            )}
          </div>
        </Card>
      )}

      {/* ── STEP 4: THÊM NHÓM FACEBOOK ──────────────────────────────────── */}
      {step === 4 && (
        <Card
          title="Bước 4: Thêm nhóm Facebook mục tiêu"
          action={
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => setStep(3)}>
                Quay lại
              </Button>
              <Button size="sm" onClick={handleNextFromStep4} icon={<IconArrowRight size={15} />}>
                Tiếp tục: Kịch bản
              </Button>
            </div>
          }
        >
          <div className="space-y-4">
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Nhập các đường link Facebook Group bạn muốn AI theo dõi bài viết săn lead.
            </p>

            <div className="flex flex-wrap items-end gap-3">
              <div className="flex-1 min-w-[240px]">
                <Field label="URL Group Facebook">
                  <Input
                    value={groupUrl}
                    onChange={(e) => setGroupUrl(e.target.value)}
                    placeholder="https://www.facebook.com/groups/congdongstartup/"
                  />
                </Field>
              </div>
              <div className="w-48">
                <Field label="Tên gợi nhớ">
                  <Input
                    value={groupName}
                    onChange={(e) => setGroupName(e.target.value)}
                    placeholder="Cộng đồng Startup"
                  />
                </Field>
              </div>
              <Button
                type="button"
                onClick={handleAddGroup}
                loading={loading}
                disabled={loading || !groupUrl.trim()}
                icon={<IconPlus size={15} />}
              >
                Thêm nhóm
              </Button>
            </div>

            {/* Danh sách nhóm đã thêm */}
            <div className="mt-4 rounded-xl border border-slate-200/80 bg-slate-50/50 p-4 dark:border-slate-800 dark:bg-slate-900/40">
              <h5 className="text-xs font-bold text-slate-700 dark:text-slate-300">
                Nhóm đã thêm vào chiến dịch ({groupsAdded.length}):
              </h5>
              {groupsAdded.length === 0 ? (
                <p className="mt-2 text-xs italic text-slate-400">
                  Chưa có nhóm nào. Bạn có thể thêm ngay hoặc sử dụng tính năng &quot;Tự lấy nhóm đã tham gia&quot; sau trong Dashboard.
                </p>
              ) : (
                <ul className="mt-2 space-y-1.5 text-xs text-slate-700 dark:text-slate-300">
                  {groupsAdded.map((name, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <IconFacebook size={14} className="text-indigo-600" />
                      <span>{name}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </Card>
      )}

      {/* ── STEP 5: SOẠN KỊCH BẢN & KẾT NỐI TELEGRAM ─────────────────────── */}
      {step === 5 && (
        <Card
          title="Bước 5: Kịch bản phản hồi & Kết nối Telegram Bot"
          action={
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => setStep(4)}>
                Quay lại
              </Button>
              <Button
                size="sm"
                onClick={handleCompleteStep5}
                loading={loading}
                disabled={loading}
                icon={<IconSparkles size={15} />}
              >
                Hoàn tất cài đặt
              </Button>
            </div>
          }
        >
          <div className="space-y-5">
            {/* Box Telegram */}
            <div className="rounded-2xl border border-blue-200 bg-blue-50/70 p-5 dark:border-blue-900/60 dark:bg-blue-950/30">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-blue-600 text-white">
                  <IconTelegram size={18} />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-blue-950 dark:text-blue-200">
                    Liên kết Telegram Bot để duyệt lead 1 chạm
                  </h4>
                  <p className="text-xs text-blue-800/80 dark:text-blue-300/80">
                    Khi AI phát hiện bài viết mới, bot sẽ gửi thẻ thông báo đến điện thoại của bạn.
                  </p>
                </div>
              </div>

              {telegramCode ? (
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                    Mã liên kết của bạn:
                  </span>
                  <code className="rounded-lg bg-white px-3 py-1 text-sm font-bold tracking-wider text-blue-700 shadow-xs dark:bg-slate-900 dark:text-blue-300">
                    /start {telegramCode}
                  </code>
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={() => {
                      navigator.clipboard.writeText(`/start ${telegramCode}`);
                      toast.info("Đã sao chép cú pháp liên kết!");
                    }}
                    icon={<IconCopy size={13} />}
                  >
                    Sao chép
                  </Button>
                  <a
                    href={`https://t.me/CommHunterBot?start=${telegramCode}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <Button size="xs" icon={<IconExternalLink size={13} />}>
                      Mở bot trên Telegram
                    </Button>
                  </a>
                </div>
              ) : (
                <p className="mt-3 text-xs text-blue-700 dark:text-blue-400">
                  (Bạn có thể kết nối bot Telegram bất kỳ lúc nào trong mục Cài đặt).
                </p>
              )}
            </div>

            {/* Kịch bản Spintax */}
            <div className="space-y-3">
              <Field label="Tên kịch bản">
                <Input
                  value={scriptTitle}
                  onChange={(e) => setScriptTitle(e.target.value)}
                  placeholder="Kịch bản chào hàng chính"
                />
              </Field>

              <Field
                label="Nội dung kịch bản Spintax (Chống trùng lặp lời)"
                hint="Dùng cú pháp {tùy chọn 1|tùy chọn 2} để hệ thống tự động xoay chuyển ngẫu nhiên câu chữ khi comment."
              >
                <Textarea
                  value={scriptContent}
                  onChange={(e) => setScriptContent(e.target.value)}
                  rows={3}
                />
              </Field>

              {/* Ô xem trước */}
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs dark:border-slate-800 dark:bg-slate-900/60">
                <div className="flex items-center justify-between text-slate-500 mb-1">
                  <span className="font-semibold text-slate-700 dark:text-slate-300">
                    Xem trước biến thể mẫu:
                  </span>
                  <button
                    type="button"
                    onClick={() => setPreviewSample(renderSpintax(scriptContent))}
                    className="flex items-center gap-1 text-indigo-600 hover:underline cursor-pointer"
                  >
                    <IconRefresh size={12} /> Đổi câu khác
                  </button>
                </div>
                <p className="text-slate-800 dark:text-slate-200 italic">&quot;{previewSample}&quot;</p>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* ── STEP 6: HOÀN TẤT THIẾT LẬP ─────────────────────────────────── */}
      {step === 6 && (
        <Card title="Chúc mừng! Thiết lập hoàn tất">
          <div className="flex flex-col items-center justify-center py-6 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-600 shadow-lg shadow-emerald-500/20 dark:bg-emerald-950 dark:text-emerald-400 mb-4">
              <IconCheck size={32} />
            </div>

            <h3 className="text-xl font-bold text-slate-900 dark:text-white">
              Chiến dịch của bạn đã sẵn sàng hoạt động!
            </h3>
            <p className="mt-2 max-w-md text-xs text-slate-500 dark:text-slate-400">
              CommHunter AI sẽ bắt đầu quét các nhóm Facebook theo lịch trình, đối chiếu từ khóa và báo lead mới về điện thoại của bạn.
            </p>

            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <Link href="/dashboard">
                <Button size="lg" icon={<IconDashboard size={18} />}>
                  Khám phá Dashboard ngay
                </Button>
              </Link>
              {createdCampaignId && (
                <Link href={`/campaigns/${createdCampaignId}`}>
                  <Button variant="ghost" size="lg">
                    Xem chi tiết chiến dịch
                  </Button>
                </Link>
              )}
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
