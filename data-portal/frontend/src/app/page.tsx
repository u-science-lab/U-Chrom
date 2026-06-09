import { listDatasets } from "@/lib/api";

export default async function HomePage() {
  let datasets;
  try {
    datasets = await listDatasets();
  } catch {
    return (
      <p className="text-gray-500">暂无法加载数据集，请确认后端服务已启动。</p>
    );
  }

  if (datasets.length === 0) {
    return <p className="text-gray-500">暂无数据集。</p>;
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {datasets.map((d) => (
        <a
          key={d.id}
          href={`/datasets/${d.id}`}
          className="rounded-lg border bg-white p-4 hover:shadow-md transition"
        >
          <h2 className="font-semibold">{d.title}</h2>
          <p className="mt-1 text-sm text-gray-500">
            {d.organism} · {d.technology}
          </p>
          <p className="mt-2 text-sm">
            {d.n_cells.toLocaleString()} cells · {d.n_markers} markers
          </p>
        </a>
      ))}
    </div>
  );
}
