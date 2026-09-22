// plan: docs/plans/desktop_watchdog_reliability_plan.md
"use strict";

const DEFAULT_BACKOFF_MS = [2000, 5000, 15000, 30000, 60000];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

class SidecarSupervisor {
  constructor({
    services,
    probe,
    stopChild,
    onStateChange,
    onFailure,
    log,
    now = () => Date.now(),
    sleepFn = sleep,
    probeIntervalMs = 5000,
    probeTimeoutMs = 1000,
    startupTimeoutMs = 30000,
    failureThreshold = 3,
    restartWindowMs = 30 * 60 * 1000,
    maxRestarts = 5,
    backoffMs = DEFAULT_BACKOFF_MS,
  }) {
    if (!services || !services.backend || !services.frontend) {
      throw new Error("backend and frontend sidecars are required");
    }
    if (typeof probe !== "function") throw new Error("probe callback is required");

    this.services = services;
    this.probe = probe;
    this.stopChild = stopChild || ((child) => child?.kill?.());
    this.onStateChange = onStateChange || (() => {});
    this.onFailure = onFailure || (() => {});
    this.log = log || (() => {});
    this.now = now;
    this.sleep = sleepFn;
    this.probeIntervalMs = probeIntervalMs;
    this.probeTimeoutMs = probeTimeoutMs;
    this.startupTimeoutMs = startupTimeoutMs;
    this.failureThreshold = failureThreshold;
    this.restartWindowMs = restartWindowMs;
    this.maxRestarts = maxRestarts;
    this.backoffMs = backoffMs;
    this.children = new Map();
    this.states = new Map(
      Object.keys(services).map((name) => [name, {
        status: "stopped",
        consecutiveProbeFailures: 0,
        restartTimes: [],
      }])
    );
    this.running = false;
    this.stopping = false;
    this.booting = false;
    this.restartTask = null;
    this.probeTimer = null;
  }

  getState(name) {
    const state = this.states.get(name);
    return state ? { ...state, restartTimes: [...state.restartTimes] } : null;
  }

  getStates() {
    return Object.fromEntries([...this.states].map(([name]) => [name, this.getState(name)]));
  }

  _setStatus(name, status) {
    const state = this.states.get(name);
    state.status = status;
    this.onStateChange(name, this.getState(name));
  }

  async start() {
    if (this.running) return;
    this.running = true;
    this.stopping = false;
    this.booting = true;
    try {
      await this._startService("backend");
      if (!(await this._waitUntilHealthy("backend", this.startupTimeoutMs))) {
        throw new Error("backend did not become ready");
      }
      await this._startService("frontend");
      if (!(await this._waitUntilHealthy("frontend", this.startupTimeoutMs))) {
        throw new Error("frontend did not become ready");
      }
      this.booting = false;
      this.probeTimer = setInterval(() => {
        this._poll().catch((error) => this.log(`watchdog probe failed: ${error.message}`));
      }, this.probeIntervalMs);
      this.probeTimer.unref?.();
    } catch (error) {
      this.booting = false;
      await this.stop();
      throw error;
    }
  }

  async stop() {
    this.stopping = true;
    this.running = false;
    this.booting = false;
    if (this.probeTimer) clearInterval(this.probeTimer);
    this.probeTimer = null;
    this.restartTask = null;
    await this._stopService("frontend");
    await this._stopService("backend");
  }

  async _startService(name) {
    if (this.stopping) return;
    const service = this.services[name];
    this._setStatus(name, "starting");
    const child = await service.start();
    this.children.set(name, child);
    child?.on?.("exit", (code, signal) => {
      if (this.children.get(name) === child) this.children.delete(name);
      if (this.stopping || this.booting) return;
      this.log(`${name} exited (code=${code}, signal=${signal})`);
      this._restartFor(name, "unexpected exit").catch((error) => {
        this.log(`${name} restart failed: ${error.message}`);
      });
    });
  }

  async _stopService(name) {
    const child = this.children.get(name);
    this.children.delete(name);
    if (!child) {
      this._setStatus(name, "stopped");
      return;
    }
    this._setStatus(name, "stopping");
    await this.stopChild(child, name);
    this._setStatus(name, "stopped");
  }

  async _probe(name) {
    let timeout;
    try {
      return await Promise.race([
        Promise.resolve(this.probe(name)),
        new Promise((resolve) => {
          timeout = setTimeout(() => resolve(false), this.probeTimeoutMs);
        }),
      ]);
    } catch (_error) {
      return false;
    } finally {
      if (timeout) clearTimeout(timeout);
    }
  }

  async _waitUntilHealthy(name, timeoutMs) {
    const deadline = this.now() + timeoutMs;
    while (!this.stopping && this.now() < deadline) {
      if (await this._probe(name)) {
        const state = this.states.get(name);
        state.consecutiveProbeFailures = 0;
        this._setStatus(name, "healthy");
        return true;
      }
      await this.sleep(Math.min(this.probeIntervalMs, Math.max(1, deadline - this.now())));
    }
    return false;
  }

  async _poll() {
    if (!this.running || this.stopping || this.restartTask) return;
    for (const name of ["backend", "frontend"]) {
      const state = this.states.get(name);
      if (state.status === "failed" || state.status === "stopped") continue;
      if (await this._probe(name)) {
        state.consecutiveProbeFailures = 0;
        this._setStatus(name, "healthy");
        continue;
      }
      state.consecutiveProbeFailures += 1;
      this.log(`${name} readiness probe failed (${state.consecutiveProbeFailures}/${this.failureThreshold})`);
      if (state.consecutiveProbeFailures >= this.failureThreshold) {
        await this._restartFor(name, "readiness probe failed");
        return;
      }
    }
  }

  async _restartFor(name, reason) {
    if (this.stopping || this.states.get(name).status === "failed") return;
    if (this.restartTask) return this.restartTask;
    this.restartTask = this._performRestart(name, reason).finally(() => {
      this.restartTask = null;
    });
    return this.restartTask;
  }

  _recordRestart(name) {
    const state = this.states.get(name);
    const cutoff = this.now() - this.restartWindowMs;
    state.restartTimes = state.restartTimes.filter((time) => time > cutoff);
    if (state.restartTimes.length >= this.maxRestarts) return null;
    state.restartTimes.push(this.now());
    return state.restartTimes.length;
  }

  async _performRestart(name, reason) {
    const attempt = this._recordRestart(name);
    if (attempt == null) {
      this._markFailed(name, `restart limit exceeded after ${reason}`);
      return;
    }
    this.log(`restarting ${name}; reason=${reason}; attempt=${attempt}`);
    this._setStatus(name, "restarting");
    if (name === "backend") {
      await this._stopService("frontend");
      await this._stopService("backend");
      await this.sleep(this.backoffMs[Math.min(attempt - 1, this.backoffMs.length - 1)] || 0);
      if (this.stopping) return;
      await this._startService("backend");
      if (!(await this._waitUntilHealthy("backend", this.startupTimeoutMs))) {
        this.log("backend restart did not become ready");
        return;
      }
      await this._startService("frontend");
      if (!(await this._waitUntilHealthy("frontend", this.startupTimeoutMs))) {
        this.log("frontend restart did not become ready");
        return;
      }
      return;
    }
    await this._stopService(name);
    await this.sleep(this.backoffMs[Math.min(attempt - 1, this.backoffMs.length - 1)] || 0);
    if (this.stopping) return;
    await this._startService(name);
    if (!(await this._waitUntilHealthy(name, this.startupTimeoutMs))) {
      this.log(`${name} restart did not become ready`);
    }
  }

  _markFailed(name, reason) {
    this._setStatus(name, "failed");
    this.log(`${name} watchdog failed: ${reason}`);
    this.onFailure({ name, reason, states: this.getStates() });
  }
}

module.exports = { DEFAULT_BACKOFF_MS, SidecarSupervisor };
