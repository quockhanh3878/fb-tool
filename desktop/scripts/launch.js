// plan: docs/plans/desktop_packaging.md
//
// npm start goi truc tiep "electron ." se ke thua ELECTRON_RUN_AS_NODE tu
// terminal cha neu co (VD: terminal tich hop cua VS Code / cac cong cu dev
// nen Electron khac tiem bien nay) — Electron doc thay bien nay va tu chay
// nhu mot tien trinh Node thuong thay vi mo GUI that, khien "app" trong
// require("electron") la undefined va crash ngay o app.whenReady(). Wrapper
// nay don sach bien do khoi env truoc khi spawn electron that.
"use strict";

const { spawn } = require("node:child_process");
const path = require("node:path");

const electronPath = require("electron");

const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;

const proc = spawn(electronPath, ["."], {
  cwd: path.join(__dirname, ".."),
  env,
  stdio: "inherit",
});

proc.on("exit", (code) => process.exit(code == null ? 1 : code));
