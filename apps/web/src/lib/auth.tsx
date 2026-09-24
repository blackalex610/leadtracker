import type { User } from "@leadtracker/shared";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";

import { ErrorState, PageFallback } from "@/components/app/states";
import { ApiError, api, UNAUTHORIZED_EVENT } from "@/lib/api";
import { keys } from "@/lib/queries";

interface AuthValue {
  user: User | null;
  authMode: string;
  logout: () => void;
}

const AuthContext = createContext<AuthValue>({ user: null, authMode: "none", logout: () => {} });

export function useAuth() {
  return useContext(AuthContext);
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const me = useQuery({ queryKey: keys.me, queryFn: api.me, retry: false, staleTime: 5 * 60_000 });

  useEffect(() => {
    const onUnauthorized = () => {
      client.clear();
      navigate(`/login?next=${encodeURIComponent(location.pathname + location.search)}`, { replace: true });
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [client, navigate, location]);

  const logout = useCallback(() => {
    void api.logout().finally(() => {
      client.clear();
      navigate("/login", { replace: true });
    });
  }, [client, navigate]);

  const value = useMemo<AuthValue>(
    () => ({ user: me.data?.user ?? null, authMode: me.data?.auth_mode ?? "none", logout }),
    [me.data, logout],
  );

  if (me.isPending) return <PageFallback />;
  if (me.error) {
    if (me.error instanceof ApiError && me.error.status === 401) {
      return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
    }
    return <ErrorState error={me.error} onRetry={() => void me.refetch()} className="h-dvh justify-center" />;
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
