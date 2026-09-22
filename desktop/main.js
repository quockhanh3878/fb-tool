// plan: docs/plans/desktop_packaging.md
//
// Giai doan 3 — Electron shell toi thieu: spawn 2 sidecar. Che do dev (chua
// dong goi) dung .venv/node HE THONG cua may dang chay. Giai doan 4 — dong
// goi that: backend chay bang Python Embeddable portable bundle o
// resources/python (tu chua python3xx.dll, khong phu thuoc Python cai san
// tren may khach — .venv thuong khong the copy sang may khac vi thieu DLL
// nay), frontend chay bang server.js cua Next standalone qua chinh
// process.execPath cua Electron voi ELECTRON_RUN_AS_NODE=1 (Electron da
// nhung san mot Node day du, khong can dong goi Node rieng). Muc tieu:
// xac nhan luong health-poll -> mo window -> dong app don sach tien trinh
// hoat dong dung, ca hai che do dev va packaged.
"use strict";

const { app, BrowserWindow, dialog } = require("electron");
const { spawn, exec } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { SidecarSupervisor } = require("./supervisor");

const REPO_ROOT = path.join(__dirname, "..");
const IS_PACKAGED = app.isPackaged;
const RESOURCES_ROOT = IS_PACKAGED ? process.resourcesPath : REPO_ROOT;
const BACKEND_PORT = 8877;
const FRONTEND_PORT = 3100;
const HEALTH_TIMEOUT_MS = 30000;
const HEALTH_POLL_MS = 500;

let sidecarSupervisor = null;
let mainWindow = null;
let splashWindow = null;
let appLogPath = null;

function userDataPaths() {
  const root = app.getPath("userData");
  const dataDir = path.join(root, "data");
  const logDir = path.join(root, "logs");
  fs.mkdirSync(dataDir, { recursive: true });
  fs.mkdirSync(logDir, { recursive: true });
  return { root, dataDir, logDir };
}

// Nhat ky vong doi cua chinh Electron shell (khac backend.log/frontend.log
// la stdout/stderr cua 2 sidecar) — de anh Ber gui lai khi ban demo bi loi
// ma khong phai do backend/frontend (crash sidecar, spawn that bai...).
function logLine(message) {
  const line = `[${new Date().toISOString()}] ${message}\n`;
  process.stdout.write(line);
  if (appLogPath) {
    try {
      fs.appendFileSync(appLogPath, line, "utf8");
    } catch (_err) {
      // Ghi log that bai thi bo qua, khong lam sap ung dung vi log.
    }
  }
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

async function probeUrl(url) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(1000) });
    return res.ok;
  } catch (_err) {
    return false;
  }
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
  const pythonExe = IS_PACKAGED
    ? path.join(RESOURCES_ROOT, "python", "python.exe")
    : path.join(REPO_ROOT, ".venv", "Scripts", "python.exe");
  if (!fs.existsSync(pythonExe)) {
    throw new Error(`Khong tim thay Python: ${pythonExe}`);
  }
  const backendDir = IS_PACKAGED
    ? path.join(RESOURCES_ROOT, "backend")
    : path.join(REPO_ROOT, "backend");
  const logStream = fs.createWriteStream(path.join(logDir, "backend.log"), {
    flags: "a",
  });
  const proc = spawn(
    pythonExe,
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT)],
    {
      cwd: backendDir,
      env: {
        ...process.env,
        RUN_MODE: "desktop",
        AUTH_REQUIRED: "false",
        DATABASE_URL: toSqliteUrl(dataDir),
        JWT_SECRET: ensureJwtSecret(root),
        BROWSER_PROFILES_ROOT: path.join(dataDir, "browser_profiles"),
        // Dashboard (cong FRONTEND_PORT) goi API khac cong -> cross-origin. CORS
        // mac dinh cua backend chi mo cong 3000 (dev SaaS) nen trinh duyet chan
        // moi request, auto-login desktop-session that bai -> ket o man dang nhap.
        CORS_ORIGINS: JSON.stringify([
          `http://127.0.0.1:${FRONTEND_PORT}`,
          `http://localhost:${FRONTEND_PORT}`,
        ]),
      },
    }
  );
  proc.stdout.pipe(logStream);
  proc.stderr.pipe(logStream);
  proc.on("exit", (code, signal) => {
    logLine(`backend thoat (code=${code}, signal=${signal})`);
  });
  return proc;
}

function startFrontend(logDir) {
  const logStream = fs.createWriteStream(path.join(logDir, "frontend.log"), {
    flags: "a",
  });
  let proc;
  if (IS_PACKAGED) {
    // Next standalone dong san NEXT_PUBLIC_API_URL luc build (bien client-side
    // duoc inline vao JS, khong doc lai luc chay) — build packaging phai dung
    // dung BACKEND_PORT o tren. Chay bang chinh Electron lam Node de khoi phai
    // dong goi Node rieng.
    const serverJs = path.join(RESOURCES_ROOT, "frontend", "server.js");
    proc = spawn(process.execPath, [serverJs], {
      cwd: path.join(RESOURCES_ROOT, "frontend"),
      env: {
        ...process.env,
        ELECTRON_RUN_AS_NODE: "1",
        PORT: String(FRONTEND_PORT),
        HOSTNAME: "127.0.0.1",
      },
    });
  } else {
    const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm";
    proc = spawn(npmCmd, ["run", "dev", "--", "-p", String(FRONTEND_PORT)], {
      cwd: path.join(REPO_ROOT, "frontend"),
      shell: process.platform === "win32",
      env: {
        ...process.env,
        NEXT_PUBLIC_API_URL: `http://127.0.0.1:${BACKEND_PORT}`,
      },
    });
  }
  proc.stdout.pipe(logStream);
  proc.stderr.pipe(logStream);
  proc.on("exit", (code, signal) => {
    logLine(`frontend thoat (code=${code}, signal=${signal})`);
  });
  return proc;
}

async function boot() {
  const { root, dataDir, logDir } = userDataPaths();
  appLogPath = path.join(logDir, "app.log");
  logLine(`Khoi dong CommHunter AI desktop (userData=${root})`);
  showSplash();

  sidecarSupervisor = new SidecarSupervisor({
    services: {
      backend: {
        start: () => {
          const child = startBackend(logDir, dataDir, root);
          logLine(`Backend spawn xong (pid=${child.pid}), cho /ready...`);
          return child;
        },
      },
      frontend: {
        start: () => {
          const child = startFrontend(logDir);
          logLine(`Frontend spawn xong (pid=${child.pid}), cho probe...`);
          return child;
        },
      },
    },
    probe: (name) => name === "backend"
      ? probeUrl(`http://127.0.0.1:${BACKEND_PORT}/ready`)
      : probeUrl(`http://127.0.0.1:${FRONTEND_PORT}`),
    stopChild: (child) => killProcessTree(child),
    probeIntervalMs: HEALTH_POLL_MS,
    startupTimeoutMs: HEALTH_TIMEOUT_MS,
    log: (message) => logLine(`Watchdog: ${message}`),
    onFailure: ({ name, reason }) => {
      logLine(`Watchdog dung tu phuc hoi ${name}: ${reason}`);
      dialog.showErrorBox(
        "Sidecar khong the tu phuc hoi",
        `${name} khong san sang sau nhieu lan thu.\n` +
          `Xem log: ${path.join(logDir, `${name}.log`)}\n` +
          "Hay khoi dong lai ung dung sau khi xu ly log."
      );
      app.quit();
    },
  });

  try {
    await sidecarSupervisor.start();
  } catch (error) {
    logLine(`Khong khoi dong duoc sidecar: ${error.message}`);
    dialog.showErrorBox(
      "Khong khoi dong duoc",
      `${error.message}.\nXem log trong ${logDir}.`
    );
    app.quit();
    return;
  }
  logLine("Backend va frontend san sang, mo cua so chinh.");

  mainWindow = new BrowserWindow({ width: 1280, height: 800 });
  await mainWindow.loadURL(`http://127.0.0.1:${FRONTEND_PORT}`);
  if (splashWindow) {
    splashWindow.close();
    splashWindow = null;
  }
}

app.whenReady().then(boot);

app.on("window-all-closed", () => {
  logLine("Tat ca cua so da dong, thoat ung dung.");
  app.quit();
});

app.on("before-quit", () => {
  logLine("Dang don dep tien trinh sidecar truoc khi thoat.");
  sidecarSupervisor?.stop();
  killByPort(BACKEND_PORT);
  killByPort(FRONTEND_PORT);
});

process.on("uncaughtException", (err) => {
  logLine(`LOI KHONG BAT DUOC: ${err && err.stack ? err.stack : err}`);
});

process.on("unhandledRejection", (reason) => {
  logLine(`PROMISE BI TU CHOI KHONG XU LY: ${reason}`);
});
