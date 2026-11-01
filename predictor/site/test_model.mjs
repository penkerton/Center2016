// Сверка JS-модели с эталонными прогнозами Python (selftest из data.js).
import fs from "node:fs";
import vm from "node:vm";

global.window = global;
vm.runInThisContext(fs.readFileSync(new URL("./data.js", import.meta.url), "utf8"));
vm.runInThisContext(fs.readFileSync(new URL("./model.js", import.meta.url), "utf8"));

const data = window.PREDICTOR_DATA;
let failures = 0;

for (const expected of data.selftest) {
  const prediction = window.FHMModel.predictById(expected.match_id);
  const actual = prediction.ensemble;
  const target = [expected.home, expected.draw, expected.away];
  const diff = target.map((value, index) => Math.abs(value - actual[index]));
  const maxDiff = Math.max(...diff);
  const ok = maxDiff < 1e-4;
  if (!ok) failures += 1;
  console.log(
    `${ok ? "OK  " : "FAIL"} match ${expected.match_id} ` +
      `python=[${target.map((v) => v.toFixed(6)).join(", ")}] ` +
      `js=[${actual.map((v) => v.toFixed(6)).join(", ")}] maxdiff=${maxDiff.toExponential(2)}`
  );
}

if (failures > 0) {
  console.error(`FAILED: ${failures} mismatches`);
  process.exit(1);
}
console.log("model parity OK");
