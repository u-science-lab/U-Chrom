"use client";

import { useState } from "react";
import { apiBase, type DatasetDetail } from "@/lib/api";

const TABS = ["Overview", "Notebook", "Download"] as const;
type Tab = (typeof TABS)[number];

export function DetailTabs({ ds }: { ds: DatasetDetail }) {
  const [tab, setTab] = useState<Tab>("Overview");

  return (
    <div>
      <div className="flex gap-2 border-b">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm ${
              tab === t ? "border-b-2 border-gray-900 font-medium" : "text-gray-500"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {tab === "Overview" && <Overview ds={ds} />}
        {tab === "Notebook" && <Notebook ds={ds} />}
        {tab === "Download" && <Download ds={ds} />}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border bg-white p-4 text-center">
      <div className="text-xl font-semibold">
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  );
}

function Overview({ ds }: { ds: DatasetDetail }) {
  const code = `from uchrom.datasets import load_dataset\n\ncd = load_dataset("${ds.id}")  # SDK coming soon`;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="cells" value={ds.n_cells} />
        <Stat label="traces" value={ds.n_traces} />
        <Stat label="spots" value={ds.n_spots} />
        <Stat label="markers" value={ds.n_markers} />
      </div>
      {ds.description && <p className="text-sm">{ds.description}</p>}
      {Object.keys(ds.cell_types).length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-medium">Cell types</h3>
          <ul className="text-sm text-gray-600">
            {Object.entries(ds.cell_types).map(([k, v]) => (
              <li key={k}>{k}: {v.toLocaleString()}</li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <h3 className="mb-2 text-sm font-medium">Load in Python</h3>
        <pre className="overflow-x-auto rounded-lg bg-gray-900 p-4 text-xs text-gray-100">
          <code>{code}</code>
        </pre>
      </div>
    </div>
  );
}

function Notebook({ ds }: { ds: DatasetDetail }) {
  if (!ds.notebook_available) {
    return <p className="text-gray-500">该数据集的 notebook 暂不可用。</p>;
  }
  return (
    <iframe
      src={`${apiBase}/api/datasets/${ds.id}/notebook`}
      className="h-[70vh] w-full rounded-lg border"
      title="notebook"
      loading="lazy"
    />
  );
}

function Download({ ds }: { ds: DatasetDetail }) {
  return (
    <div className="space-y-3">
      {ds.files.map((f) => (
        <a
          key={f.url}
          href={f.url}
          className="flex items-center justify-between rounded-lg border bg-white p-4 hover:shadow-sm"
        >
          <span className="text-sm font-medium">{f.label}</span>
          <span className="text-xs text-gray-500">
            {f.format}{f.size_mb ? ` · ${f.size_mb} MB` : ""}
          </span>
        </a>
      ))}
      {ds.analyzer_url && (
        <a
          href={ds.analyzer_url}
          className="block rounded-lg bg-gray-900 p-4 text-center text-sm text-white"
        >
          在 Analyzer 中打开
        </a>
      )}
    </div>
  );
}
