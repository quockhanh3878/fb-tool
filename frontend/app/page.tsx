"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { tokens } from "@/lib/api";

/** Trang gốc chỉ điều hướng: có token thì vào dashboard, chưa thì ra đăng nhập. */
export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(tokens.access() ? "/dashboard" : "/login");
  }, [router]);
  return <p className="p-8 text-sm text-slate-500">Đang chuyển hướng…</p>;
}
