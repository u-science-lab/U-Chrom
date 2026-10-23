import { beforeEach, describe, expect, it, vi } from "vitest";
import {
	HANDOFF_TTL_MS,
	UChromHandoff,
	createPayload,
	datasetFromCatalog,
	handleHandoff,
	isAllowedOrigin,
	routeHandoffRequest,
	type HandoffEnv,
} from "./handoff";

const ATLAS_ORIGIN = "https://uchrom-atlas.u-science.org";
const HOSTED_ORIGIN = "https://uchrom-browser.u-science.org";
const DATA_ROOT = "https://uchrom-atlas-r2.u-science.org";
const catalog = {
	version: 1,
	updated: "2026-10-22T00:00:00Z",
	datasets: [{ id: "sample_1", path: "public/sample.chromdata.zarr" }],
};

function memoryState() {
	let row: { tokenHash: string; payload: string; expiresAt: number } | undefined;
	const state = {
		storage: {
			sql: {
				exec(statement: string, ...values: unknown[]) {
					if (statement.startsWith("CREATE")) return { rowsWritten: 0, toArray: () => [] };
					if (statement.startsWith("INSERT")) {
						if (row) return { rowsWritten: 0, toArray: () => [] };
						row = { tokenHash: String(values[0]), payload: String(values[1]), expiresAt: Number(values[2]) };
						return { rowsWritten: 1, toArray: () => [] };
					}
					if (statement.startsWith("DELETE")) {
						if (row && (statement.includes("token_hash = ?") ? row.tokenHash === String(values[0]) && row.expiresAt > Number(values[1]) : row.expiresAt > Number(values[0]))) {
							const selected = [{ payload: row.payload, expires_at: row.expiresAt }];
							row = undefined;
							return { rowsWritten: 1, toArray: () => selected };
						}
						return { rowsWritten: 0, toArray: () => [] };
					}
					throw new Error(`Unexpected SQL: ${statement}`);
				},
			},
			setAlarm: vi.fn(async () => undefined),
			deleteAlarm: vi.fn(async () => undefined),
		},
	} as unknown as DurableObjectState;
	(state as unknown as { blockConcurrencyWhile: (callback: () => Promise<void>) => Promise<void> }).blockConcurrencyWhile =
		async (callback) => callback();
	return state;
}

function doRequest(object: UChromHandoff, path: string, body?: unknown) {
	const internalBody = path === "/store" ? { ...(body as object), tokenHash: "a".repeat(64) } :
		path === "/redeem" ? { tokenHash: "a".repeat(64) } : body;
	return object.fetch(new Request(`https://handoff.internal${path}`, {
		method: "POST",
		body: internalBody === undefined ? undefined : JSON.stringify(internalBody),
		headers: internalBody === undefined ? undefined : { "Content-Type": "application/json" },
	}));
}

function makeEnv() {
	const instances = new Map<string, UChromHandoff>();
	const internalRequests: Request[] = [];
	const namespace = {
		idFromName: vi.fn((name: string) => name),
		get: vi.fn((id: string) => {
			let instance = instances.get(id);
			if (!instance) {
				instance = new UChromHandoff(memoryState(), {} as never);
				instances.set(id, instance);
			}
			return { fetch: (input: RequestInfo | URL, init?: RequestInit) => {
				const request = new Request(input, init);
				internalRequests.push(request.clone());
				return instance!.fetch(request);
			} };
		}),
	};
	return {
		ATLAS_ORIGIN,
		HOSTED_ORIGIN,
		ATLAS_CATALOG_URL: "https://catalog.test/catalog.json",
		ATLAS_DATA_ROOT: DATA_ROOT,
		HANDOFFS: namespace,
		fetch: vi.fn(async () => Response.json(catalog)),
		internalRequests,
	} as unknown as HandoffEnv & { fetch: ReturnType<typeof vi.fn>; internalRequests: Request[] };
}

describe("hosted handoffs", () => {
	beforeEach(() => vi.restoreAllMocks());

	it("routes handoffs to the Worker service and keeps local APIs out of the container", async () => {
		const env = makeEnv();
		const fetch = vi.fn(async () => new Response("container called"));
		const handoff = await routeHandoffRequest(
			new Request("https://browser.test/api/agent/handoffs", { method: "GET", headers: { Origin: ATLAS_ORIGIN } }), env, fetch,
		);
		expect(handoff.status).toBe(405);
		for (const path of ["/api/agent/snapshot", "/api/control/pages", "/api/control"]) {
			const response = await routeHandoffRequest(new Request(`https://browser.test${path}`), env, fetch);
			expect(response.status).toBe(404);
		}
		expect(fetch).not.toHaveBeenCalled();
	});

	it("allows only exact configured origins", () => {
		const env = makeEnv();
		expect(isAllowedOrigin(ATLAS_ORIGIN, env)).toBe(true);
		expect(isAllowedOrigin(HOSTED_ORIGIN, env)).toBe(true);
		expect(isAllowedOrigin("https://sub.uchrom-atlas.u-science.org", env)).toBe(false);
		expect(isAllowedOrigin(`${ATLAS_ORIGIN}/`, env)).toBe(false);
		expect(isAllowedOrigin("null", env)).toBe(false);
		expect(isAllowedOrigin(null, env)).toBe(false);
	});

	it("resolves only catalog IDs and safe relative dataset paths", () => {
		expect(datasetFromCatalog(catalog, "sample_1", DATA_ROOT)).toEqual({
			id: "sample_1",
			url: `${DATA_ROOT}/public/sample.chromdata.zarr`,
			version: "2026-10-22T00:00:00Z",
		});
		expect(datasetFromCatalog(catalog, "unknown", DATA_ROOT)).toBeNull();
		expect(datasetFromCatalog({ datasets: [{ id: "bad", path: "../private.zarr" }] }, "bad", DATA_ROOT)).toBeNull();
		expect(datasetFromCatalog({ datasets: [{ id: "bad", path: "https://evil.test/data.zarr" }] }, "bad", DATA_ROOT)).toBeNull();
	});

	it("bounds the serialized payload by UTF-8 bytes", () => {
		const dataset = datasetFromCatalog(catalog, "sample_1", DATA_ROOT)!;
		expect(() => createPayload({ dataset, question: "分析", pageState: { label: "细胞" } }, 1_000, 64)).toThrow(/limit|size/i);
		const payload = createPayload({ dataset }, 1_000, 1_000);
		expect(payload.expires_at).toBe(new Date(1_000 + HANDOFF_TTL_MS).toISOString());
	});

	it("expires after ten minutes and rejects a replay", async () => {
		const object = new UChromHandoff(memoryState(), {} as never);
		let now = Date.now();
		vi.spyOn(Date, "now").mockImplementation(() => now);
		const payload = { version: 1, expires_at: new Date(now + HANDOFF_TTL_MS).toISOString() };
		const stored = await doRequest(object, "/store", { payload });
		expect(stored.status).toBe(201);
		const first = await doRequest(object, "/redeem");
		expect(first.status).toBe(200);
		expect(await first.json()).toEqual(payload);
		const replay = await doRequest(object, "/redeem");
		expect(replay.status).toBe(404);
	});

	it("atomically permits only one concurrent redemption", async () => {
		const object = new UChromHandoff(memoryState(), {} as never);
		const payload = { value: "once", expires_at: new Date(Date.now() + HANDOFF_TTL_MS).toISOString() };
		await doRequest(object, "/store", { payload });
		const results = await Promise.all([doRequest(object, "/redeem"), doRequest(object, "/redeem")]);
		expect(results.map((response) => response.status).sort()).toEqual([200, 404]);
	});

	it("rejects a handoff after its ten-minute TTL", async () => {
		const object = new UChromHandoff(memoryState(), {} as never);
		let now = Date.now();
		vi.spyOn(Date, "now").mockImplementation(() => now);
		const payload = { value: "expires", expires_at: new Date(now + HANDOFF_TTL_MS).toISOString() };
		expect((await doRequest(object, "/store", { payload })).status).toBe(201);
		now += HANDOFF_TTL_MS;
		expect((await doRequest(object, "/redeem")).status).toBe(404);
	});

	it("routes creation and redemption through the DO without exposing tokens in URLs or logs", async () => {
		const env = makeEnv();
		const info = vi.spyOn(console, "info").mockImplementation(() => undefined);
		const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
		const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
		const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
		const created = await handleHandoff(new Request("https://browser.test/api/agent/handoffs", {
			method: "POST",
			headers: { Origin: ATLAS_ORIGIN, "Content-Type": "application/json" },
			body: JSON.stringify({ dataset_id: "sample_1", question: "Inspect this dataset" }),
		}), env);
		expect(created.status).toBe(201);
		const { token } = await created.json() as { token: string };
		expect(token).toMatch(/^[A-Za-z0-9_-]{43}$/);
		expect(env.HANDOFFS.get).toHaveBeenCalled();
		const queryAttempt = await handleHandoff(new Request(`https://browser.test/api/agent/handoffs/redeem?token=${token}`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ token }),
		}), env);
		expect(queryAttempt.status).toBe(400);
		const redeemed = await handleHandoff(new Request("https://browser.test/api/agent/handoffs/redeem", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ token }),
		}), env);
		expect(redeemed.status).toBe(200);
		const observable = [info.mock.calls, warn.mock.calls, error.mock.calls, log.mock.calls].flat(2).join(" ");
		expect(observable).not.toContain(token);
		expect(env.HANDOFFS.idFromName).not.toHaveBeenCalledWith(token);
		expect(env.internalRequests.map((request) => request.url)).toEqual([
			"https://handoff.internal/store", "https://handoff.internal/redeem",
		]);
		for (const request of env.internalRequests) expect(await request.text()).not.toContain(token);
	});

	it("rejects an invalid origin, oversized request and non-catalog dataset", async () => {
		const env = makeEnv();
		const post = (origin: string, body: unknown) => handleHandoff(new Request("https://browser.test/api/agent/handoffs", {
			method: "POST",
			headers: { Origin: origin, "Content-Type": "application/json" },
			body: JSON.stringify(body),
		}), env);
		expect((await post("https://attacker.test", { dataset_id: "sample_1" })).status).toBe(403);
		expect((await post(ATLAS_ORIGIN, { dataset_id: "missing" })).status).toBe(404);
		expect((await post(HOSTED_ORIGIN, { dataset_id: "sample_1", page_state: { text: "x".repeat(1_048_576) } })).status).toBe(413);
	});

	it("does not allow Atlas to attach a page snapshot", async () => {
		const env = makeEnv();
		const response = await handleHandoff(new Request("https://browser.test/api/agent/handoffs", {
			method: "POST",
			headers: { Origin: ATLAS_ORIGIN, "Content-Type": "application/json" },
			body: JSON.stringify({ dataset_id: "sample_1", page_state: { selection: ["cell-1"] } }),
		}), env);
		expect(response.status).toBe(400);
	});
});
