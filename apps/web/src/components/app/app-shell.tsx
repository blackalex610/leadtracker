import {
  LayoutDashboardIcon,
  ListIcon,
  LogOutIcon,
  MegaphoneIcon,
  MoonIcon,
  SearchIcon,
  SettingsIcon,
  SunIcon,
} from "lucide-react";
import { Suspense } from "react";
import { NavLink, Outlet } from "react-router";

import { StartCallingDialog } from "@/components/app/start-calling-dialog";
import { PageFallback } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { useAuth } from "@/lib/auth";
import { useMeta } from "@/lib/queries";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboardIcon, end: true },
  { to: "/search", label: "Find Leads", icon: SearchIcon, end: false },
  { to: "/leads", label: "Leads", icon: ListIcon, end: false },
  { to: "/campaigns", label: "Campaigns", icon: MegaphoneIcon, end: false },
  { to: "/settings", label: "Settings", icon: SettingsIcon, end: false },
];

function navClass({ isActive }: { isActive: boolean }) {
  return cn(
    "flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
    isActive && "bg-accent text-foreground",
  );
}

export function AppShell() {
  const { theme, toggle } = useTheme();
  const { user, authMode, logout } = useAuth();
  const meta = useMeta();
  const demo = meta.data?.provider.demo_mode;

  return (
    <div className="flex h-dvh flex-col md:flex-row">
      <aside className="flex shrink-0 flex-row items-center gap-1 border-b bg-sidebar px-2 py-1.5 md:w-52 md:flex-col md:items-stretch md:border-r md:border-b-0 md:px-2 md:py-3">
        <div className="flex items-center gap-2 px-2 md:mb-4">
          <span className="grid size-6 place-items-center rounded bg-foreground text-[11px] font-bold text-background">LT</span>
          <span className="hidden text-[13px] font-semibold md:inline">Lead Tracker</span>
        </div>
        <nav className="flex flex-1 flex-row gap-0.5 overflow-x-auto md:flex-col" aria-label="Main">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
              <item.icon className="size-4" aria-hidden />
              <span className="hidden sm:inline">{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center gap-1 md:flex-col md:items-stretch md:gap-2">
          <StartCallingDialog
            trigger={
              <Button size="sm" className="md:w-full">
                <span className="hidden sm:inline">Start Calling Session</span>
                <span className="sm:hidden">Call</span>
              </Button>
            }
          />
          <div className="flex items-center justify-between gap-1 md:px-1">
            <span className="hidden truncate text-xs text-muted-foreground md:inline" title={user?.email}>
              {user?.name}
            </span>
            <div className="flex">
              <Tooltip content={theme === "dark" ? "Light mode" : "Dark mode"}>
                <Button variant="ghost" size="icon-sm" onClick={toggle} aria-label="Toggle theme">
                  {theme === "dark" ? <SunIcon /> : <MoonIcon />}
                </Button>
              </Tooltip>
              {authMode === "token" && (
                <Tooltip content="Sign out">
                  <Button variant="ghost" size="icon-sm" onClick={logout} aria-label="Sign out">
                    <LogOutIcon />
                  </Button>
                </Tooltip>
              )}
            </div>
          </div>
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
        {demo && (
          <div className="border-b border-warm/30 bg-warm-soft px-5 py-1 text-xs text-warm" role="status">
            <strong>Demo mode</strong> — searches return clearly synthetic businesses. Dialing is disabled for demo records.
          </div>
        )}
        <Suspense fallback={<PageFallback />}>
          <Outlet />
        </Suspense>
      </main>
    </div>
  );
}
