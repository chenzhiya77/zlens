import { Navigate, NavLink, Outlet, useLocation } from "react-router-dom";
import { createBrowserRouter } from "react-router-dom";
import type { ReactElement } from "react";

import Overview from "./pages/Overview";
import Pricing from "./pages/Pricing";
import Runtime from "./pages/Runtime";
import Settings from "./pages/Settings";
import Usage from "./pages/Usage";

// Sidebar grouped by purpose: analysis views vs configuration. "用量分析"
// hosts its three cuts as in-page tabs (see pages/Usage.tsx). `ownTitle` marks
// pages that render their own content header (T23 design) instead of the shell h1.
const NAV: { path: string; label: string; group: string | null; ownTitle?: boolean }[] = [
  { path: "/", label: "总览", group: null, ownTitle: true },
  { path: "/usage", label: "用量分析", group: "分析" },
  { path: "/runtime", label: "运行质量", group: "分析" },
  { path: "/pricing", label: "价格表", group: "配置" },
  { path: "/settings", label: "设置", group: "配置" },
];

function isActive(pathname: string, path: string): boolean {
  return path === "/" ? pathname === "/" : pathname.startsWith(path);
}

function Layout() {
  const { pathname } = useLocation();
  const nav = NAV.find((v) => isActive(pathname, v.path));
  const current = nav?.label ?? "zlens";

  return (
    <div className="flex min-h-screen">
      <nav className="flex w-52 shrink-0 flex-col border-r border-zinc-800/80 px-4 py-6">
        <div className="mb-8 px-2">
          <span className="text-xl font-semibold tracking-tight">zlens</span>
          <p className="mt-1 text-xs text-zinc-500">coding agent 用量透镜</p>
        </div>
        <ul className="space-y-1">
          {NAV.map((view, index) => (
            <li key={view.path}>
              {view.group && NAV[index - 1]?.group !== view.group && (
                <p className="mb-1 mt-4 px-3 text-[11px] font-medium text-zinc-600">
                  {view.group}
                </p>
              )}
              <NavLink
                to={view.path}
                end={view.path === "/"}
                className={({ isActive }) =>
                  `block rounded-md px-3 py-2 text-sm transition-colors ${
                    isActive
                      ? "bg-zinc-800 text-zinc-100"
                      : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
                  }`
                }
              >
                {view.label}
              </NavLink>
            </li>
          ))}
        </ul>
        <p className="mt-auto px-2 text-[11px] leading-relaxed text-zinc-600">
          只读本机 ZCode 数据库
          <br />
          不影响进行中的对话
        </p>
      </nav>
      <main className="min-w-0 flex-1 px-10 py-8">
        {!nav?.ownTitle && <h1 className="mb-6 text-2xl font-semibold tracking-tight">{current}</h1>}
        <Outlet />
      </main>
    </div>
  );
}

const PAGES: Record<string, ReactElement> = {
  overview: <Overview />,
  usage: <Usage />,
  runtime: <Runtime />,
  pricing: <Pricing />,
  settings: <Settings />,
};

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { path: "/", element: PAGES.overview },
      { path: "/usage", element: <Navigate to="/usage/trends" replace /> },
      { path: "/usage/:tab", element: PAGES.usage },
      { path: "/runtime", element: PAGES.runtime },
      { path: "/pricing", element: PAGES.pricing },
      { path: "/settings", element: PAGES.settings },
    ],
  },
]);
