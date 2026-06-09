import { notFound } from "next/navigation";
import { getDataset } from "@/lib/api";
import { DetailTabs } from "./DetailTabs";

export default async function DatasetPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const ds = await getDataset(id);
  if (!ds) notFound();

  return (
    <div>
      <a href="/" className="text-sm text-gray-500 hover:text-gray-900">← Back</a>
      <h1 className="mt-2 text-2xl font-semibold">{ds.title}</h1>
      <p className="mt-1 text-sm text-gray-500">
        {ds.organism} · {ds.assembly} · {ds.technology}
        {ds.doi ? ` · DOI:${ds.doi}` : ""}
      </p>
      <div className="mt-6">
        <DetailTabs ds={ds} />
      </div>
    </div>
  );
}
