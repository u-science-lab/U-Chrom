import { createApp, computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  BookOpen,
  CircleDot,
  Crosshair,
  ExternalLink,
  GitBranch,
  Moon,
  Notebook,
  Search,
  Sun,
  Waypoints,
  X,
  ZoomIn,
  ZoomOut
} from "@lucide/vue";
import "./style.css";

const rawGraph = JSON.parse(document.getElementById("uchrom-idea-graph-data").textContent);
const notebookBaseUrl = rawGraph.notebook_base_url || "";

const cdataNode = {
  id: "virtual:cdata",
  kind: "CData",
  title: rawGraph.graph_id || "cdata",
  summary: "Root object for this auto-discovery run. Browse downward from the dataset to first-round ideas, notebook evidence, follow-up directions, and second-round ideas.",
  n_nodes: rawGraph.summary?.n_nodes ?? rawGraph.nodes.length,
  n_edges: rawGraph.summary?.n_edges ?? rawGraph.edges.length
};

const nodes = [cdataNode, ...rawGraph.nodes];
const edges = rawGraph.edges;
const byId = new Map(nodes.map((n) => [n.id, n]));

const colors = {
  CData: "#4c95df",
  Group: "#7186a3",
  Idea: "#4c78a8",
  EvidenceResult: "#45a36b",
  LiteratureClaim: "#f28e2b",
  Direction: "#f1ce63",
  HandoffGap: "#8b95a3",
  Conclusion: "#8b95a3",
  NotebookRun: "#9c755f",
  Run: "#6b7280"
};

const scientificStatusOrder = ["Supported", "Borderline", "Contradicted", "Not supported", "Inconclusive"];
const auditStatusOrder = ["Pending", "Failed", "Rejected"];
const statusOrder = [...scientificStatusOrder, ...auditStatusOrder];
const notebookVisualSpecs = {
  graphic: {
    title: "Graphical abstract",
    fragment: "Graphical-abstract",
    headingText: "graphical abstract",
    altMatches: ["scientific schematic", "graphical abstract"],
    fallbackAlt: "Graphical abstract"
  },
  statistical: {
    title: "Statistical figure",
    fragment: "Statistical-figure",
    headingText: "statistical figure",
    altMatches: ["statistical figure", "statistical analysis"],
    fallbackAlt: "Statistical figure"
  }
};
const NODE_WIDTH = 232;
const NODE_HEIGHT = 94;
const NODE_GAP = 270;
const LEVEL_GAP = 154;
const HORIZONTAL_NODE_GAP = 94;
const HORIZONTAL_LEVEL_GAP = 300;
const ROUND_NODE_GAP = 132;
const ROUND_LANE_GAP = 190;
const ROUND_ROOT_LANE_GAP = 170;
const GRAPH_PADDING = 112;
const MIN_ZOOM = 0.08;
const MAX_ZOOM = 1.85;
const MINIMAP_WIDTH = 220;
const MINIMAP_HEIGHT = 136;
const THEME_STORAGE_KEY = "uchrom-idea-graph-theme";

const outcomeRelations = new Set(["supports", "borderline_supports", "contradicts", "not_supports", "inconclusive_for"]);

function initialThemeMode() {
  try {
    const stored = window.localStorage?.getItem(THEME_STORAGE_KEY);
    if (stored === "dark" || stored === "light") return stored;
  } catch {
    // Ignore storage failures and keep the graph in its original light mode.
  }
  return "light";
}

function applyThemeMode(mode) {
  const next = mode === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = next;
  document.documentElement.style.colorScheme = next;
  try {
    window.localStorage?.setItem(THEME_STORAGE_KEY, next);
  } catch {
    // Theme state is still applied even when storage is unavailable.
  }
}

function label(n) {
  if (!n) return "";
  return n.title || n.label || n.claim || n.idea_id || n.claim_id || n.reference_id || n.id;
}

function displayKind(n) {
  if (!n) return "Node";
  if (n.kind === "Group") return "Group";
  if (n.kind === "Direction") return "Follow-up direction";
  if (n.kind === "EvidenceResult") return "Evidence";
  if (n.kind === "HandoffGap") return "Handoff gap";
  return n.kind || "Node";
}

function truncate(s, n = 90) {
  s = String(s || "");
  return s.length > n ? `${s.slice(0, n - 1)}...` : s;
}

function formatNumber(x) {
  const n = Number(x);
  if (!Number.isFinite(n)) return String(x);
  if (Math.abs(n) < 0.001 && n !== 0) return n.toExponential(2);
  return n.toPrecision(3);
}

function relationLabel(relation) {
  const labels = {
    direction_proposed: "proposed idea",
    planned_direction: "planned direction",
    direction_based_on: "based on idea",
    direction_based_on_evidence: "based on evidence",
    generated: "generated",
    has_notebook: "has notebook",
    tested_by: "tested by",
    produced: "produced",
    supports: "supports",
    contradicts: "contradicts",
    not_supports: "does not support",
    borderline_supports: "borderline support",
    literature_supports: "literature supports",
    literature_related_to: "literature related"
  };
  return labels[relation] || String(relation || "").replaceAll("_", " ");
}

function evidenceForIdea(id) {
  const edge = edges.find((e) => e.target === id && outcomeRelations.has(e.relation));
  return edge ? byId.get(edge.source) : null;
}

function statusForIdea(id) {
  const ev = evidenceForIdea(id);
  if (ev?.hypothesis_status) return ev.hypothesis_status;
  const idea = byId.get(id);
  if (idea?.hypothesis_status) return idea.hypothesis_status;
  const state = String(idea?.execution_state || "").toLowerCase();
  if (idea?.review_accepted === false || state.includes("rejected")) return "Rejected";
  if (state.includes("failed")) return "Failed";
  if (state.includes("pending") || state.includes("not executed")) return "Pending";
  return "Pending";
}

function notebookForIdea(id) {
  const edge = edges.find((e) => e.source === id && e.relation === "tested_by");
  return edge ? byId.get(edge.target) : null;
}

function notebookHref(path) {
  if (!path) return "";
  if (!notebookBaseUrl) return path;
  const name = String(path).split("/").pop().replace(/\.ipynb$/, ".html");
  return `${notebookBaseUrl}/${name}`;
}

const graphicAbstractCache = new Map();

function notebookVisualSpec(kind) {
  return notebookVisualSpecs[kind] || notebookVisualSpecs.graphic;
}

function notebookVisualHref(href, kind) {
  if (!href) return "";
  return `${href}#${notebookVisualSpec(kind).fragment}`;
}

function headingTextMatches(heading, spec) {
  const text = (heading.textContent || "").replace(/¶/g, "").trim().toLowerCase();
  return text === spec.headingText;
}

function imageFromSection(heading) {
  let cursor = heading?.nextElementSibling;
  while (cursor && !/^H[1-4]$/.test(cursor.tagName)) {
    const img = cursor.matches?.("img") ? cursor : cursor.querySelector?.("img");
    if (img) return img;
    cursor = cursor.nextElementSibling;
  }
  return null;
}

function resolveNotebookImageSrc(src, href) {
  if (!src) return "";
  if (src.startsWith("data:") || /^https?:\/\//.test(src)) return src;
  try {
    return new URL(src, href || window.location.href).toString();
  } catch {
    return src;
  }
}

function extractNotebookVisual(html, href, kind = "graphic") {
  if (!html) return null;
  const spec = notebookVisualSpec(kind);
  const doc = new DOMParser().parseFromString(html, "text/html");
  const headings = [...doc.querySelectorAll("h1,h2,h3,h4")];
  const heading = doc.getElementById(spec.fragment)
    || headings.find((h) => headingTextMatches(h, spec));
  let img = imageFromSection(heading);
  img ||= [...doc.querySelectorAll("img")].find((candidate) => {
    const alt = candidate.getAttribute("alt")?.toLowerCase() || "";
    return spec.altMatches.some((match) => alt.includes(match));
  });
  const src = img?.getAttribute("src");
  if (!src) return null;
  return {
    src: resolveNotebookImageSrc(src, href),
    alt: img.getAttribute("alt") || spec.fallbackAlt
  };
}

function runIdeaIds(runId) {
  return [...new Set(edges
    .filter((e) => e.source === runId && e.relation === "generated")
    .map((e) => e.target)
    .filter((id) => byId.get(id)?.kind === "Idea"))];
}

function sortedRuns() {
  return nodes
    .filter((n) => n.kind === "Run")
    .sort((a, b) => runOrder(a) - runOrder(b) || label(a).localeCompare(label(b)));
}

function runOrder(run) {
  const text = `${run.id || ""} ${run.path || ""}`;
  const match = text.match(/iteration_(\d+)/);
  if (match) return Number(match[1]) + 1;
  return 1;
}

function claimSearchRound(claim) {
  const raw = claim?.raw || {};
  const text = [
    raw.search_iteration,
    claim?.search_iteration,
    raw.claim_id,
    claim?.claim_id,
    claim?.id,
  ].filter(Boolean).join(" ");
  const match = text.match(/iteration_(\d+)/);
  return match ? Number(match[1]) + 1 : null;
}

function runDisplayLabel(run) {
  const path = String(run?.path || run?.id || "");
  const name = path.split("/").filter(Boolean).pop() || run?.id || "";
  const text = `${run?.id || ""} ${run?.path || ""}`;
  const match = text.match(/iteration_(\d+)/);
  if (match) return `Round ${Number(match[1]) + 1}: ${name}`;
  return `Round 1 seed: ${name}`;
}

function runForIdea(ideaId) {
  const edge = edges.find((e) => e.relation === "generated" && e.target === ideaId);
  return edge ? byId.get(edge.source) : null;
}

function directionForIdea(idea) {
  const edge = edges.find((e) => e.relation === "direction_proposed" && e.target === idea.id);
  return edge ? byId.get(edge.source) : null;
}

function directionLabel(idea) {
  const direction = directionForIdea(idea);
  if (direction?.title) return direction.title;
  const id = direction?.direction_id || idea.direction_id || idea.metadata?.direction_id || "";
  const parts = String(id).split("-");
  const type = direction?.direction_type || (parts.length > 1 ? parts.slice(0, -1).join("-") : String(id));
  if (!id && !type) return "";
  return String(type || id).replaceAll("_", " ");
}

function contextUnavailable(idea) {
  const direction = directionForIdea(idea);
  const text = direction ? [
    direction.direction_id,
    direction.direction_type,
    direction.label,
    direction.title
  ].filter(Boolean).join(" ").toLowerCase() : [
    idea.iterative_context_status,
    idea.metadata?.iterative_context_status,
    idea.direction_id,
    idea.metadata?.direction_id
  ].filter(Boolean).join(" ").toLowerCase();
  return text.includes("context_unavailable")
    || text.includes("context unavailable")
    || text.includes("provided_paths_not_found")
    || text.includes("provided paths not found")
    || text.includes("not found")
    || text.includes("unavailable");
}

function parentIdeaIds(idea) {
  const raw = [
    ...(idea.signature?.parent_idea_ids || []),
    ...(idea.metadata?.parent_idea_ids || [])
  ];
  const ids = raw.map((id) => String(id).startsWith("idea:") ? String(id) : `idea:${id}`);
  for (const edge of edges.filter((e) => e.source === idea.id && e.relation === "derived_from")) ids.push(edge.target);
  const direction = directionForIdea(idea);
  if (direction) {
    for (const parent of direction.parent_idea_ids || []) {
      ids.push(String(parent).startsWith("idea:") ? String(parent) : `idea:${parent}`);
    }
    for (const edge of edges.filter((e) => e.source === direction.id && e.relation === "direction_based_on")) ids.push(edge.target);
  }
  return [...new Set(ids)].filter((id) => byId.get(id)?.kind === "Idea");
}

function sourceClaimIds(idea) {
  const raw = [
    ...(idea.signature?.source_claim_ids || []),
    ...(idea.metadata?.source_claim_ids || [])
  ];
  const ids = raw.map((id) => String(id).startsWith("literature_claim:") ? String(id) : `literature_claim:${slugForId(id)}`);
  for (const edge of edges.filter((e) => e.source === idea.id && e.relation === "motivated_by")) ids.push(edge.target);
  return [...new Set(ids)].filter((id) => byId.get(id)?.kind === "LiteratureClaim");
}

function claimIdsForIdea(idea) {
  const ids = [...sourceClaimIds(idea)];
  for (const edge of edges) {
    const relation = String(edge.relation || "");
    if (edge.target === idea.id && byId.get(edge.source)?.kind === "LiteratureClaim" && relation.startsWith("literature_")) {
      ids.push(edge.source);
    }
    if (edge.source === idea.id && byId.get(edge.target)?.kind === "LiteratureClaim") {
      ids.push(edge.target);
    }
  }
  return [...new Set(ids)].filter((id) => byId.get(id)?.kind === "LiteratureClaim");
}

function canonicalClaimIdForIdea(idea) {
  return claimIdsForIdea(idea)
    .sort((a, b) => label(byId.get(a)).localeCompare(label(byId.get(b))))
    [0] || "";
}

function claimIdeaIds(claimId) {
  return [...new Set(edges
    .filter((e) => e.source === claimId && String(e.relation || "").startsWith("literature_"))
    .map((e) => e.target)
    .filter((id) => byId.get(id)?.kind === "Idea"))];
}

function visibleClaimIdeaIds(claimId, visibleIdeaIds) {
  return claimIdeaIds(claimId).filter((id) => visibleIdeaIds.has(id));
}

function slugForId(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function directionTypeLabel(direction) {
  const raw = String(direction?.direction_type || direction?.label || "follow_up_direction");
  const known = {
    evidence_extension: "Evidence extension",
    negative_result_refinement: "Negative-result refinement",
    coverage_gap: "Coverage gap",
    cross_modal_bridge: "Cross-modal bridge",
    knowledge_seed_expansion: "Knowledge expansion",
    graph_level_direction: "Graph-level direction"
  };
  return known[raw] || raw.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function directionMeta(direction, nIdeas = null) {
  const parts = [directionTypeLabel(direction)];
  if (nIdeas !== null) parts.push(`${nIdeas} idea${nIdeas === 1 ? "" : "s"}`);
  if (direction.priority !== undefined && direction.priority !== null) parts.push(`priority ${formatNumber(direction.priority)}`);
  const parents = Array.isArray(direction.parent_idea_ids) ? direction.parent_idea_ids.length : 0;
  if (parents) parts.push(`${parents} parent signal${parents === 1 ? "" : "s"}`);
  const facets = direction.target_facets || {};
  const facetBits = [];
  if (facets.parameter_family) facetBits.push(facets.parameter_family);
  if (Array.isArray(facets.markers) && facets.markers.length) facetBits.push(`markers: ${facets.markers.slice(0, 3).join(", ")}`);
  if (Array.isArray(facets.genes) && facets.genes.length) facetBits.push(`genes: ${facets.genes.slice(0, 3).join(", ")}`);
  if (facetBits.length) parts.push(facetBits.join(" | "));
  return parts.filter(Boolean).join(" | ");
}

function directionParentIdeaIds(direction) {
  const ids = [];
  for (const parent of direction.parent_idea_ids || []) {
    ids.push(String(parent).startsWith("idea:") ? String(parent) : `idea:${parent}`);
  }
  for (const edge of edges.filter((e) => e.source === direction.id && e.relation === "direction_based_on")) ids.push(edge.target);
  return [...new Set(ids)].filter((id) => byId.get(id)?.kind === "Idea");
}

function directionEvidenceIds(direction) {
  return [...new Set(edges
    .filter((e) => e.source === direction.id && e.relation === "direction_based_on_evidence")
    .map((e) => e.target))]
    .filter((id) => byId.get(id)?.kind === "EvidenceResult");
}

function directionRound1Summary(direction) {
  const parents = directionParentIdeaIds(direction);
  const evidence = directionEvidenceIds(direction);
  if (parents.length) {
    const parentLabels = parents
      .map((id) => byId.get(id))
      .filter(Boolean)
      .map((node) => label(node))
      .slice(0, 3)
      .join("; ");
    const evidenceBits = evidence
      .map((id) => byId.get(id))
      .filter(Boolean)
      .map((ev) => {
        const parts = [ev.hypothesis_status || "evidence"];
        if (ev.p_value !== undefined && ev.p_value !== null) parts.push(`p=${formatNumber(ev.p_value)}`);
        if (ev.effect_size !== undefined && ev.effect_size !== null) parts.push(`effect=${formatNumber(ev.effect_size)}`);
        return parts.join(", ");
      })
      .slice(0, 2)
      .join("; ");
    return `Based on ${parents.length} Round1 idea/conclusion${parents.length === 1 ? "" : "s"}: ${parentLabels || parents.join(", ")}${evidenceBits ? ` (${evidenceBits})` : ""}.`;
  }
  return `Run-level ${directionTypeLabel(direction).toLowerCase()}: no explicit Round1 parent conclusion was recorded.`;
}

function searchable(n) {
  return JSON.stringify(n).toLowerCase();
}

function technicalRows(n) {
  const rows = [];
  if (n.metadata) rows.push(["Metadata", n.metadata]);
  if (n.signature) rows.push(["Signature", n.signature]);
  const rel = neighborEdges(n.id).slice(0, 30).map((e) => {
    const otherId = e.source === n.id ? e.target : e.source;
    return `${relationLabel(e.relation)} -> ${truncate(label(byId.get(otherId) || { id: otherId }), 48)}`;
  });
  if (rel.length) rows.push(["Graph relationships", rel]);
  return rows;
}

function neighborEdges(id) {
  return edges.filter((e) => e.source === id || e.target === id);
}

function detailRows(n) {
  if (!n) return [];
  const keys = [
    "rationale", "prompt", "biological_hypothesis", "computable_parameter", "expected_direction",
    "hypothesis_status", "direction_status", "p_value", "effect_size", "test_method",
    "direction_id", "direction_type", "priority", "target_facets", "parent_idea_ids",
    "evidence_basis", "novelty_notes", "constraints", "iterative_context_status",
    "source_title", "url", "doi", "pmid", "path"
  ];
  const rows = [];
  if (n.kind === "Direction") rows.push(["Round1 Link", directionRound1Summary(n)]);
  for (const key of keys) {
    const v = n[key];
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v) && !v.length) continue;
    if (typeof v === "object" && !Array.isArray(v) && !Object.keys(v).length) continue;
    rows.push([detailKeyLabel(key), v]);
  }
  return rows;
}

function detailKeyLabel(key) {
  const labels = {
    direction_id: "Direction ID",
    direction_type: "Direction Type",
    parent_idea_ids: "Parent Idea IDs",
    evidence_basis: "Evidence Basis",
    target_facets: "Target Facets",
    novelty_notes: "Novelty Notes",
    iterative_context_status: "Iterative Context Status"
  };
  return labels[key] || String(key).replaceAll("_", " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

function valueLines(value) {
  if (Array.isArray(value)) {
    return value.map((item) => {
      if (item && typeof item === "object") {
        const title = item.title || item.idea_id || item.claim_id || item.direction_id || "item";
        const bits = [];
        if (item.hypothesis_status) bits.push(item.hypothesis_status);
        if (item.p_value !== undefined && item.p_value !== null) bits.push(`p=${formatNumber(item.p_value)}`);
        if (item.effect_size !== undefined && item.effect_size !== null) bits.push(`effect=${formatNumber(item.effect_size)}`);
        return [title, ...bits].join(" | ");
      }
      return String(item);
    });
  }
  if (value && typeof value === "object") {
    return Object.entries(value).map(([k, v]) => `${detailKeyLabel(k)}: ${Array.isArray(v) ? v.join(", ") : String(v)}`);
  }
  return [String(value)];
}

function quickFacts(node, outcome) {
  if (!node) return [];
  const facts = [];
  const add = (labelText, value) => {
    if (value === undefined || value === null || value === "") return;
    const text = Array.isArray(value) ? value.filter(Boolean).join(", ") : String(value);
    if (!text) return;
    facts.push({ label: labelText, value: truncate(text, 84) });
  };
  if (node.kind === "Idea") {
    const run = runForIdea(node.id);
    add("Round", run ? (runOrder(run) > 1 ? `Round ${runOrder(run)}` : "Round 1") : "Unknown");
    add("Family", node.signature?.parameter_family);
    add("Markers", node.signature?.markers?.slice(0, 4));
    add("Genes", node.signature?.genes?.slice(0, 4));
    add("Cell types", node.signature?.cell_types?.slice(0, 4) || node.cell_types?.slice?.(0, 4));
  } else if (node.kind === "EvidenceResult" || node.kind === "Conclusion") {
    add("Status", node.hypothesis_status);
    add("Direction", node.direction_status);
    add("Test", node.test_method);
  } else if (node.kind === "Direction") {
    add("Type", directionTypeLabel(node));
    add("Priority", node.priority !== undefined && node.priority !== null ? formatNumber(node.priority) : "");
    add("Parents", directionParentIdeaIds(node).length ? `${directionParentIdeaIds(node).length} prior signal(s)` : "");
    add("Target", directionMeta(node).split(" | ").slice(-2).join(" | "));
  } else if (node.kind === "LiteratureClaim") {
    add("Source", node.source_title || node.url || node.doi || node.pmid);
    add("Related ideas", claimIdeaIds(node.id).length);
    add("Markers", node.markers?.slice?.(0, 4));
    add("Genes", node.genes?.slice?.(0, 4));
  } else if (node.kind === "CData") {
    add("Graph nodes", rawGraph.summary?.n_nodes ?? rawGraph.nodes.length);
    add("Graph edges", rawGraph.summary?.n_edges ?? rawGraph.edges.length);
  }
  if (outcome && node.kind === "Idea") {
    add("Evidence", evidenceSummary(outcome));
  }
  return facts.slice(0, 6);
}

function statusClass(status) {
  const s = String(status || "").toLowerCase();
  if (s === "supported") return "supported";
  if (s === "borderline") return "borderline";
  if (s === "inconclusive") return "inconclusive";
  if (s === "contradicted") return "contradicted";
  if (s === "not supported") return "not-supported";
  if (s === "failed") return "failed";
  if (s === "rejected") return "rejected";
  return "pending";
}

function evidenceSummary(ev) {
  if (!ev) return "No notebook-agent evidence recorded.";
  const parts = [ev.hypothesis_status || "Evidence"];
  if (ev.p_value !== undefined && ev.p_value !== null) parts.push(`p=${formatNumber(ev.p_value)}`);
  if (ev.effect_size !== undefined && ev.effect_size !== null) parts.push(`effect=${formatNumber(ev.effect_size)}`);
  if (ev.test_method) parts.push(truncate(ev.test_method, 78));
  return parts.join(" | ");
}

function ideaForEvidence(evidenceId) {
  const edge = edges.find((e) => e.source === evidenceId && outcomeRelations.has(e.relation));
  return edge ? byId.get(edge.target) : null;
}

function notebookForEvidence(evidenceId) {
  const produced = edges.find((e) => e.target === evidenceId && e.relation === "produced");
  return produced ? byId.get(produced.source) : null;
}

function makeVirtualNode(id, kind, fields = {}) {
  if (!byId.has(id)) byId.set(id, { id, kind, ...fields });
  return byId.get(id);
}

function addFollowUp(map, parentId, idea) {
  if (!map.has(parentId)) map.set(parentId, { direct: [], directions: new Map() });
  const bucket = map.get(parentId);
  const direction = directionForIdea(idea);
  if (direction) {
    if (!bucket.directions.has(direction.id)) bucket.directions.set(direction.id, { direction, ideas: [] });
    bucket.directions.get(direction.id).ideas.push(idea);
  } else {
    bucket.direct.push(idea);
  }
}

function buildDiscoveryModel(visibleIdeaIds, query) {
  const runs = sortedRuns();
  const firstRun = runs[0] || null;
  const laterRuns = runs.slice(1);
  const firstIds = new Set(firstRun ? runIdeaIds(firstRun.id) : []);
  const laterIds = new Set(laterRuns.flatMap((run) => runIdeaIds(run.id)));
  const firstIdeas = [...firstIds].map((id) => byId.get(id)).filter(Boolean);
  const laterIdeas = [...laterIds].map((id) => byId.get(id)).filter(Boolean);

  const visibleLater = laterIdeas.filter((idea) => visibleIdeaIds.has(idea.id));
  const followUpsByParent = new Map();
  for (const idea of visibleLater) {
    for (const parentId of parentIdeaIds(idea)) addFollowUp(followUpsByParent, parentId, idea);
  }

  function ideaVisible(idea) {
    return visibleIdeaIds.has(idea.id) || Boolean(followUpsByParent.get(idea.id));
  }

  const visibleFirstIdeas = firstIdeas.filter(ideaVisible);
  const claimRootIdeasByClaim = new Map();
  for (const idea of visibleFirstIdeas) {
    const claimId = canonicalClaimIdForIdea(idea);
    if (!claimId) continue;
    if (!claimRootIdeasByClaim.has(claimId)) claimRootIdeasByClaim.set(claimId, []);
    claimRootIdeasByClaim.get(claimId).push(idea);
  }

  const firstBranches = visibleFirstIdeas
    .filter((idea) => !canonicalClaimIdForIdea(idea))
    .sort((a, b) => statusOrder.indexOf(statusForIdea(a.id)) - statusOrder.indexOf(statusForIdea(b.id)) || label(a).localeCompare(label(b)))
    .map((idea) => ideaBranch(idea, followUpsByParent));

  const parentedLater = new Set(visibleLater.filter((idea) => parentIdeaIds(idea).length).map((idea) => idea.id));
  const orphanLater = visibleLater.filter((idea) => !parentedLater.has(idea.id));
  const directionIdeas = orphanLater.filter((idea) => !contextUnavailable(idea));
  const gapIdeas = orphanLater.filter((idea) => contextUnavailable(idea));

  const claimNodes = nodes
    .filter((n) => n.kind === "LiteratureClaim")
    .filter((claim) => (
      !query
      || searchable(claim).includes(query)
      || visibleClaimIdeaIds(claim.id, visibleIdeaIds).length
      || claimRootIdeasByClaim.has(claim.id)
    ))
    .sort((a, b) => label(a).localeCompare(label(b)));
  const claimBranches = claimNodes.map((claim) => {
    const relatedIds = new Set([
      ...(claimRootIdeasByClaim.get(claim.id) || []).map((idea) => idea.id),
      ...visibleClaimIdeaIds(claim.id, visibleIdeaIds),
    ]);
    const related = [...relatedIds]
      .map((id) => byId.get(id))
      .filter(Boolean)
      .sort((a, b) => label(a).localeCompare(label(b)));
    return {
      node: claim,
      caption: "claim",
      meta: `${related.length} root idea${related.length === 1 ? "" : "s"}`,
      children: related.map((idea) => ideaBranch(idea, followUpsByParent))
    };
  });

  const directionBranches = mergeUniqueBranches([
    ...groupedDirectionBranches(directionIdeas, followUpsByParent),
    ...visibleDirectionBranches(visibleIdeaIds, followUpsByParent, false),
  ]);
  const gapBranches = gapIdeas
    .sort((a, b) => label(a).localeCompare(label(b)))
    .map((idea) => ideaBranch(idea, followUpsByParent));

  return {
    root: {
      node: cdataNode,
      caption: "cdata",
      meta: `${visibleFirstIdeas.length} Round1 ideas | ${visibleLater.length} Round2 ideas`,
      children: [...claimBranches, ...firstBranches, ...directionBranches, ...gapBranches]
    },
    counts: {
      firstBranches: visibleFirstIdeas.length,
      secondIdeas: visibleLater.length,
      directions: directionBranches.length,
      claims: claimBranches.length
    }
  };
}

function buildSummaryDiscoveryModel(visibleIdeaIds, query) {
  const runs = sortedRuns();
  const firstRun = runs[0] || null;
  const laterRuns = runs.slice(1);
  const firstIds = new Set(firstRun ? runIdeaIds(firstRun.id) : []);
  const laterIds = new Set(laterRuns.flatMap((run) => runIdeaIds(run.id)));
  const firstIdeas = [...firstIds].map((id) => byId.get(id)).filter(Boolean);
  const laterIdeas = [...laterIds].map((id) => byId.get(id)).filter(Boolean);

  const visibleLater = laterIdeas.filter((idea) => visibleIdeaIds.has(idea.id));
  const followUpsByParent = new Map();
  for (const idea of visibleLater) {
    for (const parentId of parentIdeaIds(idea)) addFollowUp(followUpsByParent, parentId, idea);
  }

  const parentedLater = new Set(visibleLater.filter((idea) => parentIdeaIds(idea).length).map((idea) => idea.id));
  const orphanLater = visibleLater.filter((idea) => !parentedLater.has(idea.id));
  const directionIdeas = orphanLater.filter((idea) => !contextUnavailable(idea));
  const gapIdeas = orphanLater.filter((idea) => contextUnavailable(idea));

  const claimBranches = nodes
    .filter((n) => n.kind === "LiteratureClaim")
    .filter((claim) => !query || searchable(claim).includes(query) || visibleClaimIdeaIds(claim.id, visibleIdeaIds).length)
    .sort((a, b) => label(a).localeCompare(label(b)))
    .map((claim) => ({
      node: claim,
      caption: "claim",
      meta: `${visibleClaimIdeaIds(claim.id, visibleIdeaIds).length} linked ideas`,
      children: []
    }));

  const firstBranches = firstIdeas
    .filter((idea) => visibleIdeaIds.has(idea.id) || Boolean(followUpsByParent.get(idea.id)))
    .sort((a, b) => statusOrder.indexOf(statusForIdea(a.id)) - statusOrder.indexOf(statusForIdea(b.id)) || label(a).localeCompare(label(b)))
    .map((idea) => summaryIdeaBranch(idea, followUpsByParent));

  const directionBranches = mergeUniqueBranches([
    ...groupedSummaryDirectionBranches(directionIdeas, followUpsByParent),
    ...visibleDirectionBranches(visibleIdeaIds, followUpsByParent, true),
  ]);
  const gapBranches = gapIdeas
    .sort((a, b) => label(a).localeCompare(label(b)))
    .map((idea) => summaryIdeaBranch(idea, followUpsByParent));

  return {
    root: {
      node: cdataNode,
      caption: "cdata",
      meta: `${firstBranches.length} Round1 ideas | ${visibleLater.length} Round2 ideas`,
      children: [...claimBranches, ...firstBranches, ...directionBranches, ...gapBranches]
    }
  };
}

function summaryIdeaBranch(idea, followUpsByParent, seen = new Set()) {
  if (seen.has(idea.id)) {
    return {
      node: makeVirtualNode(`virtual:cycle:${idea.id}`, "Conclusion", {
        title: `Cycle back to ${label(idea)}`,
        hypothesis_status: "Untested",
        summary: "This idea already appears above in the graph."
      }),
      caption: "repeat",
      meta: "cycle suppressed",
      children: []
    };
  }
  const nextSeen = new Set(seen);
  nextSeen.add(idea.id);
  const run = runForIdea(idea.id);
  return {
    node: idea,
    caption: run ? (runOrder(run) > 1 ? `Round ${runOrder(run)} idea` : "Round 1 idea") : "idea",
    meta: evidenceSummary(evidenceForIdea(idea.id)),
    children: [summaryConclusionBranch(idea, followUpsByParent.get(idea.id), followUpsByParent, nextSeen)]
  };
}

function summaryConclusionBranch(idea, followUps, followUpsByParent, seen) {
  const ev = evidenceForIdea(idea.id);
  const node = ev || makeVirtualNode(`virtual:summary-conclusion:${idea.id}`, "Conclusion", {
    title: `Untested conclusion for ${label(idea)}`,
    hypothesis_status: "Untested",
    summary: "This idea has no notebook-agent evidence result recorded yet."
  });
  return {
    node,
    caption: "conclusion",
    meta: evidenceSummary(node),
    children: summaryFollowUpBranches(followUps, followUpsByParent, seen)
  };
}

function summaryFollowUpBranches(followUps, followUpsByParent, seen) {
  if (!followUps) return [];
  const directionBranches = [...followUps.directions.values()]
    .sort((a, b) => label(a.direction).localeCompare(label(b.direction)))
    .map((group) => summaryDirectionBranch(group.direction, group.ideas, followUpsByParent, seen));
  const directBranches = [...followUps.direct]
    .sort((a, b) => label(a).localeCompare(label(b)))
    .map((idea) => summaryIdeaBranch(idea, followUpsByParent, seen));
  return [...directionBranches, ...directBranches];
}

function summaryDirectionBranch(direction, ideas, followUpsByParent, seen) {
  const sorted = [...ideas].sort((a, b) => label(a).localeCompare(label(b)));
  return {
    node: direction,
    caption: "direction",
    meta: directionMeta(direction, sorted.length),
    children: sorted.map((idea) => summaryIdeaBranch(idea, followUpsByParent, seen))
  };
}

function groupedSummaryDirectionBranches(ideas, followUpsByParent) {
  const groups = new Map();
  const direct = [];
  for (const idea of ideas) {
    const direction = directionForIdea(idea);
    if (!direction) {
      direct.push(idea);
      continue;
    }
    if (!groups.has(direction.id)) groups.set(direction.id, { direction, ideas: [] });
    groups.get(direction.id).ideas.push(idea);
  }
  const directionBranches = [...groups.values()]
    .sort((a, b) => label(a.direction).localeCompare(label(b.direction)))
    .map((group) => summaryDirectionBranch(group.direction, group.ideas, followUpsByParent, new Set()));
  const directBranches = direct
    .sort((a, b) => label(a).localeCompare(label(b)))
    .map((idea) => summaryIdeaBranch(idea, followUpsByParent, new Set()));
  return [...directionBranches, ...directBranches];
}

function visibleDirectionBranches(visibleIdeaIds, followUpsByParent, summary = false) {
  const groups = new Map();
  for (const edge of edges) {
    if (edge.relation !== "direction_proposed" || !visibleIdeaIds.has(edge.target)) continue;
    const direction = byId.get(edge.source);
    const idea = byId.get(edge.target);
    if (!direction || direction.kind !== "Direction" || !idea || contextUnavailable(idea)) continue;
    if (!groups.has(direction.id)) groups.set(direction.id, { direction, ideas: [] });
    groups.get(direction.id).ideas.push(idea);
  }
  return [...groups.values()]
    .sort((a, b) => label(a.direction).localeCompare(label(b.direction)))
    .map((group) => summary
      ? summaryDirectionBranch(group.direction, group.ideas, followUpsByParent, new Set())
      : directionBranch(group.direction, group.ideas, followUpsByParent, new Set()));
}

function mergeUniqueBranches(branches) {
  const seen = new Set();
  const out = [];
  for (const branch of branches) {
    const id = branch?.node?.id;
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push(branch);
  }
  return out;
}

function ideaBranch(idea, followUpsByParent, seen = new Set()) {
  if (seen.has(idea.id)) {
    return {
      node: makeVirtualNode(`virtual:cycle:${idea.id}`, "Conclusion", {
        title: `Cycle back to ${label(idea)}`,
        hypothesis_status: "Untested",
        summary: "This idea already appears above in the tree."
      }),
      caption: "repeat",
      meta: "cycle suppressed",
      children: []
    };
  }
  const nextSeen = new Set(seen);
  nextSeen.add(idea.id);
  const run = runForIdea(idea.id);
  return {
    node: idea,
    caption: `Round ${run ? runOrder(run) : 1} idea`,
    meta: [statusForIdea(idea.id), idea.signature?.parameter_family || "", directionLabel(idea)].filter(Boolean).join(" | "),
    children: [conclusionBranch(idea, followUpsByParent.get(idea.id), followUpsByParent, nextSeen)]
  };
}

function conclusionBranch(idea, followUps, followUpsByParent, seen) {
  const ev = evidenceForIdea(idea.id);
  const node = ev || makeVirtualNode(`virtual:conclusion:${idea.id}`, "Conclusion", {
    title: `Conclusion for ${label(idea)}`,
    hypothesis_status: "Untested",
    summary: "No notebook-agent evidence result was recorded for this idea."
  });
  return {
    node,
    caption: "conclusion",
    meta: evidenceSummary(node),
    children: followUpBranches(followUps, followUpsByParent, seen)
  };
}

function followUpBranches(followUps, followUpsByParent, seen) {
  if (!followUps) return [];
  const directionBranches = [...followUps.directions.values()]
    .sort((a, b) => label(a.direction).localeCompare(label(b.direction)))
    .map((group) => directionBranch(group.direction, group.ideas, followUpsByParent, seen));
  const directBranches = [...followUps.direct]
    .sort((a, b) => label(a).localeCompare(label(b)))
    .map((idea) => ideaBranch(idea, followUpsByParent, seen));
  return [...directionBranches, ...directBranches];
}

function directionBranch(direction, ideas, followUpsByParent, seen) {
  const sorted = [...ideas].sort((a, b) => label(a).localeCompare(label(b)));
  return {
    node: direction,
    caption: "direction",
    meta: directionMeta(direction, sorted.length),
    children: sorted.map((idea) => ideaBranch(idea, followUpsByParent, seen))
  };
}

function groupedDirectionBranches(ideas, followUpsByParent) {
  const groups = new Map();
  const direct = [];
  for (const idea of ideas) {
    const direction = directionForIdea(idea);
    if (!direction) {
      direct.push(idea);
      continue;
    }
    if (!groups.has(direction.id)) groups.set(direction.id, { direction, ideas: [] });
    groups.get(direction.id).ideas.push(idea);
  }
  const directionBranches = [...groups.values()]
    .sort((a, b) => label(a.direction).localeCompare(label(b.direction)))
    .map((group) => directionBranch(group.direction, group.ideas, followUpsByParent, new Set()));
  const directBranches = direct
    .sort((a, b) => label(a).localeCompare(label(b)))
    .map((idea) => ideaBranch(idea, followUpsByParent, new Set()));
  return [...directionBranches, ...directBranches];
}

function groupEntry(id, title, caption, meta, children, summary = "") {
  return {
    node: makeVirtualNode(id, "Group", { title, summary }),
    caption,
    meta,
    children
  };
}

function groupedRound1Branches(branches) {
  const groups = [];
  for (const status of statusOrder) {
    const children = branches.filter((branch) => statusForIdea(branch.node.id) === status);
    if (!children.length) continue;
    groups.push(groupEntry(
      `virtual:group:round1:${slugForId(status)}`,
      `${status} Round1 ideas`,
      "round 1",
      `${children.length} idea${children.length === 1 ? "" : "s"}`,
      children,
      `First-round ideas whose notebook-agent evidence status is ${status}.`
    ));
  }
  return groups;
}

function findEntryPath(entry, id, path = []) {
  if (!entry?.node) return null;
  const next = [...path, entry.node.id];
  if (entry.node.id === id) return next;
  for (const child of entry.children || []) {
    const found = findEntryPath(child, id, next);
    if (found) return found;
  }
  return null;
}

function entryHasNode(entry, id) {
  return Boolean(findEntryPath(entry, id));
}

function pruneEntry(entry, expandedIds, selectedPathIds, autoExpandAll, depth = 0) {
  const allChildren = (entry.children || []).filter((child) => child?.node);
  const shouldExpand = autoExpandAll || depth === 0 || expandedIds.has(entry.node.id) || selectedPathIds.has(entry.node.id);
  const children = shouldExpand
    ? allChildren.map((child) => pruneEntry(child, expandedIds, selectedPathIds, autoExpandAll, depth + 1))
    : [];
  return {
    ...entry,
    children,
    childCount: allChildren.length,
    hiddenChildCount: Math.max(0, allChildren.length - children.length),
    isCollapsed: allChildren.length > 0 && !shouldExpand
  };
}

function spotlightEntry(entry, selectedPathIds, selectedId) {
  if (!entry?.node) return entry;
  const children = (entry.children || []).filter((child) => child?.node);
  const isSelected = entry.node.id === selectedId;
  const isOnPath = selectedPathIds.has(entry.node.id);
  let nextChildren = [];

  if (isSelected) {
    nextChildren = children.map((child) => spotlightDescendants(child, 2));
  } else if (isOnPath) {
    nextChildren = children
      .filter((child) => selectedPathIds.has(child.node.id))
      .map((child) => spotlightEntry(child, selectedPathIds, selectedId));
  }

  const hiddenHere = Math.max(0, children.length - nextChildren.length);
  return {
    ...entry,
    children: nextChildren,
    hiddenChildCount: (entry.hiddenChildCount || 0) + hiddenHere,
    isCollapsed: hiddenHere > 0 && !nextChildren.length
  };
}

function spotlightDescendants(entry, depthRemaining) {
  const children = (entry.children || []).filter((child) => child?.node);
  if (depthRemaining <= 0) {
    return {
      ...entry,
      children: [],
      hiddenChildCount: (entry.hiddenChildCount || 0) + children.length,
      isCollapsed: children.length > 0
    };
  }
  return {
    ...entry,
    children: children.map((child) => spotlightDescendants(child, depthRemaining - 1))
  };
}

function layoutTree(rootEntry, direction = "vertical") {
  if (direction === "round") return layoutRoundLanes(rootEntry);
  return layoutClassicTree(rootEntry, direction);
}

function layoutRoundLanes(rootEntry) {
  const items = [];
  const links = [];
  const itemByNodeId = new Map();
  const linkKeys = new Set();
  const ideaOrder = new Map();
  let uid = 0;

  for (const run of sortedRuns()) {
    const round = runOrder(run);
    runIdeaIds(run.id).forEach((id, index) => {
      ideaOrder.set(id, { round, index });
    });
  }

  function children(entry) {
    return (entry.children || []).filter((child) => child?.node);
  }

  function pushLink(source, target, role, duplicate = false) {
    const key = `${source.uid}->${target.uid}:${role}`;
    if (linkKeys.has(key)) return;
    linkKeys.add(key);
    links.push({ source, target, role, duplicate });
  }

  function walk(entry, depth, parent = null) {
    const existing = itemByNodeId.get(entry.node.id);
    if (existing) {
      if (parent) pushLink(parent, existing, edgeRole(parent, existing), true);
      return {
        uid: `ref-${uid++}`,
        entry,
        node: entry.node,
        depth,
        parent,
        children: [],
        x: 0,
        y: 0,
        isReference: true
      };
    }
    const item = {
      uid: `node-${uid++}`,
      entry,
      node: entry.node,
      depth,
      parent,
      children: [],
      x: 0,
      y: 0
    };
    itemByNodeId.set(entry.node.id, item);
    items.push(item);
    if (parent) pushLink(parent, item, edgeRole(parent, item));
    item.children = children(entry)
      .map((child) => walk(child, depth + 1, item))
      .filter((child) => !child.isReference);
    return item;
  }

  const root = walk(rootEntry, 0, null);

  function ideaRound(idea) {
    return ideaOrder.get(idea?.id)?.round || (runForIdea(idea?.id) ? runOrder(runForIdea(idea.id)) : 1);
  }

  function ideaIndex(idea) {
    return ideaOrder.get(idea?.id)?.index ?? 0;
  }

  function parentIdea(item) {
    let cursor = item?.parent;
    while (cursor) {
      if (cursor.node.kind === "Idea") return cursor.node;
      cursor = cursor.parent;
    }
    return null;
  }

  function childIdeas(item) {
    const found = [];
    const stack = [...(item?.children || [])];
    while (stack.length) {
      const child = stack.shift();
      if (child.node.kind === "Idea") found.push(child.node);
      stack.push(...(child.children || []));
    }
    return found;
  }

  function evidenceIdea(item) {
    if (item.node.kind === "EvidenceResult") return ideaForEvidence(item.node.id);
    if (item.node.kind === "Conclusion") return parentIdea(item);
    return null;
  }

  function mean(values, fallback = 0) {
    const nums = values.map(Number).filter(Number.isFinite);
    if (!nums.length) return fallback;
    return nums.reduce((a, b) => a + b, 0) / nums.length;
  }

  function itemRound(item) {
    if (item.node.kind === "Idea") return ideaRound(item.node);
    if (item.node.kind === "EvidenceResult" || item.node.kind === "Conclusion") {
      return ideaRound(evidenceIdea(item));
    }
    if (item.node.kind === "Direction" || item.node.kind === "HandoffGap") {
      const childRounds = childIdeas(item).map(ideaRound);
      if (childRounds.length) return Math.min(...childRounds);
      const parent = parentIdea(item);
      return parent ? ideaRound(parent) + 1 : 2;
    }
    if (item.node.kind === "LiteratureClaim") {
      const searchRound = claimSearchRound(item.node);
      if (searchRound) return searchRound;
      const childRounds = childIdeas(item).map(ideaRound);
      return childRounds.length ? Math.min(...childRounds) : 1;
    }
    return 1;
  }

  function itemStage(item) {
    if (item.node.kind === "CData") return 0;
    const round = Math.max(1, itemRound(item));
    const base = (round - 1) * 3;
    if (item.node.kind === "LiteratureClaim") return base + 1;
    if (item.node.kind === "Direction" || item.node.kind === "HandoffGap") return base + 1;
    if (item.node.kind === "Idea") return base + 2;
    if (item.node.kind === "EvidenceResult" || item.node.kind === "Conclusion") return base + 3;
    if (item.node.kind === "Group") return Math.max(1, item.depth);
    return base + 2;
  }

  function itemOrder(item) {
    if (item.node.kind === "Idea") return ideaIndex(item.node);
    if (item.node.kind === "EvidenceResult" || item.node.kind === "Conclusion") {
      return ideaIndex(evidenceIdea(item));
    }
    if (item.node.kind === "LiteratureClaim" || item.node.kind === "Direction" || item.node.kind === "HandoffGap") {
      const kids = childIdeas(item);
      if (kids.length) return mean(kids.map(ideaIndex), 0);
      const parent = parentIdea(item);
      return parent ? ideaIndex(parent) : 0;
    }
    if (item.node.kind === "CData") return 0;
    return mean((item.children || []).map(itemOrder), item.depth);
  }

  for (const item of items) {
    item.depth = itemStage(item);
    item._roundOrder = itemOrder(item);
  }

  const byLane = new Map();
  for (const item of items) {
    if (!byLane.has(item.depth)) byLane.set(item.depth, []);
    byLane.get(item.depth).push(item);
  }

  const laneYByDepth = new Map();
  const sortedDepths = [...byLane.keys()].sort((a, b) => a - b);
  let nextLaneY = GRAPH_PADDING;
  for (const [index, depth] of sortedDepths.entries()) {
    if (index === 0) {
      laneYByDepth.set(depth, GRAPH_PADDING);
      nextLaneY = GRAPH_PADDING + ROUND_ROOT_LANE_GAP;
    } else {
      laneYByDepth.set(depth, nextLaneY);
      nextLaneY += ROUND_LANE_GAP;
    }
  }

  let maxX = GRAPH_PADDING;
  for (const laneItems of byLane.values()) {
    laneItems.sort((a, b) => a._roundOrder - b._roundOrder || label(a.node).localeCompare(label(b.node)));
    let previousX = -Infinity;
    for (const item of laneItems) {
      const idealX = GRAPH_PADDING + item._roundOrder * ROUND_NODE_GAP;
      item.x = Math.max(idealX, previousX + ROUND_NODE_GAP * 0.56);
      item.y = laneYByDepth.get(item.depth) ?? GRAPH_PADDING;
      previousX = item.x;
      maxX = Math.max(maxX, item.x + nodeWidth(item) / 2);
    }
  }

  const maxY = Math.max(...items.map((item) => item.y), GRAPH_PADDING);
  const width = Math.max(1100, maxX + GRAPH_PADDING);
  const height = Math.max(720, maxY + GRAPH_PADDING);
  root.x = width / 2;
  root.y = GRAPH_PADDING;

  return {
    nodes: items,
    links,
    root,
    width,
    height,
    direction: "round",
    byNodeId: itemByNodeId
  };
}

function layoutWrappedLineageTree(rootEntry) {
  const items = [];
  const links = [];
  let uid = 0;
  let maxDepth = 0;
  const branchCount = (rootEntry?.children || []).filter((child) => child?.node).length;
  const columns = branchCount > 24 ? 6 : branchCount > 14 ? 5 : 4;
  const columnWidth = 292;
  const width = GRAPH_PADDING * 2 + columns * columnWidth;
  const rootY = GRAPH_PADDING;
  const firstBranchY = rootY + 150;
  const stackGap = 104;
  const siblingGap = 30;
  const root = {
    uid: `node-${uid++}`,
    entry: rootEntry,
    node: rootEntry.node,
    depth: 0,
    parent: null,
    children: [],
    x: width / 2,
    y: rootY
  };
  items.push(root);

  function children(entry) {
    return (entry.children || []).filter((child) => child?.node);
  }

  function makeItem(entry, depth, parent, x, y) {
    maxDepth = Math.max(maxDepth, depth);
    const item = {
      uid: `node-${uid++}`,
      entry,
      node: entry.node,
      depth,
      parent,
      children: [],
      x,
      y
    };
    items.push(item);
    if (parent) {
      parent.children.push(item);
      links.push({ source: parent, target: item, role: edgeRole(parent, item) });
    }
    return item;
  }

  function walkStack(entry, depth, parent, x, y) {
    const item = makeItem(entry, depth, parent, x, y);
    const kids = children(entry);
    if (!kids.length) return y + nodeHeight(item) / 2;

    let cursorY = y + stackGap;
    let bottom = cursorY;
    for (const kid of kids) {
      const childBottom = walkStack(kid, depth + 1, item, x, cursorY);
      bottom = Math.max(bottom, childBottom);
      cursorY = childBottom + siblingGap + nodeHeight(item) / 2;
    }
    return bottom;
  }

  const colBottoms = Array(columns).fill(firstBranchY);
  const branches = children(rootEntry);
  for (const branch of branches) {
    const col = colBottoms.indexOf(Math.min(...colBottoms));
    const x = GRAPH_PADDING + columnWidth * col + columnWidth / 2;
    const y = colBottoms[col];
    const bottom = walkStack(branch, 1, root, x, y);
    colBottoms[col] = bottom + 86;
  }

  const height = Math.max(720, Math.max(...colBottoms) + GRAPH_PADDING / 2);
  return {
    nodes: items,
    links,
    root,
    width,
    height,
    maxDepth,
    byNodeId: new Map(items.map((item) => [item.node.id, item]))
  };
}

function layoutClassicTree(rootEntry, direction = "vertical") {
  const horizontal = direction === "horizontal";
  const items = [];
  const links = [];
  const itemByNodeId = new Map();
  const linkKeys = new Set();
  let uid = 0;
  let maxDepth = 0;

  function children(entry) {
    return (entry.children || []).filter((child) => child?.node);
  }

  function pushLink(source, target, role, duplicate = false) {
    const key = `${source.uid}->${target.uid}:${role}`;
    if (linkKeys.has(key)) return;
    linkKeys.add(key);
    links.push({ source, target, role, duplicate });
  }

  function entryWeight(entry) {
    const kids = children(entry);
    if (!kids.length) return 1;
    const childWeight = kids.reduce((sum, child) => sum + entryWeight(child), 0);
    if (entry.node.kind === "CData") return Math.max(1, childWeight);
    if (entry.node.kind === "LiteratureClaim" || entry.node.kind === "Direction" || entry.node.kind === "HandoffGap") {
      return Math.max(1.1, childWeight * 0.92);
    }
    return Math.max(1, childWeight);
  }

  function walk(entry, depth, start, width, parent = null) {
    maxDepth = Math.max(maxDepth, depth);
    const existing = itemByNodeId.get(entry.node.id);
    if (existing) {
      if (parent) pushLink(parent, existing, edgeRole(parent, existing), true);
      return {
        uid: `ref-${uid++}`,
        entry,
        node: entry.node,
        depth,
        parent,
        children: [],
        x: horizontal ? 0 : start + width / 2,
        y: horizontal ? start + width / 2 : 0,
        isReference: true
      };
    }
    const item = {
      uid: `node-${uid++}`,
      entry,
      node: entry.node,
      depth,
      parent,
      children: [],
      x: 0,
      y: 0
    };
    itemByNodeId.set(entry.node.id, item);
    items.push(item);
    if (parent) pushLink(parent, item, edgeRole(parent, item));
    const kids = children(entry);
    if (horizontal) item.y = start + width / 2;
    else item.x = start + width / 2;
    if (kids.length) {
      const weights = kids.map(entryWeight);
      const total = weights.reduce((a, b) => a + b, 0) || 1;
      let cursor = start;
      const childRefs = kids.map((kid, i) => {
        const childWidth = width * (weights[i] / total);
        const child = walk(kid, depth + 1, cursor, childWidth, item);
        cursor += childWidth;
        return child;
      });
      item.children = childRefs.filter((child) => !child.isReference);
      if (horizontal) item.y = (childRefs[0].y + childRefs[childRefs.length - 1].y) / 2;
      else item.x = (childRefs[0].x + childRefs[childRefs.length - 1].x) / 2;
    }
    return item;
  }

  const totalWeight = Math.max(1, entryWeight(rootEntry));
  const breadthGap = horizontal ? HORIZONTAL_NODE_GAP : NODE_GAP;
  const levelGap = horizontal ? HORIZONTAL_LEVEL_GAP : LEVEL_GAP;
  const breadth = Math.max(horizontal ? 720 : 1100, Math.ceil(totalWeight * breadthGap + GRAPH_PADDING * 2));
  const root = walk(rootEntry, 0, GRAPH_PADDING, breadth - GRAPH_PADDING * 2, null);
  const depthSpan = Math.max(horizontal ? 1100 : 720, GRAPH_PADDING + maxDepth * levelGap + GRAPH_PADDING);
  const dx = horizontal ? 0 : breadth / 2 - root.x;
  const dy = horizontal ? breadth / 2 - root.y : 0;
  for (const item of items) {
    if (horizontal) {
      item.x = GRAPH_PADDING + item.depth * levelGap;
      item.y += dy;
    } else {
      item.x += dx;
      item.y = GRAPH_PADDING + item.depth * levelGap;
    }
  }
  return {
    nodes: items,
    links,
    root,
    width: horizontal ? depthSpan : breadth,
    height: horizontal ? breadth : depthSpan,
    direction,
    byNodeId: itemByNodeId
  };
}

function edgeRole(parent, child) {
  const pk = parent.node?.kind;
  const ck = child.node?.kind;
  if ((pk === "EvidenceResult" || pk === "Conclusion") && ck === "Direction") return "direction";
  if (pk === "Direction" && ck === "Idea") return "direction";
  if (pk === "CData" && ck === "Direction") return "run-direction";
  return "";
}

function edgeLabel(link) {
  const pk = link.source.node?.kind;
  const ck = link.target.node?.kind;
  if (pk === "CData" && ck === "Group") return "organize";
  if (pk === "CData" && ck === "Idea") return "hypothesis";
  if (pk === "CData" && ck === "LiteratureClaim") return "claim";
  if (pk === "CData" && ck === "Direction") return "run direction";
  if (pk === "CData" && ck === "HandoffGap") return "handoff";
  if (pk === "Group" && ck === "Group") return "group";
  if (pk === "Group" && ck === "HandoffGap") return "handoff";
  if (pk === "Group" && ck === "LiteratureClaim") return "claim";
  if (pk === "Group" && ck === "Direction") return "direction";
  if (pk === "Group" && ck === "Idea") return "idea";
  if (pk === "HandoffGap" && ck === "Idea") return "idea";
  if (pk === "LiteratureClaim" && ck === "Idea") return "motivates";
  if (pk === "Idea" && (ck === "EvidenceResult" || ck === "Conclusion")) return "tested";
  if ((pk === "EvidenceResult" || pk === "Conclusion") && ck === "Direction") return "follow-up";
  if ((pk === "EvidenceResult" || pk === "Conclusion") && ck === "Idea") return "next idea";
  if (pk === "Direction" && ck === "Idea") return "generates";
  return link.role || "links";
}

function edgeLabelWidth(link) {
  return Math.max(54, Math.min(112, edgeLabel(link).length * 6.4 + 24));
}

function edgeLabelTransform(link, direction = "vertical") {
  if (direction === "horizontal") {
    const x1 = link.source.x + nodeWidth(link.source) / 2 + 8;
    const x2 = link.target.x - nodeWidth(link.target) / 2 - 8;
    const x = x1 + (x2 - x1) * 0.56;
    const y = (link.source.y + link.target.y) / 2;
    return `translate(${x}, ${y})`;
  }
  const x = (link.source.x + link.target.x) / 2;
  const y1 = link.source.y + nodeHeight(link.source) / 2 + 8;
  const y2 = link.target.y - nodeHeight(link.target) / 2 - 8;
  const y = y1 + (y2 - y1) * 0.56;
  return `translate(${x}, ${y})`;
}

function laneLabel(depth, items) {
  const kinds = new Set(items.map((item) => item.node.kind));
  const hasIdea = kinds.has("Idea");
  const hasEvidence = kinds.has("EvidenceResult") || kinds.has("Conclusion");
  const hasClaim = kinds.has("LiteratureClaim");
  const hasDirection = kinds.has("Direction");
  if (kinds.has("CData")) return "Dataset";
  if (depth > 0) {
    const round = Math.floor((depth - 1) / 3) + 1;
    const phase = ((depth - 1) % 3) + 1;
    if (phase === 1 && hasClaim && hasDirection) return `Round ${round} literature + directions`;
    if (phase === 1 && hasClaim) return `Round ${round} claims`;
    if (phase === 1 && hasDirection) return `Round ${round} directions`;
    if (phase === 2 && hasIdea) return `Round ${round} hypotheses`;
    if (phase === 3 && hasEvidence) return `Round ${round} notebook evidence`;
  }
  if (hasClaim && (hasIdea || hasDirection)) return "Claims + hypotheses";
  if (hasDirection && hasIdea) return "Directions + hypotheses";
  if (hasIdea && hasEvidence) return "Hypotheses + evidence";
  if (hasClaim) return "Literature context";
  if (hasDirection) return "Follow-up direction";
  if (hasEvidence) return "Notebook evidence";
  if (hasIdea) {
    const hasLater = items.some((item) => {
      const run = runForIdea(item.node.id);
      return run && runOrder(run) > 1;
    });
    return hasLater ? "Generated hypotheses" : "Round 1 hypotheses";
  }
  if (kinds.has("Group") || kinds.has("HandoffGap")) return depth <= 1 ? "Context groups" : "Context branch";
  return "Graph layer";
}

function laneMeta(items) {
  const ideas = items.filter((item) => item.node.kind === "Idea").length;
  const evidence = items.filter((item) => item.node.kind === "EvidenceResult" || item.node.kind === "Conclusion").length;
  const claims = items.filter((item) => item.node.kind === "LiteratureClaim").length;
  const directions = items.filter((item) => item.node.kind === "Direction").length;
  const bits = [];
  if (ideas) bits.push(`${ideas} idea${ideas === 1 ? "" : "s"}`);
  if (evidence) bits.push(`${evidence} evidence`);
  if (claims) bits.push(`${claims} claim${claims === 1 ? "" : "s"}`);
  if (directions) bits.push(`${directions} direction${directions === 1 ? "" : "s"}`);
  return bits.length ? bits.join(" | ") : `${items.length} node${items.length === 1 ? "" : "s"}`;
}

function svgLines(text, maxChars = 23, maxLines = 2) {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  const lines = [];
  let line = "";
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (next.length > maxChars && line) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  const clipped = lines.slice(0, maxLines);
  if (lines.length > maxLines) clipped[clipped.length - 1] = `${clipped[clipped.length - 1].slice(0, Math.max(2, maxChars - 3))}...`;
  return clipped.length ? clipped : [""];
}

function compactSvgLines(text, maxChars = 14, maxLines = 2) {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  const lines = [];
  let line = "";
  const clipWord = (word) => word.length > maxChars ? `${word.slice(0, Math.max(2, maxChars - 3))}...` : word;
  for (const rawWord of words) {
    const word = clipWord(rawWord);
    const next = line ? `${line} ${word}` : word;
    if (next.length > maxChars && line) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
    if (lines.length >= maxLines) break;
  }
  if (line && lines.length < maxLines) lines.push(line);
  if (!lines.length) lines.push("");
  const hasRemaining = words.join(" ").length > lines.join(" ").length;
  if (hasRemaining && lines.length) {
    const last = lines.length - 1;
    lines[last] = `${lines[last].slice(0, Math.max(2, maxChars - 3))}...`;
  }
  return lines;
}

function nodeWidth(item) {
  if (item.node.kind === "CData") return 244;
  if (item.node.kind === "Group") return 220;
  if (item.node.kind === "LiteratureClaim") return 224;
  if (item.node.kind === "Direction") return 224;
  if (item.node.kind === "EvidenceResult" || item.node.kind === "Conclusion") return 194;
  return NODE_WIDTH;
}

function nodeHeight(item) {
  if (item.node.kind === "CData") return 92;
  if (item.node.kind === "Group") return 78;
  if (item.node.kind === "EvidenceResult" || item.node.kind === "Conclusion") return 62;
  return NODE_HEIGHT;
}

function nodeColor(node) {
  if (node.kind === "EvidenceResult" || node.kind === "Conclusion") {
    const status = String(node.hypothesis_status || "").toLowerCase();
    if (status === "supported") return "#2a9d55";
    if (status === "borderline") return "#c8841b";
    if (status === "inconclusive") return "#8b95a3";
    if (status === "contradicted") return "#8b5cf6";
    if (status === "not supported") return "#d64545";
    return "#8b95a3";
  }
  return colors[node.kind] || "#8b95a3";
}

function nodeAccentColor(node) {
  if (node.kind === "EvidenceResult" || node.kind === "Conclusion") return nodeColor(node);
  if (node.kind === "Idea") return colors.Idea;
  return nodeColor(node);
}

function nodeMetaLabel(item) {
  const node = item.node;
  if (node.kind === "Idea") {
    const ev = evidenceForIdea(node.id);
    const pieces = [];
    const run = runForIdea(node.id);
    if (run) pieces.push(runOrder(run) > 1 ? `Round ${runOrder(run)}` : "Round 1");
    if (node.signature?.parameter_family) pieces.push(node.signature.parameter_family);
    if (ev?.p_value !== undefined && ev?.p_value !== null) pieces.push(`p=${formatNumber(ev.p_value)}`);
    return pieces.join(" | ");
  }
  if (node.kind === "EvidenceResult" || node.kind === "Conclusion") return evidenceSummary(node);
  if (node.kind === "Direction") return directionMeta(node);
  return item.entry.meta || displayKind(node);
}

function nodeBadge(item) {
  const node = item?.node;
  if (!node) return null;
  if (node.kind === "Idea") {
    const status = statusForIdea(node.id);
    return { text: status, status };
  }
  if (node.kind === "EvidenceResult" || node.kind === "Conclusion") {
    const status = node.hypothesis_status || "Pending";
    return { text: status, status };
  }
  if (node.kind === "Direction") return { text: "Direction", status: "Pending" };
  if (node.kind === "LiteratureClaim") return { text: "Claim", status: "Pending" };
  return null;
}

function nodeBadgeWidth(item) {
  const text = nodeBadge(item)?.text || "";
  return Math.min(96, Math.max(48, text.length * 6.2 + 18));
}

function childSummary(item) {
  const count = item.entry.hiddenChildCount || 0;
  if (!count) return "";
  return `${count} item${count === 1 ? "" : "s"}`;
}

function bestInitialIdeaId() {
  const ideas = nodes.filter((n) => n.kind === "Idea");
  if (!ideas.length) return cdataNode.id;
  return [...ideas].sort((a, b) => {
    const sa = statusOrder.indexOf(statusForIdea(a.id));
    const sb = statusOrder.indexOf(statusForIdea(b.id));
    const eva = evidenceForIdea(a.id);
    const evb = evidenceForIdea(b.id);
    const pa = eva?.p_value ?? Number.POSITIVE_INFINITY;
    const pb = evb?.p_value ?? Number.POSITIVE_INFINITY;
    return sa - sb || pa - pb || label(a).localeCompare(label(b));
  })[0].id;
}

function nodeTitleText(item) {
  const node = item.node;
  if (node.kind === "EvidenceResult" || node.kind === "Conclusion") return node.hypothesis_status || "Conclusion";
  return label(node);
}

function nodeTokens(item) {
  const node = item.node;
  const tokens = [];
  if (node.kind === "Idea") {
    const run = runForIdea(node.id);
    const ev = evidenceForIdea(node.id);
    if (run) tokens.push(runOrder(run) > 1 ? `Round ${runOrder(run)}` : "Round 1");
    if (node.signature?.parameter_family) tokens.push(node.signature.parameter_family);
    if (Array.isArray(node.signature?.markers) && node.signature.markers.length) tokens.push(node.signature.markers.slice(0, 2).join(" / "));
    if (Array.isArray(node.signature?.genes) && node.signature.genes.length) tokens.push(`gene ${node.signature.genes.slice(0, 2).join(", ")}`);
    if (ev?.p_value !== undefined && ev?.p_value !== null) tokens.push(`p ${formatNumber(ev.p_value)}`);
  } else if (node.kind === "EvidenceResult" || node.kind === "Conclusion") {
    if (node.p_value !== undefined && node.p_value !== null) tokens.push(`p ${formatNumber(node.p_value)}`);
    if (node.effect_size !== undefined && node.effect_size !== null) tokens.push(`effect ${formatNumber(node.effect_size)}`);
    if (node.test_method) tokens.push(truncate(node.test_method, 28));
  } else if (node.kind === "Direction") {
    tokens.push(directionTypeLabel(node));
    if (node.priority !== undefined && node.priority !== null) tokens.push(`priority ${formatNumber(node.priority)}`);
    const parentCount = directionParentIdeaIds(node).length;
    if (parentCount) tokens.push(`${parentCount} parent`);
  } else if (node.kind === "LiteratureClaim") {
    if (node.source_title) tokens.push(truncate(node.source_title, 22));
    const related = claimIdeaIds(node.id).length;
    if (related) tokens.push(`${related} ideas`);
  } else if (node.kind === "Group") {
    if (item.entry.meta) tokens.push(item.entry.meta);
  } else if (node.kind === "CData") {
    tokens.push(`${rawGraph.summary?.n_nodes ?? rawGraph.nodes.length} nodes`);
    tokens.push(`${rawGraph.summary?.n_edges ?? rawGraph.edges.length} edges`);
  }
  return tokens.filter(Boolean).slice(0, 4);
}

function nodeCardClasses(item) {
  return [
    "graph-node-card",
    `kind-${String(item.node.kind || "node").toLowerCase()}`,
    statusClass(nodeBadge(item)?.status || item.node.hypothesis_status || "")
  ].filter(Boolean).join(" ");
}

function globalNodeRadius(item) {
  if (item.node.kind === "CData") return 8;
  if (item.node.kind === "LiteratureClaim") return 5.5;
  if (item.node.kind === "Direction") return 5.5;
  if (item.node.kind === "EvidenceResult" || item.node.kind === "Conclusion") return 4.7;
  return 5.5;
}

function globalLabelWidth(item) {
  if (item.node.kind === "CData") return 188;
  if (item.node.kind === "EvidenceResult" || item.node.kind === "Conclusion") return 148;
  return 178;
}

function globalTitleLines(item) {
  const maxChars = item.node.kind === "EvidenceResult" || item.node.kind === "Conclusion" ? 20 : 24;
  return svgLines(nodeTitleText(item), maxChars, item.node.kind === "CData" ? 1 : 2);
}

function globalShortLabelLines(item) {
  const maxChars = item.node.kind === "CData"
    ? 18
    : item.node.kind === "EvidenceResult" || item.node.kind === "Conclusion"
      ? 12
      : item.node.kind === "LiteratureClaim" || item.node.kind === "Direction"
        ? 13
        : 15;
  return compactSvgLines(nodeTitleText(item), maxChars, item.node.kind === "CData" ? 1 : 2);
}

function globalMetaText(item) {
  const node = item.node;
  if (node.kind === "Idea") return statusForIdea(node.id);
  if (node.kind === "EvidenceResult" || node.kind === "Conclusion") {
    const bits = [node.hypothesis_status || "Untested"];
    if (node.p_value !== undefined && node.p_value !== null) bits.push(`p ${formatNumber(node.p_value)}`);
    return bits.join(" | ");
  }
  if (node.kind === "Direction") return directionTypeLabel(node);
  if (node.kind === "LiteratureClaim") return "literature claim";
  if (node.kind === "CData") return `${rawGraph.summary?.n_nodes ?? rawGraph.nodes.length} nodes | ${rawGraph.summary?.n_edges ?? rawGraph.edges.length} edges`;
  return displayKind(node);
}

const App = {
  components: {
    BookOpen,
    CircleDot,
    Crosshair,
    ExternalLink,
    GitBranch,
    Moon,
    Notebook,
    Search,
    Sun,
    Waypoints,
    X,
    ZoomIn,
    ZoomOut
  },
  template: `
    <div class="app-shell">
      <header class="topbar">
        <div class="brand-block">
          <div class="brand-mark"><Waypoints :size="19" /></div>
          <div>
            <div class="eyebrow compact">Iterative auto-discovery</div>
            <h1>{{ title }}</h1>
          </div>
        </div>
        <div class="top-panel-actions">
          <button
            class="theme-toggle"
            :title="darkMode ? 'Switch to light mode' : 'Switch to dark mode'"
            :aria-label="darkMode ? 'Switch to light mode' : 'Switch to dark mode'"
            :aria-pressed="darkMode ? 'true' : 'false'"
            @click="toggleTheme"
          >
            <Sun v-if="darkMode" :size="16" />
            <Moon v-else :size="16" />
          </button>
          <button title="Toggle explore panel" aria-label="Toggle explore panel" :class="{active: sidebarOpen}" @click="sidebarOpen = !sidebarOpen">
            <Search :size="16" />
            <span>Explore</span>
          </button>
        </div>
      </header>

      <div
        class="workspace"
        :class="{'focus-mode': focusMode, 'sidebar-open': sidebarOpen && !focusMode, 'inspector-open': inspectorOpen && !focusMode}"
        :style="workspaceStyle"
      >
        <button v-if="!sidebarOpen && !focusMode" class="edge-panel-toggle" title="Open explore panel" aria-label="Open explore panel" @click="sidebarOpen = true">
          <Search :size="17" />
        </button>

        <aside v-if="sidebarOpen && !focusMode" class="sidebar">
          <div class="side-head">
            <div>
              <div class="eyebrow compact">Explore</div>
              <strong>Ideas and evidence</strong>
            </div>
            <button class="panel-close" title="Hide explore panel" aria-label="Hide explore panel" @click="sidebarOpen = false">x</button>
          </div>

          <section class="overview-card">
            <div class="overview">
              <div class="metric"><b>{{ stats.ideas }}</b><span>ideas</span></div>
              <div class="metric"><b>{{ stats.evidence }}</b><span>evidence</span></div>
              <div class="metric"><b>{{ shownCount }}</b><span>shown</span></div>
              <div class="metric"><b>{{ stats.claims }}</b><span>claims</span></div>
            </div>
          </section>

          <section class="search-card">
            <label class="search-box">
              <Search :size="16" />
              <input v-model="query" placeholder="Search ideas, genes, claims..." />
            </label>
            <div class="status-tabs">
              <button v-for="s in statusFilters" :key="s" :class="{active: statusFilter === s}" @click="statusFilter = s">
                <span>{{ s }}</span>
                <b>{{ statusCount(s) }}</b>
              </button>
            </div>
          </section>

          <section class="idea-list">
            <div class="section-title">Visible ideas</div>
            <button v-for="idea in visibleIdeas.slice(0, 80)" :key="idea.id" class="idea-card" :class="{selected: selectedId === idea.id}" @click="selectNode(idea.id)">
              <span class="status-pill" :class="statusClass(statusForIdea(idea.id))">{{ statusForIdea(idea.id) }}</span>
              <span class="idea-card-title">{{ truncate(label(idea), 82) }}</span>
              <span class="idea-card-meta">{{ ideaMeta(idea) }}</span>
            </button>
            <div v-if="!visibleIdeas.length" class="empty">No matching ideas.</div>
          </section>
        </aside>
        <div
          v-if="sidebarOpen && !focusMode"
          class="panel-resizer sidebar-resizer"
          role="separator"
          aria-label="Resize explore panel"
          @pointerdown="startPanelResize('sidebar', $event)"
        ></div>

        <main class="graph-card">
          <div class="graph-toolbar">
            <div>
              <div class="graph-title-row">
                <GitBranch :size="17" />
                <span>Idea graph</span>
              </div>
              <div class="toolbar-subtitle">{{ graphSubtitle }}</div>
            </div>
          </div>
          <div ref="plotRef" class="plot" :class="['layout-' + layoutDirection, {'overview-zoom': overviewZoom, 'global-context': globalView}]">
            <div class="canvas-tools layout-tools">
              <button title="Fit full overview" data-tooltip="Fit overview" aria-label="Fit full overview" @click="fitOverview"><Crosshair :size="15" /></button>
            </div>
            <div class="canvas-tools zoom-tools">
              <button title="Zoom out" data-tooltip="Zoom out" aria-label="Zoom out" @click="zoomOut"><ZoomOut :size="15" /></button>
              <span>{{ zoomPercent }}%</span>
              <button title="Zoom in" data-tooltip="Zoom in" aria-label="Zoom in" @click="zoomIn"><ZoomIn :size="15" /></button>
              <button title="Focus selected node" data-tooltip="Focus selected node" aria-label="Focus selected node" @click="focusSelected"><CircleDot :size="15" /></button>
            </div>
            <div class="minimap">
              <div class="minimap-title">Overview</div>
              <svg
                class="minimap-svg"
                :viewBox="'0 0 ' + minimap.width + ' ' + minimap.height"
                @click="onMinimapClick"
              >
                <path
                  v-for="link in tree.links"
                  :key="'mini-' + link.source.uid + '-' + link.target.uid"
                  class="minimap-edge"
                  :class="link.role"
                  :d="minimapEdgePath(link)"
                />
                <circle
                  v-for="item in tree.nodes"
                  :key="'mini-' + item.uid"
                  class="minimap-node"
                  :class="{active: activeUids.has(item.uid), selected: isSelectedItem(item)}"
                  :cx="minimapX(item.x)"
                  :cy="minimapY(item.y)"
                  :r="isSelectedItem(item) ? 4 : 2.6"
                  :fill="nodeAccentColor(item.node)"
                />
                <rect
                  class="minimap-viewport"
                  :x="minimap.view.x"
                  :y="minimap.view.y"
                  :width="minimap.view.width"
                  :height="minimap.view.height"
                  rx="4"
                />
              </svg>
            </div>
            <svg
              class="graph-svg"
              :viewBox="'0 0 ' + plotSize.width + ' ' + plotSize.height"
              @wheel="onWheel"
              @pointermove="onPointerMove"
              @pointerup="endPan"
              @pointerleave="endPan"
            >
              <rect class="stage-hit" x="0" y="0" :width="plotSize.width" :height="plotSize.height" @pointerdown="startPan" />
              <defs>
                <marker id="edge-arrow-active" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto" markerUnits="strokeWidth">
                  <path d="M 0 0 L 6 3 L 0 6 z" class="edge-arrow-active" />
                </marker>
                <marker id="edge-arrow-direction" markerWidth="5.5" markerHeight="5.5" refX="4.7" refY="2.75" orient="auto" markerUnits="strokeWidth">
                  <path d="M 0 0 L 5.5 2.75 L 0 5.5 z" class="edge-arrow-direction" />
                </marker>
              </defs>
              <g class="viewport-layer" :transform="viewportTransform">
                <g class="lane-guides">
                  <g
                    v-for="lane in laneGuides"
                    :key="'lane-' + lane.depth"
                    class="lane-guide"
                    :class="{active: lane.active, odd: lane.depth % 2 === 1}"
                  >
                    <rect class="lane-band" :x="lane.x" :y="lane.y" :width="lane.width" :height="lane.height" rx="18" />
                    <text class="lane-label" :x="lane.x + 18" :y="lane.y + 26">{{ lane.label }}</text>
                    <text class="lane-meta" :x="lane.x + 18" :y="lane.y + 45">{{ lane.meta }}</text>
                  </g>
                </g>
                <path
                  v-for="link in tree.links"
                  :key="link.source.uid + '-' + link.target.uid"
                  :class="edgeClass(link)"
                  :data-source-id="link.source.node.id"
                  :data-target-id="link.target.node.id"
                  :data-edge-role="link.role"
                  :d="edgePath(link)"
                  :marker-end="edgeMarker(link)"
                />
                <g
                  v-for="link in tree.links"
                  v-show="edgeLabelVisible(link)"
                  :key="'label-' + link.source.uid + '-' + link.target.uid"
                  class="edge-label"
                  :class="link.role"
                  :transform="edgeLabelTransform(link, layoutDirection)"
                >
                  <rect class="edge-label-bg" :x="-edgeLabelWidth(link) / 2" y="-11" :width="edgeLabelWidth(link)" height="22" rx="11" />
                  <text class="edge-label-text" y="1" text-anchor="middle" dominant-baseline="central">{{ edgeLabel(link) }}</text>
                </g>
                <g
                  v-for="item in tree.nodes"
                  :key="item.uid"
                  :class="nodeClass(item)"
                  :data-node-id="item.node.id"
                  :data-node-kind="item.node.kind"
                  :transform="'translate(' + item.x + ',' + item.y + ')'"
                  @mouseover.stop="hoverNode(item.node.id, item.uid)"
                  @mousemove.stop="hoverNode(item.node.id, item.uid)"
                  @pointerenter.stop="hoverNode(item.node.id, item.uid)"
                  @pointerleave.stop="clearHover"
                  @click.stop="selectNode(item.node.id, item.uid)"
                >
                  <circle
                    v-if="isSelectedItem(item) && globalView"
                    class="selection-ring global"
                    :r="globalNodeRadius(item) * globalDotScale + 10"
                  />
                  <circle
                    v-else-if="isSelectedItem(item)"
                    class="selection-ring"
                    :r="selectionRingRadius"
                  />
                  <g
                    v-if="globalView"
                    class="global-node-visual"
                    :class="[String(item.node.kind || 'node').toLowerCase(), statusClass(nodeBadge(item)?.status || item.node.hypothesis_status || '')]"
                    :style="{'--node-accent': nodeAccentColor(item.node)}"
                  >
                    <circle class="global-node-hit" :r="globalNodeRadius(item) * globalDotScale + 14" />
                    <circle class="global-node-halo" :r="globalNodeRadius(item) * globalDotScale + 7" />
                    <circle class="global-node-dot" :r="globalNodeRadius(item) * globalDotScale" />
                    <text
                      class="global-node-name"
                      text-anchor="middle"
                      :y="globalNodeRadius(item) * globalDotScale + 16"
                    >
                      <tspan
                        v-for="(line, i) in globalShortLabelLines(item)"
                        :key="'global-short-label-' + item.uid + '-' + i"
                        x="0"
                        :dy="i === 0 ? 0 : 9.5"
                      >{{ line }}</tspan>
                    </text>
                  </g>
                  <template v-else>
                    <rect class="node-shadow" :x="-nodeWidth(item) / 2" :y="-nodeHeight(item) / 2" :width="nodeWidth(item)" :height="nodeHeight(item)" rx="8" />
                    <rect class="node-card-bg" :x="-nodeWidth(item) / 2" :y="-nodeHeight(item) / 2" :width="nodeWidth(item)" :height="nodeHeight(item)" rx="8" />
                    <circle
                      v-if="item.parent"
                      class="node-port node-port-in"
                      :cx="isHorizontal ? -nodeWidth(item) / 2 - 8 : 0"
                      :cy="isHorizontal ? 0 : -nodeHeight(item) / 2 - 8"
                      r="4"
                      :style="{'--node-accent': nodeAccentColor(item.node)}"
                    />
                    <circle
                      v-if="item.entry.childCount"
                      class="node-port node-port-out"
                      :cx="isHorizontal ? nodeWidth(item) / 2 + 8 : 0"
                      :cy="isHorizontal ? 0 : nodeHeight(item) / 2 + 8"
                      r="4"
                      :style="{'--node-accent': nodeAccentColor(item.node)}"
                    />
                    <foreignObject
                      :x="-nodeWidth(item) / 2"
                      :y="-nodeHeight(item) / 2"
                      :width="nodeWidth(item)"
                      :height="nodeHeight(item)"
                    >
                      <div
                        xmlns="http://www.w3.org/1999/xhtml"
                        :class="nodeCardClasses(item)"
                        :style="{'--node-accent': nodeAccentColor(item.node)}"
                      >
                        <div class="node-card-top">
                          <span class="node-caption">{{ item.entry.caption }}</span>
                          <span v-if="nodeBadge(item)" class="node-badge" :class="statusClass(nodeBadge(item).status)">
                            <span class="node-badge-dot"></span>
                            <span class="node-badge-text">{{ nodeBadge(item).text }}</span>
                          </span>
                        </div>
                        <div class="node-title">{{ truncate(nodeTitleText(item), compactLabels ? 48 : 68) }}</div>
                        <div v-if="!compactLabels && !overviewZoom" class="node-token-row">
                          <span v-for="token in nodeTokens(item)" :key="token" class="node-token">{{ token }}</span>
                        </div>
                        <button
                          v-if="item.entry.childCount"
                          class="node-expander"
                          :class="{collapsed: item.entry.isCollapsed}"
                          type="button"
                          @click.stop="toggleBranch(item.node.id)"
                        >
                          {{ item.entry.isCollapsed ? '+' : '-' }}
                        </button>
                        <span v-if="childSummary(item)" class="child-count">{{ childSummary(item) }}</span>
                      </div>
                    </foreignObject>
                  </template>
                </g>
                <g v-if="globalView" class="global-tooltip-layer">
                  <g
                    v-for="item in tree.nodes"
                    v-show="isHoveredItem(item)"
                    :key="'tooltip-' + item.uid"
                    class="global-node-tooltip"
                    :class="[String(item.node.kind || 'node').toLowerCase(), statusClass(nodeBadge(item)?.status || item.node.hypothesis_status || '')]"
                    :transform="'translate(' + item.x + ',' + item.y + ')'"
                  >
                    <g
                      class="global-node-label is-visible"
                      :transform="'translate(0,' + (globalNodeRadius(item) * globalDotScale + 10) + ') scale(' + globalLabelScale + ')'"
                    >
                      <rect
                        class="global-label-bg"
                        :x="-globalLabelWidth(item) / 2"
                        y="0"
                        :width="globalLabelWidth(item)"
                        height="58"
                        rx="12"
                      />
                      <text class="global-node-caption" text-anchor="middle" y="15">{{ item.entry.caption }}</text>
                      <text
                        v-for="(line, i) in globalTitleLines(item)"
                        :key="'global-tooltip-title-' + item.uid + '-' + i"
                        class="global-node-title"
                        text-anchor="middle"
                        :y="31 + i * 13"
                      >{{ line }}</text>
                      <text class="global-node-meta" text-anchor="middle" y="54">{{ truncate(globalMetaText(item), 34) }}</text>
                    </g>
                  </g>
                </g>
              </g>
            </svg>
          </div>
        </main>

        <aside v-if="inspectorOpen && !focusMode" class="inspector" :class="{'preview-mode': selectedNotebookPreviewOpen && selectedNotebookHref}">
          <section v-if="selectedNotebookPreviewOpen && selectedNotebookHref" class="inspector-preview">
            <div class="inspector-preview-toolbar">
              <div>
                <div class="eyebrow">Notebook preview</div>
                <h2>{{ truncate(label(selectedNode), 56) }}</h2>
              </div>
              <div class="inspector-preview-actions">
                <a
                  class="preview-icon-button"
                  :href="selectedPreviewHref"
                  target="_blank"
                  rel="noreferrer"
                  title="Open preview in a new tab"
                  aria-label="Open preview in a new tab"
                >
                  <ExternalLink :size="16" />
                </a>
                <button
                  class="preview-icon-button"
                  type="button"
                  title="Back to details"
                  aria-label="Back to details"
                  @click="selectedNotebookPreviewOpen = false"
                >
                  <X :size="16" />
                </button>
              </div>
            </div>
            <iframe :src="selectedPreviewHref" title="Notebook preview" loading="lazy" @load="prepareNotebookPreviewFrame"></iframe>
          </section>

          <div v-else-if="selectedNode" class="detail">
            <div class="detail-head">
              <div>
                <div class="eyebrow">{{ displayKind(selectedNode) }}</div>
                <h2>{{ label(selectedNode) }}</h2>
              </div>
              <div class="detail-head-actions">
                <span v-if="selectedStatus" class="status-pill large" :class="statusClass(selectedStatus)">{{ selectedStatus }}</span>
                <button class="panel-close" title="Hide inspector" aria-label="Hide inspector" @click="inspectorOpen = false">x</button>
              </div>
            </div>
            <div class="badge-row">
              <button
                v-if="selectedNotebookHref"
                class="soft-chip notebook-chip"
                type="button"
                :class="{active: selectedNotebookPreviewOpen}"
                title="Preview notebook in the inspector"
                aria-label="Preview notebook in the inspector"
                @click="selectedNotebookPreviewOpen = true"
              >
                <Notebook :size="15" />
                Notebook
              </button>
              <a
                v-if="selectedNotebookHref"
                class="icon-link"
                :href="selectedNotebookHref"
                target="_blank"
                rel="noreferrer"
                title="Open notebook in a new tab"
                aria-label="Open notebook in a new tab"
              >
                <ExternalLink :size="15" />
              </a>
              <span class="soft-chip"><BookOpen :size="14" /> {{ selectedPathNodes.length }} levels</span>
            </div>
            <p v-if="selectedSummary">{{ selectedSummary }}</p>

            <section
              v-if="selectedGraphicAbstract.state === 'loaded'"
              class="graphic-abstract-card"
              :class="{active: graphicAbstractDialogOpen}"
            >
              <div class="graphic-abstract-head">
                <span>{{ selectedNotebookVisualTitle }}</span>
                <button
                  type="button"
                  :title="'Preview notebook at ' + selectedNotebookVisualTitle"
                  :aria-label="'Preview notebook at ' + selectedNotebookVisualTitle"
                  @click="selectedNotebookPreviewOpen = true"
                >preview</button>
              </div>
              <button
                class="graphic-abstract-image-button"
                type="button"
                :title="'Expand ' + selectedNotebookVisualTitle"
                :aria-label="'Expand ' + selectedNotebookVisualTitle"
                @click="graphicAbstractDialogOpen = true"
              >
                <img :src="selectedGraphicAbstract.src" :alt="selectedGraphicAbstract.alt" loading="lazy" />
              </button>
            </section>

            <div v-if="selectedOutcome" class="inspector-outcome-card" :class="statusClass(selectedOutcome.hypothesis_status)">
              <div class="key">Notebook verdict</div>
              <div class="outcome-title-row">
                <span class="outcome-dot"></span>
                <strong>{{ selectedOutcome.hypothesis_status || 'Evidence' }}</strong>
              </div>
              <div class="outcome-metrics light">
                <span v-if="selectedOutcome.p_value !== undefined && selectedOutcome.p_value !== null">p {{ formatNumber(selectedOutcome.p_value) }}</span>
                <span v-if="selectedOutcome.effect_size !== undefined && selectedOutcome.effect_size !== null">effect {{ formatNumber(selectedOutcome.effect_size) }}</span>
                <span v-if="selectedOutcome.direction_status">{{ selectedOutcome.direction_status }}</span>
              </div>
            </div>

            <div v-if="selectedQuickFacts.length" class="fact-grid">
              <div v-for="fact in selectedQuickFacts" :key="fact.label" class="fact-tile">
                <div class="fact-label">{{ fact.label }}</div>
                <div class="fact-value">{{ fact.value }}</div>
              </div>
            </div>

            <div class="kv"><div class="key">ID</div><div class="value mono">{{ selectedNode.id }}</div></div>
            <div v-if="selectedRows.length" class="detail-section-heading">Details</div>
            <div v-for="[key, value] in selectedRows" :key="key" class="kv">
              <div class="key">{{ key }}</div>
              <div class="value">
                <template v-for="line in valueLines(value)" :key="line">
                  <span class="value-pill" v-if="Array.isArray(value) || (value && typeof value === 'object')">{{ line }}</span>
                  <span v-else>{{ line }}</span>
                </template>
              </div>
            </div>

            <details v-if="technicalRowsForSelected.length" class="technical">
              <summary>Technical details</summary>
              <div v-for="[key, value] in technicalRowsForSelected" :key="key" class="kv">
                <div class="key">{{ key }}</div>
                <div class="value">
                  <span v-for="line in valueLines(value)" :key="line" class="value-pill">{{ line }}</span>
                </div>
              </div>
            </details>
          </div>
          <div v-else class="empty">No node selected.</div>
        </aside>
        <div
          v-if="inspectorOpen && !focusMode"
          class="panel-resizer inspector-resizer"
          role="separator"
          aria-label="Resize inspector panel"
          @pointerdown="startPanelResize('inspector', $event)"
        ></div>
      </div>

      <div
        v-if="graphicAbstractDialogOpen && selectedGraphicAbstract.state === 'loaded'"
        class="graphic-abstract-dialog-backdrop"
        role="dialog"
        aria-modal="true"
        :aria-label="selectedNotebookVisualTitle + ' preview'"
        @click.self="graphicAbstractDialogOpen = false"
      >
        <div class="graphic-abstract-dialog">
          <div class="graphic-abstract-dialog-head">
            <div>
              <div class="eyebrow">{{ selectedNotebookVisualTitle }}</div>
              <h2>{{ truncate(label(selectedNode), 74) }}</h2>
            </div>
            <button
              class="preview-icon-button"
              type="button"
              :title="'Close ' + selectedNotebookVisualTitle"
              :aria-label="'Close ' + selectedNotebookVisualTitle"
              @click="graphicAbstractDialogOpen = false"
            >
              <X :size="16" />
            </button>
          </div>
          <div class="graphic-abstract-dialog-body">
            <img :src="selectedGraphicAbstract.src" :alt="selectedGraphicAbstract.alt" />
          </div>
        </div>
      </div>

      <div
        v-if="notebookPreviewImage.open"
        class="graphic-abstract-dialog-backdrop"
        role="dialog"
        aria-modal="true"
        aria-label="Notebook image preview"
        @click.self="closeNotebookPreviewImage"
      >
        <div class="graphic-abstract-dialog">
          <div class="graphic-abstract-dialog-head">
            <div>
              <div class="eyebrow">Notebook image</div>
              <h2>{{ truncate(notebookPreviewImage.alt || label(selectedNode), 74) }}</h2>
            </div>
            <button
              class="preview-icon-button"
              type="button"
              title="Close notebook image"
              aria-label="Close notebook image"
              @click="closeNotebookPreviewImage"
            >
              <X :size="16" />
            </button>
          </div>
          <div class="graphic-abstract-dialog-body">
            <img :src="notebookPreviewImage.src" :alt="notebookPreviewImage.alt || 'Notebook image'" />
          </div>
        </div>
      </div>
    </div>
  `,
  setup() {
    const title = document.title || "U-Chrom Idea Graph";
    const themeMode = ref(initialThemeMode());
    const darkMode = computed(() => themeMode.value === "dark");
    const query = ref("");
    const statusFilter = ref("All");
    const selectedId = ref(cdataNode.id);
    const selectedUid = ref("");
    const hoveredId = ref("");
    const hoveredUid = ref("");
    const compactLabels = ref(false);
    const spotlightMode = ref(false);
    const globalView = ref(true);
    const layoutDirection = ref("round");
    const focusMode = ref(false);
    const sidebarOpen = ref(false);
    const inspectorOpen = ref(false);
    const selectedNotebookPreviewOpen = ref(false);
    const graphicAbstractDialogOpen = ref(false);
    const notebookPreviewImage = ref({ open: false, src: "", alt: "" });
    const sidebarWidth = ref(278);
    const inspectorWidth = ref(360);
    const plotRef = ref(null);
    const plotSize = ref({ width: 1200, height: 720 });
    const view = ref({ x: 0, y: 0, k: 0.92 });
    const dragging = ref(null);
    const panelResize = ref(null);
    const expandedIds = ref(new Set([cdataNode.id]));
    const viewportPinned = ref(false);
    const statusFilters = ["All", ...statusOrder];
    let resizeObserver = null;

    const stats = computed(() => ({
      ideas: nodes.filter((n) => n.kind === "Idea").length,
      evidence: nodes.filter((n) => n.kind === "EvidenceResult").length,
      directions: nodes.filter((n) => n.kind === "Direction").length,
      claims: nodes.filter((n) => n.kind === "LiteratureClaim").length
    }));
    const workspaceStyle = computed(() => ({
      "--sidebar-width": `${sidebarWidth.value}px`,
      "--inspector-width": `${inspectorWidth.value}px`
    }));
    const statusCounts = computed(() => {
      const allIdeas = nodes.filter((n) => n.kind === "Idea");
      const counts = { All: allIdeas.filter((idea) => statusForIdea(idea.id) !== "Rejected").length };
      for (const status of statusOrder) counts[status] = 0;
      for (const idea of allIdeas) {
        counts[statusForIdea(idea.id)] = (counts[statusForIdea(idea.id)] || 0) + 1;
      }
      return counts;
    });
    const evidenceStatusItems = computed(() => {
      const total = Math.max(1, statusCounts.value.All || 1);
      return statusOrder.map((status) => ({
        status,
        count: statusCounts.value[status] || 0,
        percent: Math.max(4, ((statusCounts.value[status] || 0) / total) * 100)
      }));
    });

    const summary = computed(() => `${rawGraph.summary?.n_nodes ?? rawGraph.nodes.length} nodes, ${rawGraph.summary?.n_edges ?? rawGraph.edges.length} edges`);

    const visibleIdeaIds = computed(() => {
      const q = query.value.trim().toLowerCase();
      return new Set(nodes
        .filter((n) => n.kind === "Idea")
        .filter((idea) => {
          const status = statusForIdea(idea.id);
          return statusFilter.value === "All" ? status !== "Rejected" : status === statusFilter.value;
        })
        .filter((idea) => {
          if (!q) return true;
          const ev = evidenceForIdea(idea.id);
          const nb = notebookForIdea(idea.id);
          const direction = directionForIdea(idea);
          const claims = sourceClaimIds(idea).map((id) => byId.get(id)).filter(Boolean);
          return [idea, ev, nb, direction, ...claims].filter(Boolean).some((n) => searchable(n).includes(q));
        })
        .map((idea) => idea.id));
    });

    const visibleIdeas = computed(() => [...visibleIdeaIds.value]
      .map((id) => byId.get(id))
      .filter(Boolean)
      .sort((a, b) => statusOrder.indexOf(statusForIdea(a.id)) - statusOrder.indexOf(statusForIdea(b.id)) || label(a).localeCompare(label(b))));

    const model = computed(() => buildDiscoveryModel(visibleIdeaIds.value, query.value.trim().toLowerCase()));
    const selectedPathList = computed(() => findEntryPath(model.value.root, selectedId.value) || [cdataNode.id]);
    const selectedPathIds = computed(() => new Set(selectedPathList.value));
    const selectedPathNodes = computed(() => {
      const path = selectedUidExists.value ? visualPathIdsForUid(selectedUid.value) : selectedPathList.value;
      return path.map((id) => byId.get(id)).filter(Boolean);
    });
    const selectedEdgeKeys = computed(() => {
      const keys = new Set();
      const path = selectedUidExists.value
        ? visualPathUidsForUid(selectedUid.value)
        : visualPathUidsForNodePath(selectedPathList.value);
      for (let i = 1; i < path.length; i += 1) keys.add(`${path[i - 1]}->${path[i]}`);
      const n = byId.get(selectedId.value);
      if (n?.kind === "Idea") {
        const selectedItem = selectedUidExists.value
          ? tree.value.nodes.find((item) => item.uid === selectedUid.value)
          : tree.value.byNodeId.get(n.id);
        const outcomeItem = (selectedItem?.children || []).find((child) => (
          child.node.kind === "EvidenceResult" || child.node.kind === "Conclusion"
        ));
        if (selectedItem && outcomeItem) keys.add(`${selectedItem.uid}->${outcomeItem.uid}`);
      }
      return keys;
    });
    const hoveredPathIds = computed(() => new Set(hoveredId.value
      ? (hoveredUidExists.value ? visualPathIdsForUid(hoveredUid.value) : (findEntryPath(model.value.root, hoveredId.value) || []))
      : []));
    const autoExpandAll = computed(() => {
      if (globalView.value) return true;
      const hasSearch = Boolean(query.value.trim());
      return visibleIdeas.value.length <= 12 || hasSearch;
    });
    const expandedRoot = computed(() => pruneEntry(model.value.root, expandedIds.value, selectedPathIds.value, autoExpandAll.value));
    const spotlightActive = computed(() => spotlightMode.value && !query.value.trim());
    const displayRoot = computed(() => {
      if (!spotlightActive.value) return expandedRoot.value;
      return spotlightEntry(expandedRoot.value, selectedPathIds.value, selectedId.value);
    });
    const expandedTree = computed(() => layoutTree(expandedRoot.value, layoutDirection.value));
    const tree = computed(() => layoutTree(displayRoot.value, layoutDirection.value));
    const selectedUidExists = computed(() => Boolean(selectedUid.value && tree.value.nodes.some((item) => item.uid === selectedUid.value)));
    const hoveredUidExists = computed(() => Boolean(hoveredUid.value && tree.value.nodes.some((item) => item.uid === hoveredUid.value)));
    const hiddenBySpotlight = computed(() => Math.max(0, expandedTree.value.nodes.length - tree.value.nodes.length));
    const shownCount = computed(() => tree.value.nodes.length);
    const graphSubtitle = computed(() => {
      const directionLabel = layoutDirection.value === "horizontal"
        ? "left-right"
        : layoutDirection.value === "round"
          ? "round-lane"
          : "top-down";
      return globalView.value
        ? `${shownCount.value} expanded nodes in a ${directionLabel} graph; hover any dot to preview details`
        : `${tree.value.nodes.length} visible nodes, all loaded in a stable ${directionLabel} graph`;
    });
    const isHorizontal = computed(() => layoutDirection.value === "horizontal");
    const safeView = computed(() => sanitizeViewport(view.value));
    const zoomPercent = computed(() => Math.round(safeView.value.k * 100));
    const viewportTransform = computed(() => `translate(${safeView.value.x} ${safeView.value.y}) scale(${safeView.value.k})`);
    const overviewZoom = computed(() => safeView.value.k < 0.28);
    const globalDotScale = computed(() => globalView.value ? clamp(0.9 / Math.max(safeView.value.k, 0.01), 1, 14) : 1);
    const globalLabelScale = computed(() => globalView.value ? clamp(0.72 / Math.max(safeView.value.k, 0.01), 1, 12) : 1);
    const selectionRingRadius = computed(() => clamp(19 / Math.max(safeView.value.k, 0.01), 18, 190));
    const laneGuides = computed(() => {
      const byDepth = new Map();
      for (const item of tree.value.nodes) {
        if (!byDepth.has(item.depth)) byDepth.set(item.depth, []);
        byDepth.get(item.depth).push(item);
      }
      const bounds = treeBounds();
      return [...byDepth.entries()]
        .sort(([a], [b]) => a - b)
        .map(([depth, items]) => {
          const active = items.some((item) => activeUids.value.has(item.uid));
          if (layoutDirection.value === "horizontal") {
            return {
              depth,
              x: items[0].x - 132,
              y: bounds.minY - 8,
              width: 264,
              height: bounds.height + 16,
              label: laneLabel(depth, items),
              meta: laneMeta(items),
              active
            };
          }
          return {
            depth,
            x: bounds.minX - 8,
            y: items[0].y - 62,
            width: bounds.width + 16,
            height: 124,
            label: laneLabel(depth, items),
            meta: laneMeta(items),
            active
          };
        });
    });
    const minimap = computed(() => {
      const bounds = treeBounds();
      const pad = 12;
      const scale = clamp(Math.min(
        (MINIMAP_WIDTH - pad * 2) / bounds.width,
        (MINIMAP_HEIGHT - pad * 2) / bounds.height
      ), 0.001, 4, 1);
      const offsetX = (MINIMAP_WIDTH - bounds.width * scale) / 2 - bounds.minX * scale;
      const offsetY = (MINIMAP_HEIGHT - bounds.height * scale) / 2 - bounds.minY * scale;
      const v = safeView.value;
      const visibleWorld = {
        x: (0 - v.x) / v.k,
        y: (0 - v.y) / v.k,
        width: finiteNumber(plotSize.value.width, 1200) / v.k,
        height: finiteNumber(plotSize.value.height, 720) / v.k
      };
      return {
        width: MINIMAP_WIDTH,
        height: MINIMAP_HEIGHT,
        scale,
        offsetX,
        offsetY,
        view: {
          x: clamp(offsetX + visibleWorld.x * scale, 0, MINIMAP_WIDTH),
          y: clamp(offsetY + visibleWorld.y * scale, 0, MINIMAP_HEIGHT),
          width: clamp(visibleWorld.width * scale, 8, MINIMAP_WIDTH),
          height: clamp(visibleWorld.height * scale, 8, MINIMAP_HEIGHT)
        }
      };
    });

    const selectedNode = computed(() => byId.get(selectedId.value) || cdataNode);
    const selectedStatus = computed(() => {
      const n = selectedNode.value;
      if (n.kind === "Idea") return statusForIdea(n.id);
      return n.hypothesis_status || "";
    });
    const selectedSummary = computed(() => {
      const n = selectedNode.value;
      return n.summary || n.rationale || n.biological_hypothesis || n.claim || n.prompt || n.computable_parameter || "";
    });
    const selectedOutcome = computed(() => {
      const n = selectedNode.value;
      if (n.kind === "Idea") return evidenceForIdea(n.id);
      if (n.kind === "EvidenceResult" || n.kind === "Conclusion") return n;
      const evidenceEdge = neighborEdges(n.id).find((e) => outcomeRelations.has(e.relation));
      return evidenceEdge ? byId.get(evidenceEdge.source) || byId.get(evidenceEdge.target) || null : null;
    });
    const selectedEvidenceId = computed(() => selectedOutcome.value?.id || "");
    const selectedIdeaId = computed(() => {
      const n = selectedNode.value;
      if (n.kind === "Idea") return n.id;
      if (n.kind === "EvidenceResult" || n.kind === "Conclusion") return ideaForEvidence(n.id)?.id || "";
      return "";
    });
    const selectedRows = computed(() => detailRows(selectedNode.value));
    const technicalRowsForSelected = computed(() => technicalRows(selectedNode.value));
    const selectedQuickFacts = computed(() => quickFacts(selectedNode.value, selectedOutcome.value));
    const selectedNotebookHref = computed(() => {
      const n = selectedNode.value;
      if (n.kind === "NotebookRun" && n.path) return notebookHref(n.path);
      if (n.kind === "Idea") return notebookHref(notebookForIdea(n.id)?.path || "");
      if (n.kind === "EvidenceResult") {
        return notebookHref(notebookForEvidence(n.id)?.path || "");
      }
      if (selectedOutcome.value?.id) return notebookHref(notebookForEvidence(selectedOutcome.value.id)?.path || "");
      return "";
    });
    const selectedNotebookVisualKind = computed(() => {
      const kind = selectedNode.value?.kind;
      return kind === "EvidenceResult" || kind === "Conclusion" ? "statistical" : "graphic";
    });
    const selectedNotebookVisualTitle = computed(() => notebookVisualSpec(selectedNotebookVisualKind.value).title);
    const selectedGraphicAbstract = ref({ state: "idle", src: "", alt: "", href: "" });
    const selectedPreviewHref = computed(() => notebookVisualHref(selectedNotebookHref.value, selectedNotebookVisualKind.value));
    watch([selectedNotebookHref, selectedNotebookVisualKind], () => {
      selectedNotebookPreviewOpen.value = false;
      graphicAbstractDialogOpen.value = false;
      closeNotebookPreviewImage();
    });
    let graphicAbstractRequestId = 0;
    watch([selectedNotebookHref, selectedNotebookVisualKind], async ([href, visualKind]) => {
      const requestId = ++graphicAbstractRequestId;
      if (!href) {
        selectedGraphicAbstract.value = { state: "idle", src: "", alt: "", href: "" };
        return;
      }
      const cacheKey = `${visualKind}:${href}`;
      const visualHref = notebookVisualHref(href, visualKind);
      if (graphicAbstractCache.has(cacheKey)) {
        selectedGraphicAbstract.value = graphicAbstractCache.get(cacheKey);
        return;
      }
      selectedGraphicAbstract.value = { state: "loading", src: "", alt: "", href: visualHref };
      try {
        const response = await fetch(href, { cache: "no-store" });
        if (!response.ok) throw new Error(`Notebook preview fetch failed: ${response.status}`);
        const html = await response.text();
        const abstract = extractNotebookVisual(html, href, visualKind);
        const next = abstract
          ? { state: "loaded", href: visualHref, ...abstract }
          : { state: "missing", src: "", alt: "", href: visualHref };
        graphicAbstractCache.set(cacheKey, next);
        if (requestId === graphicAbstractRequestId) selectedGraphicAbstract.value = next;
      } catch {
        const next = { state: "error", src: "", alt: "", href: visualHref };
        graphicAbstractCache.set(cacheKey, next);
        if (requestId === graphicAbstractRequestId) selectedGraphicAbstract.value = next;
      }
    }, { immediate: true });
    const activeIds = computed(() => {
      const ids = new Set([...selectedPathList.value, ...hoveredPathIds.value, selectedId.value]);
      if (hoveredId.value) ids.add(hoveredId.value);
      return ids;
    });
    const activeUids = computed(() => {
      const selectedPath = selectedUidExists.value
        ? visualPathUidsForUid(selectedUid.value)
        : visualPathUidsForNodePath(selectedPathList.value);
      const hoveredPath = hoveredUidExists.value
        ? visualPathUidsForUid(hoveredUid.value)
        : visualPathUidsForNodePath(hoveredId.value ? (findEntryPath(model.value.root, hoveredId.value) || []) : []);
      const uids = new Set([...selectedPath, ...hoveredPath]);
      const selectedItem = selectedUidExists.value
        ? tree.value.nodes.find((item) => item.uid === selectedUid.value)
        : tree.value.byNodeId.get(selectedId.value);
      const hoveredItem = hoveredUidExists.value
        ? tree.value.nodes.find((item) => item.uid === hoveredUid.value)
        : tree.value.byNodeId.get(hoveredId.value);
      if (selectedItem) uids.add(selectedItem.uid);
      if (hoveredItem) uids.add(hoveredItem.uid);
      return uids;
    });
    const focusActive = computed(() => !globalView.value && (Boolean(hoveredId.value) || selectedId.value !== cdataNode.id));

    function visualUidForNode(id) {
      return tree.value.nodes.find((item) => item.node.id === id)?.uid || "";
    }

    function visualPathIdsForUid(uid) {
      return visualPathItemsForUid(uid).map((item) => item.node.id);
    }

    function visualPathUidsForUid(uid) {
      return visualPathItemsForUid(uid).map((item) => item.uid);
    }

    function visualPathUidsForNodePath(pathIds) {
      const uids = [];
      let parentUid = "";
      for (const id of pathIds || []) {
        const item = tree.value.nodes.find((candidate) => (
          candidate.node.id === id && (!parentUid || candidate.parent?.uid === parentUid)
        )) || tree.value.nodes.find((candidate) => candidate.node.id === id);
        if (!item) continue;
        uids.push(item.uid);
        parentUid = item.uid;
      }
      return uids;
    }

    function visualPathItemsForUid(uid) {
      const item = tree.value.nodes.find((candidate) => candidate.uid === uid);
      if (!item) return [];
      const path = [];
      let cursor = item;
      while (cursor) {
        path.unshift(cursor);
        cursor = cursor.parent;
      }
      return path;
    }

    function isSelectedItem(item) {
      if (selectedUidExists.value) return item.uid === selectedUid.value;
      return item.node.id === selectedId.value;
    }

    function isHoveredItem(item) {
      if (hoveredUidExists.value) return item.uid === hoveredUid.value;
      return item.node.id === hoveredId.value;
    }

    function preserveViewport(snapshot) {
      if (!snapshot || !viewportPinned.value) return;
      nextTick(() => {
        setView(snapshot);
        window.requestAnimationFrame?.(() => setView(snapshot));
        window.setTimeout(() => setView(snapshot), 80);
      });
    }

    function selectNode(id, uid = "") {
      const snapshot = safeView.value;
      const shouldPreserveViewport = globalView.value && viewportPinned.value;
      selectedId.value = id;
      selectedUid.value = uid || visualUidForNode(id);
      inspectorOpen.value = true;
      if (!globalView.value) {
        const path = findEntryPath(model.value.root, id);
        if (path) {
          const next = new Set(expandedIds.value);
          for (const parentId of path.slice(0, -1)) next.add(parentId);
          const entry = findEntryById(model.value.root, id);
          if (entry?.children?.length) next.add(id);
          expandedIds.value = next;
        }
      }
      if (shouldPreserveViewport) preserveViewport(snapshot);
    }

    function findEntryById(entry, id) {
      if (entry?.node?.id === id) return entry;
      for (const child of entry.children || []) {
        const found = findEntryById(child, id);
        if (found) return found;
      }
      return null;
    }

    function toggleBranch(id) {
      globalView.value = false;
      const next = new Set(expandedIds.value);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      next.add(cdataNode.id);
      expandedIds.value = next;
      selectedId.value = id;
      selectedUid.value = visualUidForNode(id);
      inspectorOpen.value = true;
    }

    function hoverNode(id, uid = "") {
      hoveredId.value = id;
      hoveredUid.value = uid || visualUidForNode(id);
    }

    function clearHover() {
      hoveredId.value = "";
      hoveredUid.value = "";
    }

    function collapseAll() {
      globalView.value = false;
      const path = findEntryPath(model.value.root, selectedId.value) || [cdataNode.id];
      expandedIds.value = new Set([cdataNode.id, ...path.slice(0, -1)]);
      nextTick(fitTree);
    }

    function toggleFocusMode() {
      focusMode.value = !focusMode.value;
      nextTick(() => {
        measurePlot();
        fitTree();
      });
    }

    function toggleTheme() {
      themeMode.value = darkMode.value ? "light" : "dark";
    }

    function toggleSpotlight() {
      spotlightMode.value = !spotlightMode.value;
      if (spotlightMode.value) globalView.value = false;
      nextTick(fitTree);
    }

    function showContext() {
      spotlightMode.value = false;
      globalView.value = true;
      nextTick(fitTree);
    }

    function showGlobalView() {
      spotlightMode.value = false;
      globalView.value = true;
      nextTick(fitTree);
    }

    function statusCount(status) {
      return statusCounts.value[status] || 0;
    }

    function ideaMeta(idea) {
      const ev = evidenceForIdea(idea.id);
      const parts = [];
      if (idea.signature?.parameter_family) parts.push(idea.signature.parameter_family);
      if (ev?.p_value !== undefined && ev?.p_value !== null) parts.push(`p=${formatNumber(ev.p_value)}`);
      if (directionLabel(idea)) parts.push(truncate(directionLabel(idea), 34));
      const run = runForIdea(idea.id);
      if (run) parts.push(runOrder(run) > 1 ? `Round ${runOrder(run)}` : "Round 1");
      return parts.filter(Boolean).join(" | ");
    }

    function nodeTitleLines(item) {
      const text = item.node.kind === "EvidenceResult" || item.node.kind === "Conclusion"
        ? item.node.hypothesis_status || "Conclusion"
        : label(item.node);
      return svgLines(text, compactLabels.value ? 24 : 28, 2);
    }

    function nodeClass(item) {
      return [
        "tree-node",
        item.node.kind.toLowerCase(),
        `status-${statusClass(nodeBadge(item)?.status || item.node.hypothesis_status || "")}`,
        isSelectedItem(item) ? "selected" : "",
        isHoveredItem(item) ? "hovered" : "",
        activeUids.value.has(item.uid) ? "active" : "",
        focusActive.value && !activeUids.value.has(item.uid) ? "dimmed" : ""
      ].filter(Boolean).join(" ");
    }

    function edgeClass(link) {
      const active = activeUids.value.has(link.source.uid) && activeUids.value.has(link.target.uid);
      const lineage = selectedEdgeKeys.value.has(edgeKey(link));
      const dimmed = focusActive.value && !active;
      return ["tree-edge", link.role, lineage ? "lineage-edge" : "", active ? "active" : "", dimmed ? "dimmed" : ""].filter(Boolean).join(" ");
    }

    function edgeMarker(link) {
      if (globalView.value || safeView.value.k < 0.62) return null;
      const active = activeUids.value.has(link.source.uid) && activeUids.value.has(link.target.uid);
      if (active || selectedEdgeKeys.value.has(edgeKey(link))) return "url(#edge-arrow-active)";
      if (link.role === "direction" || link.role === "run-direction") return "url(#edge-arrow-direction)";
      return null;
    }

    function edgeLabelVisible(link) {
      if (globalView.value) return false;
      return selectedEdgeKeys.value.has(edgeKey(link)) || (focusActive.value && activeUids.value.has(link.source.uid) && activeUids.value.has(link.target.uid));
    }

    function edgeKey(link) {
      return `${link.source.uid}->${link.target.uid}`;
    }

    function edgePath(link) {
      const a = link.source;
      const b = link.target;
      if (globalView.value) {
        const x1 = a.x;
        const y1 = a.y;
        const x2 = b.x;
        const y2 = b.y;
        if (layoutDirection.value === "horizontal") {
          const dx = x2 - x1;
          if (Math.abs(dx) < 3) {
            const bow = Math.min(90, Math.max(18, Math.abs(y2 - y1) * 0.18));
            return `M ${x1} ${y1} C ${x1 - bow} ${y1} ${x2 - bow} ${y2} ${x2} ${y2}`;
          }
          const c1x = x1 + dx * 0.42;
          const c2x = x1 + dx * 0.58;
          return `M ${x1} ${y1} C ${c1x} ${y1} ${c2x} ${y2} ${x2} ${y2}`;
        }
        const dy = y2 - y1;
        if (Math.abs(dy) < 3) {
          const bow = Math.min(90, Math.max(18, Math.abs(x2 - x1) * 0.18));
          return `M ${x1} ${y1} C ${x1} ${y1 - bow} ${x2} ${y2 - bow} ${x2} ${y2}`;
        }
        const c1y = y1 + dy * 0.42;
        const c2y = y1 + dy * 0.58;
        return `M ${x1} ${y1} C ${x1} ${c1y} ${x2} ${c2y} ${x2} ${y2}`;
      }
      if (layoutDirection.value === "horizontal") {
        const x1 = a.x + nodeWidth(a) / 2 + 8;
        const y1 = a.y;
        const x2 = b.x - nodeWidth(b) / 2 - 8;
        const y2 = b.y;
        const midX = x1 + Math.max(38, (x2 - x1) * 0.52);
        const dy = y2 - y1;
        const turn = Math.min(18, Math.abs(dy) / 2);
        if (Math.abs(dy) < 2) return `M ${x1} ${y1} L ${x2} ${y2}`;
        const sy = dy > 0 ? 1 : -1;
        return [
          `M ${x1} ${y1}`,
          `L ${midX - turn} ${y1}`,
          `Q ${midX} ${y1} ${midX} ${y1 + sy * turn}`,
          `L ${midX} ${y2 - sy * turn}`,
          `Q ${midX} ${y2} ${midX + turn} ${y2}`,
          `L ${x2} ${y2}`
        ].join(" ");
      }
      const x1 = a.x;
      const y1 = a.y + nodeHeight(a) / 2 + 8;
      const x2 = b.x;
      const y2 = b.y - nodeHeight(b) / 2 - 8;
      const midY = y1 + Math.max(28, (y2 - y1) * 0.52);
      const dx = x2 - x1;
      const turn = Math.min(18, Math.abs(dx) / 2);
      if (Math.abs(dx) < 2) return `M ${x1} ${y1} L ${x2} ${y2}`;
      const sx = dx > 0 ? 1 : -1;
      return [
        `M ${x1} ${y1}`,
        `L ${x1} ${midY - turn}`,
        `Q ${x1} ${midY} ${x1 + sx * turn} ${midY}`,
        `L ${x2 - sx * turn} ${midY}`,
        `Q ${x2} ${midY} ${x2} ${midY + turn}`,
        `L ${x2} ${y2}`
      ].join(" ");
    }

    function minimapX(x) {
      return minimap.value.offsetX + x * minimap.value.scale;
    }

    function minimapY(y) {
      return minimap.value.offsetY + y * minimap.value.scale;
    }

    function minimapEdgePath(link) {
      const x1 = minimapX(link.source.x);
      const y1 = minimapY(link.source.y);
      const x2 = minimapX(link.target.x);
      const y2 = minimapY(link.target.y);
      if (layoutDirection.value === "horizontal") {
        const midX = x1 + (x2 - x1) * 0.52;
        const dy = y2 - y1;
        if (Math.abs(dy) < 1) return `M ${x1} ${y1} L ${x2} ${y2}`;
        const turn = Math.min(8, Math.abs(dy) / 2);
        const sy = dy > 0 ? 1 : -1;
        return `M ${x1} ${y1} L ${midX - turn} ${y1} Q ${midX} ${y1} ${midX} ${y1 + sy * turn} L ${midX} ${y2 - sy * turn} Q ${midX} ${y2} ${midX + turn} ${y2} L ${x2} ${y2}`;
      }
      const midY = y1 + (y2 - y1) * 0.52;
      const dx = x2 - x1;
      if (Math.abs(dx) < 1) return `M ${x1} ${y1} L ${x2} ${y2}`;
      const turn = Math.min(8, Math.abs(dx) / 2);
      const sx = dx > 0 ? 1 : -1;
      return `M ${x1} ${y1} L ${x1} ${midY - turn} Q ${x1} ${midY} ${x1 + sx * turn} ${midY} L ${x2 - sx * turn} ${midY} Q ${x2} ${midY} ${x2} ${midY + turn} L ${x2} ${y2}`;
    }

    function onMinimapClick(event) {
      const rect = event.currentTarget.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      if (!Number.isFinite(minimap.value.scale) || minimap.value.scale <= 0) return;
      viewportPinned.value = true;
      const x = (event.clientX - rect.left) * (MINIMAP_WIDTH / rect.width);
      const y = (event.clientY - rect.top) * (MINIMAP_HEIGHT / rect.height);
      const worldX = (x - minimap.value.offsetX) / minimap.value.scale;
      const worldY = (y - minimap.value.offsetY) / minimap.value.scale;
      const v = safeView.value;
      setView({
        ...v,
        x: finiteNumber(plotSize.value.width, 1200) / 2 - worldX * v.k,
        y: finiteNumber(plotSize.value.height, 720) / 2 - worldY * v.k
      });
    }

    function fitRoot() {
      viewportPinned.value = false;
      nextTick(() => {
        centerOnItem(tree.value.root, 0.92, { yOffset: 92 });
      });
    }

    function fitTree(options = {}) {
      if (!options.preserveUserView) viewportPinned.value = false;
      const bounds = treeBounds();
      const w = Math.max(1, finiteNumber(plotSize.value.width, 1200));
      const h = Math.max(1, finiteNumber(plotSize.value.height, 720));
      const readableFit = layoutDirection.value === "horizontal"
        ? (h - 86) / bounds.height
        : (w - 86) / bounds.width;
      const fullFit = Math.min((w - 86) / bounds.width, (h - 96) / bounds.height);
      const k = globalView.value
        ? clamp(fullFit, MIN_ZOOM, 1.0)
        : clamp(readableFit, 0.68, 1.02);
      setView({
        k,
        x: globalView.value || layoutDirection.value !== "horizontal"
          ? (w - bounds.width * k) / 2 - bounds.minX * k
          : 88 - bounds.minX * k,
        y: globalView.value || layoutDirection.value === "horizontal"
          ? (h - bounds.height * k) / 2 - bounds.minY * k
          : 88 - bounds.minY * k
      });
    }

    function fitOverview() {
      viewportPinned.value = false;
      const bounds = treeBounds();
      const w = Math.max(1, finiteNumber(plotSize.value.width, 1200));
      const h = Math.max(1, finiteNumber(plotSize.value.height, 720));
      const k = clamp(Math.min((w - 80) / bounds.width, (h - 90) / bounds.height), MIN_ZOOM, 1.15);
      setView({
        k,
        x: (w - bounds.width * k) / 2 - bounds.minX * k,
        y: (h - bounds.height * k) / 2 - bounds.minY * k
      });
    }

    function focusSelected() {
      viewportPinned.value = false;
      const item = tree.value.byNodeId.get(selectedId.value) || tree.value.root;
      centerOnItem(item, Math.max(safeView.value.k, 0.82), { yOffset: finiteNumber(plotSize.value.height, 720) * 0.36 });
    }

    function centerOnItem(item, zoom = safeView.value.k, options = {}) {
      if (!item) return;
      const k = clamp(zoom, MIN_ZOOM, MAX_ZOOM);
      const plotWidth = finiteNumber(plotSize.value.width, 1200);
      const plotHeight = finiteNumber(plotSize.value.height, 720);
      const yOffset = options.yOffset ?? plotHeight / 2;
      setView({
        k,
        x: plotWidth / 2 - item.x * k,
        y: yOffset - item.y * k
      });
    }

    function treeBounds() {
      const xs = tree.value.nodes
        .flatMap((item) => [item.x - nodeWidth(item) / 2, item.x + nodeWidth(item) / 2])
        .filter(Number.isFinite);
      const ys = tree.value.nodes
        .flatMap((item) => [item.y - nodeHeight(item) / 2, item.y + nodeHeight(item) / 2])
        .filter(Number.isFinite);
      if (!xs.length || !ys.length) {
        return { minX: 0, maxX: 1, minY: 0, maxY: 1, width: 1, height: 1 };
      }
      const minX = Math.min(...xs, 0);
      const maxX = Math.max(...xs, 1);
      const minY = Math.min(...ys, 0);
      const maxY = Math.max(...ys, 1);
      return {
        minX,
        maxX,
        minY,
        maxY,
        width: Math.max(1, maxX - minX),
        height: Math.max(1, maxY - minY)
      };
    }

    function finiteNumber(value, fallback = 0) {
      const n = Number(value);
      return Number.isFinite(n) ? n : fallback;
    }

    function clamp(value, min, max, fallback = min) {
      const n = finiteNumber(value, fallback);
      return Math.min(max, Math.max(min, n));
    }

    function sanitizeViewport(next = {}, fallback = view.value || {}) {
      const fallbackK = clamp(fallback.k, MIN_ZOOM, MAX_ZOOM, 0.92);
      return {
        x: finiteNumber(next.x, finiteNumber(fallback.x, 0)),
        y: finiteNumber(next.y, finiteNumber(fallback.y, 0)),
        k: clamp(next.k, MIN_ZOOM, MAX_ZOOM, fallbackK)
      };
    }

    function setView(next) {
      view.value = sanitizeViewport(next);
    }

    function zoomBy(multiplier, origin = null) {
      viewportPinned.value = true;
      const old = safeView.value;
      const nextK = clamp(old.k * finiteNumber(multiplier, 1), MIN_ZOOM, MAX_ZOOM, old.k);
      const point = origin || { x: finiteNumber(plotSize.value.width, 1200) / 2, y: finiteNumber(plotSize.value.height, 720) / 2 };
      const worldX = (point.x - old.x) / old.k;
      const worldY = (point.y - old.y) / old.k;
      setView({
        k: nextK,
        x: point.x - worldX * nextK,
        y: point.y - worldY * nextK
      });
    }

    function zoomIn() {
      zoomBy(1.18);
    }

    function zoomOut() {
      zoomBy(1 / 1.18);
    }

    function normalizedWheel(event) {
      const lineHeight = 16;
      const pageHeight = Math.max(1, finiteNumber(plotSize.value.height, 720));
      const scale = event.deltaMode === 1 ? lineHeight : event.deltaMode === 2 ? pageHeight : 1;
      return {
        x: finiteNumber(event.deltaX, 0) * scale,
        y: finiteNumber(event.deltaY, 0) * scale
      };
    }

    function onWheel(event) {
      const rect = plotRef.value?.getBoundingClientRect();
      if (!rect) return;
      event.preventDefault();
      viewportPinned.value = true;
      const origin = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      const delta = normalizedWheel(event);
      const wantsZoom = event.ctrlKey || event.metaKey || event.altKey;
      if (wantsZoom) {
        const zoomDelta = clamp(delta.y, -120, 120);
        zoomBy(Math.exp(-zoomDelta * 0.0045), origin);
        return;
      }
      const dx = event.shiftKey && Math.abs(delta.x) < 0.5 ? delta.y : delta.x;
      const dy = event.shiftKey && Math.abs(delta.x) < 0.5 ? 0 : delta.y;
      const v = safeView.value;
      setView({
        ...v,
        x: v.x - clamp(dx, -220, 220, 0),
        y: v.y - clamp(dy, -220, 220, 0)
      });
    }

    function startPan(event) {
      viewportPinned.value = true;
      dragging.value = {
        pointerId: event.pointerId,
        x: finiteNumber(event.clientX, 0),
        y: finiteNumber(event.clientY, 0),
        view: { ...safeView.value }
      };
      event.currentTarget.setPointerCapture?.(event.pointerId);
    }

    function onPointerMove(event) {
      if (!dragging.value) return;
      const start = dragging.value;
      setView({
        ...start.view,
        x: start.view.x + finiteNumber(event.clientX, start.x) - start.x,
        y: start.view.y + finiteNumber(event.clientY, start.y) - start.y
      });
    }

    function endPan() {
      dragging.value = null;
    }

    function startPanelResize(panel, event) {
      if (!event) return;
      event.preventDefault();
      event.stopPropagation();
      const startX = finiteNumber(event.clientX, 0);
      const startSidebar = sidebarWidth.value;
      const startInspector = inspectorWidth.value;
      const minSidebar = 220;
      const maxSidebar = 430;
      const minInspector = 300;
      const maxInspector = 620;
      const move = (moveEvent) => {
        const delta = finiteNumber(moveEvent.clientX, startX) - startX;
        if (panel === "sidebar") {
          sidebarWidth.value = clamp(startSidebar + delta, minSidebar, maxSidebar);
        } else {
          inspectorWidth.value = clamp(startInspector - delta, minInspector, maxInspector);
        }
        nextTick(measurePlot);
      };
      const up = () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        document.body.classList.remove("is-resizing-panel");
        panelResize.value = null;
        nextTick(() => {
          measurePlot();
          if (globalView.value && !viewportPinned.value) fitTree();
        });
      };
      panelResize.value = { panel, move, up };
      document.body.classList.add("is-resizing-panel");
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    }

    function openNotebookPreviewImage(src, alt = "") {
      if (!src) return;
      notebookPreviewImage.value = { open: true, src, alt };
    }

    function closeNotebookPreviewImage() {
      notebookPreviewImage.value = { open: false, src: "", alt: "" };
    }

    function prepareNotebookPreviewFrame(event) {
      const frame = event?.target;
      const doc = frame?.contentDocument;
      if (!doc) return;
      let frameHref = window.location.href;
      try {
        frameHref = frame.contentWindow?.location?.href
          || new URL(frame.getAttribute("src") || selectedPreviewHref.value || "", window.location.href).toString();
      } catch {
        frameHref = window.location.href;
      }
      for (const img of doc.querySelectorAll("img")) {
        if (!img.getAttribute("src")) continue;
        img.style.cursor = "zoom-in";
        img.title = img.title || "Click to enlarge";
        img.addEventListener("click", (clickEvent) => {
          clickEvent.preventDefault();
          clickEvent.stopPropagation();
          const rawSrc = img.getAttribute("src") || "";
          let src = rawSrc;
          if (!rawSrc.startsWith("data:") && !/^https?:\/\//.test(rawSrc)) {
            try {
              src = new URL(rawSrc, frameHref).toString();
            } catch {
              src = rawSrc;
            }
          }
          openNotebookPreviewImage(src, img.getAttribute("alt") || "");
        });
      }
    }

    function measurePlot() {
      const rect = plotRef.value?.getBoundingClientRect();
      if (!rect) return false;
      const nextWidth = finiteNumber(Math.floor(rect.width), plotSize.value.width || 1200);
      const nextHeight = finiteNumber(Math.floor(rect.height), plotSize.value.height || 720);
      const width = Math.max(640, nextWidth);
      const height = Math.max(420, nextHeight);
      const changed = Math.abs(width - plotSize.value.width) > 1 || Math.abs(height - plotSize.value.height) > 1;
      plotSize.value = {
        width,
        height
      };
      return changed;
    }

    onMounted(() => {
      nextTick(() => {
        measurePlot();
        fitTree();
        if (window.ResizeObserver && plotRef.value) {
          resizeObserver = new ResizeObserver(() => {
            const changed = measurePlot();
            if (changed && globalView.value && !viewportPinned.value) nextTick(fitTree);
          });
          resizeObserver.observe(plotRef.value);
        }
      });
    });

    onBeforeUnmount(() => {
      resizeObserver?.disconnect();
      if (panelResize.value) {
        window.removeEventListener("pointermove", panelResize.value.move);
        window.removeEventListener("pointerup", panelResize.value.up);
        document.body.classList.remove("is-resizing-panel");
      }
    });

    watch([query, statusFilter, spotlightMode, globalView], () => {
      nextTick(() => {
        fitTree();
      });
    });
    watch(themeMode, applyThemeMode, { immediate: true });

    return {
      title,
      darkMode,
      toggleTheme,
      summary,
      query,
      statusFilter,
      statusFilters,
      selectedId,
      hoveredId,
      compactLabels,
      spotlightMode,
      spotlightActive,
      globalView,
      layoutDirection,
      focusMode,
      sidebarOpen,
      inspectorOpen,
      selectedNotebookPreviewOpen,
      graphicAbstractDialogOpen,
      notebookPreviewImage,
      workspaceStyle,
      isHorizontal,
      overviewZoom,
      zoomPercent,
      globalDotScale,
      globalLabelScale,
      selectionRingRadius,
      plotRef,
      plotSize,
      view,
      stats,
      statusCount,
      evidenceStatusItems,
      shownCount,
      graphSubtitle,
      hiddenBySpotlight,
      visibleIdeas,
      tree,
      laneGuides,
      minimap,
      activeIds,
      activeUids,
      selectedPathNodes,
      viewportTransform,
      selectedNode,
      selectedStatus,
      selectedSummary,
      selectedOutcome,
      selectedEvidenceId,
      selectedIdeaId,
      selectedRows,
      technicalRowsForSelected,
      selectedQuickFacts,
      selectedNotebookHref,
      selectedPreviewHref,
      selectedNotebookVisualTitle,
      selectedGraphicAbstract,
      label,
      truncate,
      formatNumber,
      displayKind,
      statusForIdea,
      ideaMeta,
      statusClass,
      valueLines,
      nodeWidth,
      nodeHeight,
      nodeColor,
      nodeAccentColor,
      nodeMetaLabel,
      nodeBadge,
      nodeBadgeWidth,
      childSummary,
      nodeTitleText,
      nodeTokens,
      nodeCardClasses,
      nodeTitleLines,
      globalNodeRadius,
      globalLabelWidth,
      globalTitleLines,
      globalShortLabelLines,
      globalMetaText,
      nodeClass,
      edgeClass,
      edgeMarker,
      edgeLabel,
      edgeLabelWidth,
      edgeLabelTransform,
      edgeLabelVisible,
      edgePath,
      isSelectedItem,
      isHoveredItem,
      minimapX,
      minimapY,
      minimapEdgePath,
      onMinimapClick,
      selectNode,
      toggleBranch,
      toggleFocusMode,
      toggleSpotlight,
      showContext,
      showGlobalView,
      hoverNode,
      clearHover,
      collapseAll,
      fitRoot,
      fitTree,
      fitOverview,
      focusSelected,
      zoomIn,
      zoomOut,
      onWheel,
      startPan,
      onPointerMove,
      endPan
      ,
      startPanelResize,
      prepareNotebookPreviewFrame,
      closeNotebookPreviewImage
    };
  }
};

createApp(App).mount("#uchrom-idea-graph-app");
