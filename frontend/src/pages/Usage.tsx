import { useNavigate, useParams } from "react-router-dom";

import Segmented from "../components/Segmented";
import Models from "./Models";
import Projects from "./Projects";
import Trends from "./Trends";

const TABS = [
  { key: "trends", label: "日趋势" },
  { key: "models", label: "按模型" },
  { key: "projects", label: "按项目" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

// One nav entry ("用量分析") hosts the three usage cuts as in-page tabs;
// sub-routes keep each tab deep-linkable.
export default function Usage() {
  const { tab } = useParams();
  const navigate = useNavigate();
  const active: TabKey = TABS.some((t) => t.key === tab) ? (tab as TabKey) : "trends";

  return (
    <div className="space-y-6">
      <Segmented
        value={active}
        options={TABS.map(({ key, label }) => ({ key, label }))}
        onChange={(key) => navigate(`/usage/${key}`)}
      />
      {active === "trends" && <Trends />}
      {active === "models" && <Models />}
      {active === "projects" && <Projects />}
    </div>
  );
}
