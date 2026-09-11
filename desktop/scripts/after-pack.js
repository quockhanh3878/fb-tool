// plan: docs/plans/desktop_packaging.md
//
// electron-builder bo qua het moi thu muc ten "node_modules" o tang liet ke
// file khi copy extraResources (danh cho co che rieng cua "files" hieu duoc
// cay dependency npm) — filter khong cuu duoc vi thu muc chua bao gio lot vao
// danh sach de loc. Next standalone lai can dung node_modules that (server.js
// require("next") truc tiep), nen copy tay bang fs sau khi pack xong.
"use strict";

const fs = require("node:fs");
const path = require("node:path");

exports.default = async function afterPack(context) {
  const src = path.join(__dirname, "..", "..", "frontend", ".next", "standalone", "node_modules");
  const dest = path.join(context.appOutDir, "resources", "frontend", "node_modules");
  if (!fs.existsSync(src)) {
    throw new Error(`Khong tim thay node_modules cua Next standalone: ${src}`);
  }
  fs.cpSync(src, dest, { recursive: true });
  console.log(`[after-pack] Da copy node_modules cua Next standalone -> ${dest}`);
};
