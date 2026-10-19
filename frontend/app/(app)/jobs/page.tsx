// plan: docs/plans/community_job_runner_plan.md
"use client";

import { useState } from "react";

import { IconHeartPulse } from "@/components/icons";
import { Badge, Button, Card, Empty, ErrorNote, Spinner, fmtDate, useAsync, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import type { JobStatus } from "@/lib/types";

export default function JobsPage() {
  const jobs = useAsync(() => api.jobs());
  const toast = useToast();
  const [busy, setBusy] = useState("");

  async function toggle(job: JobStatus) {
    setBusy(job.job_name);
    try {
      if (job.status === "paused") await api.resumeJob(job.job_name);
      else await api.pauseJob(job.job_name);
      toast.info(job.status === "paused" ? "Đã cho job chạy lại" : "Đã tạm dừng job");
      jobs.reload();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Không cập nhật được job");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
            <IconHeartPulse size={18} />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-2xl">Job vận hành</h1>
        </div>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Theo dõi lần chạy gần nhất, lỗi và ngắt mạch từng job.</p>
      </header>

      <ErrorNote>{jobs.error}</ErrorNote>
      {jobs.loading && <Spinner label="Đang tải trạng thái job…" />}
      {!jobs.loading && !jobs.data?.length && <Empty>Chưa có dữ liệu job.</Empty>}
      <div className="grid gap-4 md:grid-cols-2">
        {jobs.data?.map((job) => (
          <Card key={job.job_name} title={job.job_name} action={<Badge value={job.status} />}>
            <div className="space-y-2 text-xs text-slate-500 dark:text-slate-400">
              <p>Bắt đầu: <span className="font-medium text-slate-700 dark:text-slate-200">{fmtDate(job.started_at)}</span></p>
              <p>Kết thúc: <span className="font-medium text-slate-700 dark:text-slate-200">{fmtDate(job.finished_at)}</span></p>
              {job.error && <p className="rounded-lg bg-rose-50 p-2 text-rose-700 dark:bg-rose-950/30 dark:text-rose-300">{job.error}</p>}
            </div>
            <div className="mt-4 flex justify-end">
              <Button size="sm" variant={job.status === "paused" ? "primary" : "outline"} loading={busy === job.job_name} onClick={() => toggle(job)}>
                {job.status === "paused" ? "Chạy lại" : "Tạm dừng"}
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
