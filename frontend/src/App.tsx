import { NavLink, Outlet, useLocation } from "react-router-dom";
import { createBrowserRouter } from "react-router-dom";
import type { ReactElement } from "react";

import Health from "./pages/Health";
import Models from "./pages/Models";
import Overview from "./pages/Overview";
import Performance from "./pages/Performance";
import Projects from "./pages/Projects";
import Trends from "./pages/Trends";

export const VIEWS = [
  { path: "/", label: "总览" },
  { path: "/trends", label: "日趋势" },
  { path: "/models", label: "按模型" },
  { path: "/projects", label: "按项目" },
  { path: "/performance", label: "性能" },
  { path: "/health", label: "健康度" },
] as const;

const PAGE_ELEMENTS: Record<(typeof VIEWS)[number]["path"], ReactElement> = {
  "/": <Overview />,
  "/trends": <Trends />,
  "/models": <Models />,
  "/projects": <Projects />,
  "/performance": <Performance />,
  "/health": <Health />,
};

function Layout() {
  const { pathname } = useLocation();
  const current = VIEWS.find((v) => v.path === pathname)?.label ?? "zlens";

  return (
    <div className="flex min-h-screen">
      <nav className="flex w-52 shrink-0 flex-col border-r border-zinc-800/80 px-4 py-6">
        <div className="mb-8 px-2">
          <span className="text-xl font-semibold tracking-tight">zlens</span>
          <p className="mt-1 text-xs text-zinc-500">coding agent 用量透镜</p>
        </div>
        <ul className="space-y-1">
          {VIEWS.map((view) => (
            <li key={view.path}>
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
      <main className="flex-1 px-10 py-8">
        <h1 className="mb-6 text-2xl font-semibold tracking-tight">{current}</h1>
        <Outlet />
      </main>
    </div>
  );
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: VIEWS.map(({ path }) => ({ path, element: PAGE_ELEMENTS[path] })),
  },
]);
