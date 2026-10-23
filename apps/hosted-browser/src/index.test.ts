import { describe, expect, it, vi } from "vitest";
import worker, { UChromHandoff } from "./index";
import { UChromHandoff as HandoffObject } from "./handoff";

// The Cloudflare container runtime is external to these routing tests.
vi.mock("@cloudflare/containers", () => ({ Container: class {} }));

function makeEnv() {
	const container = {
		fetch: vi.fn(async (_request: Request) => new Response("hosted app")),
		startAndWaitForPorts: vi.fn(),
	};
	const getByName = vi.fn(() => container);
	const handoffs = { idFromName: vi.fn(), get: vi.fn() };
	const env = { UCHROM: { getByName }, HANDOFFS: handoffs } as unknown as Parameters<typeof worker.fetch>[1];
	return { env, container, getByName };
}

describe("hosted Worker routes", () => {
	it("exports the handoff Durable Object for its binding", () => {
		expect(UChromHandoff).toBe(HandoffObject);
	});

	it.each([
		["/api/agent/handoffs", "GET", 405],
		["/api/agent/handoffs/redeem", "GET", 405],
		["/api/agent", "GET", 404],
		["/api/agent/snapshot", "GET", 404],
		["/api/agent/events", "GET", 404],
		["/api/control", "POST", 404],
		["/api/control/pages", "POST", 404],
		["/api/agent/handoffs/other", "POST", 404],
	])("handles %s before selecting a container", async (path, method, status) => {
		const { env, container, getByName } = makeEnv();
		const response = await worker.fetch(new Request(`https://browser.test${path}`, {
			method,
			headers: { Origin: "https://uchrom-atlas.u-science.org" },
		}), env);
		expect(response.status).toBe(status);
		expect(response.headers.get("Set-Cookie")).toBeNull();
		expect(getByName).not.toHaveBeenCalled();
		expect(container.fetch).not.toHaveBeenCalled();
	});

	it.each(["/", "/api/datasets", "/api/agent-status", "/api/controller"])(
		"keeps %s on the hosted container route", async (path) => {
			const { env, container, getByName } = makeEnv();
			const response = await worker.fetch(new Request(`https://browser.test${path}`, {
				headers: { Cookie: "uchrom_session=existing-session" },
			}), env);
			expect(response.status).toBe(200);
			expect(await response.text()).toBe("hosted app");
			expect(getByName).toHaveBeenCalledOnce();
			expect(container.fetch).toHaveBeenCalledOnce();
			expect(container.fetch.mock.calls[0][0].url).toBe(`https://browser.test${path}`);
		},
	);
});
