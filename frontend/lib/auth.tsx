"use client";
/** Ngữ cảnh đăng nhập: giữ hồ sơ người dùng + gói cước cho toàn bộ dashboard. */
import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api, tokens } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  /** true khi phiên này vừa tự đăng nhập qua /api/auth/desktop-session (RUN_MODE=desktop). */
  isDesktop: boolean;
  refreshUser: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  isDesktop: false,
  refreshUser: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [isDesktop, setIsDesktop] = useState(false);

  const refreshUser = useCallback(async () => {
    // Chế độ desktop: 1 máy = 1 user, LUÔN tự cấp token mới kể cả khi đã có token
    // (token cũ có thể hỏng; và phải biết isDesktop ở mọi lần mở app, không chỉ
    // lần đầu). Chế độ SaaS: endpoint trả 404 -> giữ token đang có, không có thì
    // rơi về màn đăng nhập như cũ.
    try {
      tokens.save(await api.desktopSession());
      setIsDesktop(true);
    } catch {
      if (!tokens.access()) {
        setUser(null);
        setLoading(false);
        return;
      }
    }
    try {
      setUser(await api.me());
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    tokens.clear();
    setUser(null);
    router.push("/login");
  }, [router]);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  const value = useMemo(
    () => ({ user, loading, isDesktop, refreshUser, logout }),
    [user, loading, isDesktop, refreshUser, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
