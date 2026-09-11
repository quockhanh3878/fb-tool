// plan: docs/plans/desktop_packaging.md
//
// Giai doan 3 — Electron shell toi thieu: spawn 2 sidecar bang .venv/node
// HE THONG cua may dang chay (chua bundle — Giai doan 4 se dong goi rieng
// .venv + Next standalone vao resources). Muc tieu: xac nhan luong
// health-poll -> mo window -> dong app don sach tien trinh hoat dong dung.
"use strict";

const { app, BrowserWindow, dialog } = require("electron");
const { spawn, exec } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

const REPO_ROOT = path.join(__dirname, "..");
const BACKEND_PORT = 8877;
const FRONTEND_PORT = 3100;
const HEALTH_TIMEOUT_MS = 30000;
const HEALTH_POLL_MS = 500;

let backendProc = null;
let frontendProc = null;
let mainWindow = null;
let splashWindow = null;

function userDataPaths() {
  const root = app.getPath("userData");
  const dataDir = path.join(root, "data");
  const logDir = path.join(root, "logs");
  fs.mkdirSync(dataDir, { recursive: true });
  fs.mkdirSync(logDir, { recursive: true });
  return { root, dataDir, logDir };
}

function toSqliteUrl(dataDir) {
  // Alembic/SQLAlchemy can duong dan sqlite kieu POSIX (forward slash) ke ca
  // tren Windows, nguoc lai "unable to open database file".
  const posix = dataDir.replace(/\\/g, "/");
  return `sqlite+aiosqlite:///${posix}/commhunter_api.db`;
}

function ensureJwtSecret(root) {
  // Sinh 1 lan + luu ben — doi JWT_SECRET giua cac lan mo app se buoc
  // refresh token cu het hieu luc (khong nguy hiem vi auto-login lai ngay,
  // nhung khong can thiet phai doi moi lan khoi dong).
  const secretFile = path.join(root, "jwt_secret.txt");
  if (fs.existsSync(secretFile)) {
    return fs.readFileSync(secretFile, "utf8").trim();
  }
  const secret = crypto.randomBytes(32).toString("hex");
  fs.writeFileSync(secretFile, secret, "utf8");
  return secret;
}

function showSplash() {
  splashWindow = new BrowserWindow({
    width: 420,
    height: 220,
    frame: false,
    resizable: false,
    center: true,
  });
  splashWindow.loadURL(
    "data:text/html;charset=utf-8," +
      encodeURIComponent(`<!doctype html>
        <meta charset="utf-8">
        <body style="margin:0;display:flex;align-items:center;justify-content:center;
          height:220px;font-family:sans-serif;background:#0f172a;color:#e2e8f0;">
          <div style="text-align:center">
            <div style="font-size:16px;margin-bottom:8px;">CommHunter AI</div>
            <div style="font-size:13px;color:#94a3b8;">Dang khoi dong...</div>
          </div>
        </body>`)
  );
}

async function waitForHealth(url, timeoutMs) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(1000) });
      if (res.ok) return true;
    } catch (_err) {
      // Chua san sang — thu lai.
    }
    await new Promise((r) => setTimeout(r, HEALTH_POLL_MS));
  }
  return false;
}

function killProcessTree(proc) {
  if (proc == null || proc.pid == null) return;
  if (process.platform === "win32") {
    exec(`taskkill /pid ${proc.pid} /T /F`);
  } else {
    try {
      process.kill(-proc.pid, "SIGTERM");
    } catch (_err) {
      proc.kill("SIGTERM");
    }
  }
}

function killByPort(port) {
  // taskkill /T bo sot chau khi tien trinh trung gian chay qua shell:true
  // (npm.cmd -> cmd.exe -> node) — cmd.exe cha da thoat truoc khi chau kip
  // gan lai parent PID hop le, nen /T khong lan toi duoc. Don theo cong dang
  // nghe la cach chac chan tren Windows.
  if (process.platform !== "win32") return;
  exec(`for /f "tokens=5" %a in ('netstat -ano ^| findstr :${port} ^| findstr LISTENING') do taskkill /pid %a /T /F`, {
    shell: "cmd.exe",
  });
}

function startBackend(logDir, dataDir, root) {
  const pythonExe = path.join(REPO_ROOT, ".venv", "Scripts", "python.exe");
  if (!fs.existsSync(pythonExe)) {
    throw new Error(`Khong tim thay Python trong .venv: ${pythonExe}`);
  }
  const logStream = fs.createWriteStream(path.join(logDir, "backend.log"), {
    flags: "a",
  });
  const proc = spawn(
    pythonExe,
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT)],
    {
      cwd: path.join(REPO_ROOT, "backend"),
      env: {
        ...process.env,
        RUN_MODE: "desktop",
        DATABASE_URL: toSqliteUrl(dataDir),
        JWT_SECRET: ensureJwtSecret(root),
        BROWSER_PROFILES_ROOT: path.join(dataDir, "browser_profiles"),
      },
    }
  );
  proc.stdout.pipe(logStream);
  proc.stderr.pipe(logStream);
  return proc;
}

function startFrontend(logDir) {
  const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm";
  const logStream = fs.createWriteStream(path.join(logDir, "frontend.log"), {
    flags: "a",
  });
  const proc = spawn(npmCmd, ["run", "dev", "--", "-p", String(FRONTEND_PORT)], {
    cwd: path.join(REPO_ROOT, "frontend"),
    shell: process.platform === "win32",
    env: {
      ...process.env,
      NEXT_PUBLIC_API_URL: `http://127.0.0.1:${BACKEND_PORT}`,
    },
  });
  proc.stdout.pipe(logStream);
  proc.stderr.pipe(logStream);
  return proc;
}

async function boot() {
  const { root, dataDir, logDir } = userDataPaths();
  showSplash();

  backendProc = startBackend(logDir, dataDir, root);
  const backendOk = await waitForHealth(`http://127.0.0.1:${BACKEND_PORT}/health`, HEALTH_TIMEOUT_MS);
  if (!backendOk) {
    dialog.showErrorBox(
      "Khong khoi dong duoc",
      `Backend khong phan hoi sau ${HEALTH_TIMEOUT_MS / 1000}s.\n` +
        `Xem log: ${path.join(logDir, "backend.log")}`
    );
    app.quit();
    return;
  }

  frontendProc = startFrontend(logDir);
  const frontendOk = await waitForHealth(`http://127.0.0.1:${FRONTEND_PORT}`, HEALTH_TIMEOUT_MS);
  if (!frontendOk) {
    dialog.showErrorBox(
      "Khong khoi dong duoc",
      `Dashboard khong phan hoi sau ${HEALTH_TIMEOUT_MS / 1000}s.\n` +
        `Xem log: ${path.join(logDir, "frontend.log")}`
    );
    app.quit();
    return;
  }

  mainWindow = new BrowserWindow({ width: 1280, height: 800 });
  await mainWindow.loadURL(`http://127.0.0.1:${FRONTEND_PORT}`);
  if (splashWindow) {
    splashWindow.close();
    splashWindow = null;
  }
}

app.whenReady().then(boot);

app.on("window-all-closed", () => {
  app.quit();
});

app.on("before-quit", () => {
  killProcessTree(backendProc);
  killProcessTree(frontendProc);
  killByPort(BACKEND_PORT);
  killByPort(FRONTEND_PORT);
});
