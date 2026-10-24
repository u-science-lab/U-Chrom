const DEFAULT_ATLAS_ORIGIN = "https://uchrom-atlas.u-science.org";
const DEFAULT_HOSTED_ORIGIN = "https://uchrom-browser.u-science.org";
const DEFAULT_CATALOG_URL = "https://uchrom-atlas-r2.u-science.org/catalog.json";
const DEFAULT_DATA_ROOT = "https://uchrom-atlas-r2.u-science.org";

export const HANDOFF_TTL_MS = 10 * 60 * 1000;
export const HANDOFF_MAX_BYTES = 1024 * 1024;
const MAX_QUESTION_LENGTH = 4000;

export interface HandoffEnv {
	HANDOFFS: DurableObjectNamespace;
	ATLAS_ORIGIN?: string;
	HOSTED_ORIGIN?: string;
	ATLAS_CATALOG_URL?: string;
	ATLAS_DATA_ROOT?: string;
	fetch?: typeof fetch;
}

export interface HandoffPayload {
	version: 1;
	issued_at: string;
	expires_at: string;
	dataset: { id: string; url: string; version: string };
	question?: string;
	page_state?: Record<string, unknown>;
}

interface Catalog {
	version?: string | number;
	updated?: string;
	datasets?: Array<{ id?: string; path?: string }>;
}

class HandoffError extends Error {
	constructor(readonly status: number, message: string) {
		super(message);
	}
}

export function isAllowedOrigin(origin: string | null, env: HandoffEnv): boolean {
	return origin !== null && (origin === (env.ATLAS_ORIGIN ?? DEFAULT_ATLAS_ORIGIN) ||
		origin === (env.HOSTED_ORIGIN ?? DEFAULT_HOSTED_ORIGIN));
}

export function datasetFromCatalog(catalog: Catalog, id: string, dataRoot: string, etag?: string | null) {
	if (!Array.isArray(catalog.datasets)) return null;
	const entry = catalog.datasets.find((dataset) => dataset.id === id);
	if (!entry || typeof entry.path !== "string" || !isSafeCatalogPath(entry.path)) return null;
	const version = catalog.updated || etag?.replace(/^W\//, "").replace(/^"|"$/g, "") ||
		(catalog.version === undefined ? "unknown" : String(catalog.version));
	return {
		id: entry.id!,
		url: `${dataRoot.replace(/\/+$/, "")}/${entry.path}`,
		version,
	};
}

function isSafeCatalogPath(path: string): boolean {
	if (!path || path.startsWith("/") || path.includes("\\") || path.includes("?") || path.includes("#")) return false;
	try {
		const decoded = decodeURIComponent(path);
		return decoded.split("/").every((part) => part !== "" && part !== "." && part !== "..") &&
			!decoded.includes("\\") && !decoded.startsWith("/") &&
			new URL(path, `${DEFAULT_DATA_ROOT}/`).origin === new URL(DEFAULT_DATA_ROOT).origin;
	} catch {
		return false;
	}
}

export function createPayload(
	input: { dataset: HandoffPayload["dataset"]; question?: string; pageState?: Record<string, unknown> },
	now = Date.now(),
	maxBytes = HANDOFF_MAX_BYTES,
): HandoffPayload {
	const issuedAt = new Date(now).toISOString();
	const payload: HandoffPayload = {
		version: 1,
		issued_at: issuedAt,
		expires_at: new Date(now + HANDOFF_TTL_MS).toISOString(),
		dataset: input.dataset,
	};
	if (input.question !== undefined) payload.question = input.question;
	if (input.pageState !== undefined) payload.page_state = input.pageState;
	if (new TextEncoder().encode(JSON.stringify(payload)).byteLength > maxBytes) {
		throw new HandoffError(413, "handoff payload exceeds the 1 MiB limit");
	}
	return payload;
}

function jsonResponse(value: unknown, status: number, origin?: string | null): Response {
	const headers = new Headers({ "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
	if (origin) {
		headers.set("Access-Control-Allow-Origin", origin);
		headers.set("Access-Control-Allow-Methods", "POST, OPTIONS");
		headers.set("Access-Control-Allow-Headers", "Content-Type");
		headers.set("Vary", "Origin");
	}
	return new Response(JSON.stringify(value), { status, headers });
}

async function readJson(request: Request, maxBytes: number): Promise<Record<string, unknown>> {
	const contentLength = request.headers.get("Content-Length");
	if (contentLength && (!/^\d+$/.test(contentLength) || Number(contentLength) > maxBytes)) {
		throw new HandoffError(413, "request body exceeds the 1 MiB limit");
	}
	if (!request.body) throw new HandoffError(400, "a JSON request body is required");
	const reader = request.body.getReader();
	const chunks: Uint8Array[] = [];
	let size = 0;
	try {
		while (true) {
			const { done, value } = await reader.read();
			if (done) break;
			size += value.byteLength;
			if (size > maxBytes) {
				await reader.cancel();
				throw new HandoffError(413, "request body exceeds the 1 MiB limit");
			}
			chunks.push(value);
		}
	} finally {
		reader.releaseLock();
	}
	let parsed: unknown;
	try {
		const bytes = new Uint8Array(size);
		let offset = 0;
		for (const chunk of chunks) {
			bytes.set(chunk, offset);
			offset += chunk.byteLength;
		}
		parsed = JSON.parse(new TextDecoder("utf-8", { fatal: true, ignoreBOM: false }).decode(bytes));
	} catch {
		throw new HandoffError(400, "request body must be valid JSON");
	}
	if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
		throw new HandoffError(400, "request body must be a JSON object");
	}
	return parsed as Record<string, unknown>;
}

function randomToken(): string {
	const bytes = crypto.getRandomValues(new Uint8Array(32));
	return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function objectForToken(token: string, env: HandoffEnv): Promise<{
	object: DurableObjectStub; tokenHash: string;
}> {
	const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
	const bytes = new Uint8Array(digest);
	const tokenHash = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
	const shard = String(bytes[0] % 32).padStart(2, "0");
	return { object: env.HANDOFFS.get(env.HANDOFFS.idFromName(`handoff-${shard}`)), tokenHash };
}

async function createHandoff(request: Request, env: HandoffEnv, origin: string): Promise<Response> {
	const input = await readJson(request, HANDOFF_MAX_BYTES);
	if (Object.keys(input).some((key) => !["dataset_id", "question", "page_state"].includes(key))) {
		throw new HandoffError(400, "unsupported handoff field");
	}
	if (typeof input.dataset_id !== "string" || input.dataset_id.length < 1 || input.dataset_id.length > 200) {
		throw new HandoffError(400, "dataset_id must be a non-empty catalog ID");
	}
	const hostedOrigin = env.HOSTED_ORIGIN ?? DEFAULT_HOSTED_ORIGIN;
	if (origin === (env.ATLAS_ORIGIN ?? DEFAULT_ATLAS_ORIGIN) && input.page_state !== undefined) {
		throw new HandoffError(400, "Atlas handoffs cannot include page_state");
	}
	if (input.page_state !== undefined &&
		(!input.page_state || typeof input.page_state !== "object" || Array.isArray(input.page_state))) {
		throw new HandoffError(400, "page_state must be a JSON object");
	}
	if (input.page_state !== undefined && origin !== hostedOrigin) {
		throw new HandoffError(400, "this origin cannot include page_state");
	}
	if (input.question !== undefined &&
		(typeof input.question !== "string" || input.question.length > MAX_QUESTION_LENGTH)) {
		throw new HandoffError(400, `question must be a string of at most ${MAX_QUESTION_LENGTH} characters`);
	}
	const fetcher = env.fetch ?? fetch;
	let response: Response;
	try {
		response = await fetcher(env.ATLAS_CATALOG_URL ?? DEFAULT_CATALOG_URL, {
			headers: { Accept: "application/json" },
			signal: AbortSignal.timeout(5000),
		});
	} catch {
		throw new HandoffError(503, "Atlas catalog is temporarily unavailable");
	}
	if (!response.ok) throw new HandoffError(503, "Atlas catalog is temporarily unavailable");
	let catalog: Catalog;
	try {
		catalog = await response.json() as Catalog;
	} catch {
		throw new HandoffError(503, "Atlas catalog is temporarily unavailable");
	}
	const dataset = datasetFromCatalog(catalog, input.dataset_id, env.ATLAS_DATA_ROOT ?? DEFAULT_DATA_ROOT,
		response.headers.get("ETag"));
	if (!dataset) throw new HandoffError(404, "dataset_id is not present in the Atlas catalog");
	const payload = createPayload({
		dataset,
		...(input.question === undefined ? {} : { question: input.question as string }),
		...(input.page_state === undefined ? {} : { pageState: input.page_state as Record<string, unknown> }),
	});
	const token = randomToken();
	const { object: handoff, tokenHash } = await objectForToken(token, env);
	const stored = await handoff.fetch("https://handoff.internal/store", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ tokenHash, payload }),
	});
	if (!stored.ok) throw new HandoffError(503, "handoff could not be stored");
	return jsonResponse({ token, expires_at: payload.expires_at }, 201, origin);
}

async function redeemHandoff(request: Request, env: HandoffEnv): Promise<Response> {
	if (new URL(request.url).search) throw new HandoffError(400, "redeem tokens must be sent in the JSON body");
	const input = await readJson(request, 256);
	if (Object.keys(input).some((key) => key !== "token") ||
		typeof input.token !== "string" || !/^[A-Za-z0-9_-]{43}$/.test(input.token)) {
		throw new HandoffError(400, "a valid handoff token is required in the JSON body");
	}
	const { object: handoff, tokenHash } = await objectForToken(input.token, env);
	const response = await handoff.fetch("https://handoff.internal/redeem", {
		method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tokenHash }),
	});
	if (!response.ok) return jsonResponse({ error: "handoff is invalid, expired, or already redeemed" }, 404);
	return new Response(response.body, {
		status: 200,
		headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
	});
}

export async function handleHandoff(request: Request, env: HandoffEnv): Promise<Response> {
	const url = new URL(request.url);
	const origin = request.headers.get("Origin");
	const isRedeem = url.pathname === "/api/agent/handoffs/redeem";
	if (url.pathname !== "/api/agent/handoffs" && !isRedeem) return jsonResponse({ error: "not found" }, 404);
	if (isRedeem) {
		if (request.method !== "POST") return jsonResponse({ error: "method not allowed" }, 405);
		try {
			return await redeemHandoff(request, env);
		} catch (error) {
			if (error instanceof HandoffError) return jsonResponse({ error: error.message }, error.status);
			return jsonResponse({ error: "handoff service is temporarily unavailable" }, 503);
		}
	}
	if (!isAllowedOrigin(origin, env)) return jsonResponse({ error: "origin is not allowed" }, 403);
	if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: {
		"Access-Control-Allow-Origin": origin!,
		"Access-Control-Allow-Methods": "POST, OPTIONS",
		"Access-Control-Allow-Headers": "Content-Type",
		"Access-Control-Max-Age": "600",
		"Vary": "Origin",
	} });
	if (request.method !== "POST") return jsonResponse({ error: "method not allowed" }, 405, origin);
	try {
		return await createHandoff(request, env, origin!);
	} catch (error) {
		if (error instanceof HandoffError) return jsonResponse({ error: error.message }, error.status, origin);
		console.error("handoff create failed", error);
		return jsonResponse({ error: "handoff service is temporarily unavailable" }, 503, origin);
	}
}

export async function routeHandoffRequest(
	request: Request,
	env: HandoffEnv,
	containerFetch: (request: Request) => Promise<Response>,
): Promise<Response> {
	const path = new URL(request.url).pathname;
	if (path === "/api/agent/handoffs" || path === "/api/agent/handoffs/redeem") {
		return handleHandoff(request, env);
	}
	if (path === "/api/agent" || path.startsWith("/api/agent/") ||
		path === "/api/control" || path.startsWith("/api/control/")) {
		return new Response("not found", { status: 404 });
	}
	return containerFetch(request);
}

export class UChromHandoff {
	private readonly sql: DurableObjectStorage["sql"];
	private readonly state: DurableObjectState;
	private readonly sqlReady: Promise<void>;

	constructor(state: DurableObjectState, _env: unknown) {
		this.state = state;
		this.sql = state.storage.sql;
		this.sqlReady = state.blockConcurrencyWhile(async () => {
			this.sql.exec("CREATE TABLE IF NOT EXISTS handoff (token_hash TEXT PRIMARY KEY, payload TEXT NOT NULL, expires_at INTEGER NOT NULL)");
		});
	}

	async fetch(request: Request): Promise<Response> {
		await this.sqlReady;
		const path = new URL(request.url).pathname;
		if (request.method === "POST" && path === "/store") {
			let body: unknown;
			try {
				body = await request.json();
			} catch {
				return new Response(null, { status: 400 });
			}
			if (!body || typeof body !== "object" || !("payload" in body) ||
				!("tokenHash" in body) || typeof body.tokenHash !== "string" || !/^[0-9a-f]{64}$/.test(body.tokenHash)) {
				return new Response(null, { status: 400 });
			}
			const { payload, tokenHash } = body as { payload: HandoffPayload; tokenHash: string };
			const expiresAt = Date.parse(payload.expires_at);
			if (!Number.isFinite(expiresAt) || expiresAt <= Date.now() || expiresAt > Date.now() + HANDOFF_TTL_MS + 1000) {
				return new Response(null, { status: 400 });
			}
			const serialized = JSON.stringify(payload);
			if (new TextEncoder().encode(serialized).byteLength > HANDOFF_MAX_BYTES) return new Response(null, { status: 413 });
			const result = this.sql.exec(
				"INSERT INTO handoff (token_hash, payload, expires_at) VALUES (?, ?, ?)", tokenHash, serialized, expiresAt,
			);
			if (result.rowsWritten !== 1) return new Response(null, { status: 409 });
			await this.state.storage.setAlarm(expiresAt);
			return new Response(null, { status: 201 });
		}
		if (request.method === "POST" && path === "/redeem") {
			let body: unknown;
			try {
				body = await request.json();
			} catch {
				return new Response(null, { status: 400 });
			}
			if (!body || typeof body !== "object" || !("tokenHash" in body) ||
				typeof body.tokenHash !== "string" || !/^[0-9a-f]{64}$/.test(body.tokenHash)) {
				return new Response(null, { status: 400 });
			}
			const rows = this.sql.exec<{ payload: string }>(
				"DELETE FROM handoff WHERE token_hash = ? AND expires_at > ? RETURNING payload", body.tokenHash, Date.now(),
			).toArray();
			if (rows.length !== 1) return new Response(null, { status: 404 });
			return new Response(rows[0].payload, { headers: { "Content-Type": "application/json; charset=utf-8" } });
		}
		return new Response(null, { status: 404 });
	}

	async alarm(): Promise<void> {
		this.sql.exec("DELETE FROM handoff WHERE expires_at <= ?", Date.now());
	}
}
