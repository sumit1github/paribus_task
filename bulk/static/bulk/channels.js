class ResilientSocket {
    constructor(url, { protocols = [], maxDelay = 30_000 } = {}) {
        this.url = url;
        this.protocols = protocols;
        this.maxDelay = maxDelay;
        this.attempt = 0;
        this.shouldRun = true;
        this.listeners = { message: [], open: [], close: [], error: [] };
        this.connect();
    }

    connect() {
        this.ws = new WebSocket(this.url, this.protocols);

        this.ws.onopen = (e) => {
            this.attempt = 0;
            this.startHeartbeat();
            this.flushQueue();
            this.listeners.open.forEach(fn => fn(e));
        };

        this.ws.onmessage = (e) => {
            // Heartbeat reply
            if (e.data === "pong") { this.lastPong = Date.now(); return; }
            this.listeners.message.forEach(fn => fn(e));
        };

        this.ws.onclose = (e) => {
            this.stopHeartbeat();
            this.listeners.close.forEach(fn => fn(e));
            // 4401 = unauthenticated — don't retry, trigger re-auth instead
            if (!this.shouldRun || e.code === 4401) return;
            const delay = Math.min(this.maxDelay, (2 ** this.attempt) * 500);
            const jitter = Math.random() * 300;
            setTimeout(() => this.connect(), delay + jitter);
            this.attempt++;
        };

        this.ws.onerror = (e) => this.listeners.error.forEach(fn => fn(e));
    }

    startHeartbeat() {
        this.lastPong = Date.now();
        this.hb = setInterval(() => {
            if (Date.now() - this.lastPong > 35_000) {
                this.ws.close(4000, "heartbeat-timeout");
                return;
            }
            if (this.ws.readyState === WebSocket.OPEN) this.ws.send("ping");
        }, 15_000);
    }
    stopHeartbeat() { clearInterval(this.hb); }

    queue = [];
    send(data) {
        const payload = typeof data === "string" ? data : JSON.stringify(data);
        if (this.ws.readyState === WebSocket.OPEN) this.ws.send(payload);
        else this.queue.push(payload);
    }
    flushQueue() { while (this.queue.length) this.ws.send(this.queue.shift()); }

    on(event, fn) { this.listeners[event].push(fn); return this; }

    close() { this.shouldRun = false; this.ws.close(1000, "client-close"); }
}



const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
const socket = new ResilientSocket(`${wsScheme}://${window.location.host}/ws/batch/${batch_id}/`);

socket.on("open", () => console.log("WS open →", socket.url));
socket.on("error", (e) => console.warn("WS error", e));
socket.on("close", (e) => console.log("WS close", e.code, e.reason));

socket.on("message", (event) => {
    // Server sends rendered HTML for the progress fragment.
    console.log("WS message", event.data);
    const target = document.getElementById("progress-body");
    if (target) {
        target.innerHTML = event.data;
    }
});
