import { loadPyodide } from "pyodide";
import fs from "node:fs";
import path from "node:path";

const SP = path.resolve(process.argv[2]);
const wheel = path.join(SP, "wheel", "query_doctor-0.11.0-py3-none-any.whl");
const bench = fs.readFileSync(path.join(SP, "bench.py"), "utf8");
const profiles = process.argv.slice(3);

const mark = (label, t0) =>
  console.log(`${label}: ${(performance.now() - t0).toFixed(0)} ms`);

let t = performance.now();
const py = await loadPyodide();
mark("pyodide boot", t);

t = performance.now();
try {
  await py.loadPackage("micropip");
  py.FS.writeFile("/query_doctor-0.11.0-py3-none-any.whl", new Uint8Array(fs.readFileSync(wheel)));
  const micropip = py.pyimport("micropip");
  await micropip.install("emfs:/query_doctor-0.11.0-py3-none-any.whl");
} catch (e) {
  console.error("INSTALL FAILED:", e.message?.slice(0, 4000) ?? String(e).slice(0, 4000));
  process.exit(1);
}
mark("wheel install", t);

t = performance.now();
py.FS.writeFile("/bench.py", bench);
await py.runPythonAsync(`
import sys
sys.path.insert(0, "/")
import bench
`);
mark("import analyzer core", t);

for (const p of profiles) {
  const text = fs.readFileSync(path.join(SP, p), "utf8");
  py.globals.set("profile_text", text);
  const res = await py.runPythonAsync(`
import json, bench
json.dumps(bench.run(profile_text))
`);
  const out = JSON.parse(res);
  console.log(
    `${p}: ${out.kib.toFixed(0)} KiB -> ${(out.seconds * 1000).toFixed(0)} ms ` +
      `(operators=${out.operators}, fact keys=${out.keys})`,
  );
}
