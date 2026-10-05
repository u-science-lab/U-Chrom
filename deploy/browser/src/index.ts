// The hosted U-Chrom web browser: a Worker in front of a container running `python -m uchrom.browser --web --hosted`.
//
// The server keeps each visitor's datasets in memory (a session per cookie), so a visitor must always reach the same
// instance: the Worker gives every new visitor a session id (cookie), and picks the instance by a hash of it.
import { Container } from "@cloudflare/containers";

export class UChromBrowser extends Container {
	defaultPort = 8000;
	// the container sleeps (and stops being billed) after this long without a request
	sleepAfter = "15m";
}

// A cold container (image pull, Python start) can take longer than the default wait for its port: the first request
// of an instance waits up to two minutes instead of answering 503.
const START_TIMEOUTS = { instanceGetTimeoutMS: 120_000, portReadyTimeoutMS: 120_000, waitInterval: 500 };

interface Env {
	UCHROM: DurableObjectNamespace<UChromBrowser>;
	INSTANCES?: string;
}

const COOKIE = "uchrom_session";

function sessionOf(request: Request): string | null {
	const m = (request.headers.get("Cookie") ?? "").match(new RegExp(`(?:^|;\\s*)${COOKIE}=([^;]+)`));
	return m ? m[1] : null;
}

function fnv1a(s: string): number {
	let h = 0x811c9dc5;
	for (let i = 0; i < s.length; i++) {
		h ^= s.charCodeAt(i);
		h = Math.imul(h, 0x01000193) >>> 0;
	}
	return h >>> 0;
}

export default {
	async fetch(request: Request, env: Env): Promise<Response> {
		const n = Math.max(1, parseInt(env.INSTANCES ?? "2", 10) || 1);
		let sid = sessionOf(request);
		const fresh = !sid;
		if (!sid) {
			const bytes = crypto.getRandomValues(new Uint8Array(18));
			sid = btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
			const headers = new Headers(request.headers);
			const old = headers.get("Cookie");
			headers.set("Cookie", old ? `${old}; ${COOKIE}=${sid}` : `${COOKIE}=${sid}`);
			request = new Request(request, { headers });
		}
		const container = env.UCHROM.getByName(`browser-${fnv1a(sid) % n}`);
		const retry = request.clone();                    // the body is consumed by the first attempt
		let response = await container.fetch(request).catch(() => null as Response | null);
		if (!response || response.status === 503) {
			await container.startAndWaitForPorts(8000, START_TIMEOUTS);
			response = await container.fetch(retry);
		}
		if (!fresh) return response;
		const out = new Response(response.body, response);
		out.headers.append("Set-Cookie", `${COOKIE}=${sid}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=1800`);
		return out;
	},
} satisfies ExportedHandler<Env>;
