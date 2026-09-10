"use client";
import { useEffect, useState } from "react";
import { IconMoon, IconSun } from "./icons";
import { cx } from "./ui";

export function ThemeToggle({ className = "" }: { className?: string }) {
  const [theme, setTheme] = useState<"light" | "dark">("dark");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const stored = localStorage.getItem("commhunter_theme");
    if (stored === "light" || stored === "dark") {
      setTheme(stored);
      document.documentElement.classList.toggle("dark", stored === "dark");
    } else {
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      setTheme(prefersDark ? "dark" : "light");
      document.documentElement.classList.toggle("dark", prefersDark);
    }
  }, []);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("commhunter_theme", next);
    document.documentElement.classList.toggle("dark", next === "dark");
  }

  if (!mounted) {
    return (
      <div className={cx("h-9 w-9 rounded-lg border border-slate-200 dark:border-slate-800", className)} />
    );
  }

  return (
    <button
      type="button"
      onClick={toggle}
      title={theme === "dark" ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"}
      aria-label="Chuyển chế độ sáng tối"
      className={cx(
        "flex h-9 w-9 items-center justify-center rounded-lg border transition-all duration-200",
        "border-slate-200/80 bg-white/80 text-slate-700 shadow-xs hover:border-slate-300 hover:bg-slate-100",
        "dark:border-slate-800/80 dark:bg-slate-900/80 dark:text-slate-200 dark:hover:border-slate-700 dark:hover:bg-slate-800",
        className,
      )}
    >
      {theme === "dark" ? (
        <IconSun size={17} className="text-amber-400 transition-transform duration-200 hover:rotate-45" />
      ) : (
        <IconMoon size={17} className="text-indigo-600 transition-transform duration-200 hover:-rotate-12" />
      )}
    </button>
  );
}
