// plan: docs/plans/desktop_watchdog_reliability_plan.md
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const { SidecarSupervisor } = require("../supervisor");

function harness(overrides = {}) {
  const starts = [];
  const stops = [];
  const children = { backend: [], frontend: [] };
  const probes = { backend: true, frontend: true };
  const supervisor = new SidecarSupervisor({
    services: {
      backend: { start: () => spawn("backend") },
      frontend: { start: () => spawn("frontend") },
    },
    probe: async (name) => probes[name],
    stopChild: async (child, name) => {
      stops.push(name);
      child.killed = true;
    },
    sleepFn: async () => {},
    probeIntervalMs: 1,
    startupTimeoutMs: 10,
    ...overrides,
  });

  function spawn(name) {
    const child = new EventEmitter();
    child.killed = false;
    children[name].push(child);
    starts.push(name);
    return child;
  }

  return { supervisor, starts, stops, children, probes };
}

async function flush() {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
}

test("restarts backend then frontend after an abnormal backend exit", async () => {
  const h = harness({ backoffMs: [0] });
  await h.supervisor.start();
  h.children.backend[0].emit("exit", 1, null);
  await flush();
  assert.deepEqual(h.starts, ["backend", "frontend", "backend", "frontend"]);
  assert.ok(h.stops.includes("frontend"));
  await h.supervisor.stop();
});

test("restarts only frontend after an abnormal frontend exit", async () => {
  const h = harness({ backoffMs: [0] });
  await h.supervisor.start();
  h.children.frontend[0].emit("exit", 1, null);
  await flush();
  assert.deepEqual(h.starts, ["backend", "frontend", "frontend"]);
  await h.supervisor.stop();
});

test("graceful stop never respawns an exiting child", async () => {
  const h = harness({ backoffMs: [0] });
  await h.supervisor.start();
  const backend = h.children.backend[0];
  await h.supervisor.stop();
  backend.emit("exit", 0, null);
  await flush();
  assert.deepEqual(h.starts, ["backend", "frontend"]);
});

test("three failed probes trigger one ordered restart", async () => {
  const h = harness({ backoffMs: [0] });
  await h.supervisor.start();
  let failedProbes = 0;
  h.supervisor.probe = async (name) => {
    if (name === "backend" && failedProbes < 3) {
      failedProbes += 1;
      return false;
    }
    return true;
  };
  await h.supervisor._poll();
  await h.supervisor._poll();
  await h.supervisor._poll();
  assert.deepEqual(h.starts, ["backend", "frontend", "backend", "frontend"]);
  await h.supervisor.stop();
});

test("the sixth restart is blocked within the restart window", async () => {
  const failures = [];
  const h = harness({ backoffMs: [0], onFailure: (failure) => failures.push(failure) });
  await h.supervisor.start();
  for (let index = 0; index < 6; index += 1) {
    h.children.frontend[h.children.frontend.length - 1].emit("exit", 1, null);
    await flush();
  }
  assert.equal(h.supervisor.getState("frontend").status, "failed");
  assert.equal(failures.length, 1);
  assert.equal(h.starts.filter((name) => name === "frontend").length, 6);
  await h.supervisor.stop();
});
