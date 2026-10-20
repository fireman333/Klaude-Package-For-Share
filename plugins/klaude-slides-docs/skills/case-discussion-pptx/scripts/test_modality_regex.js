// Small test for IMAGE_MODALITY_REGEX in generate_case_pptx.js (extracts the literal from source).
const fs = require("fs");
const path = require("path");
const src = fs.readFileSync(path.join(__dirname, "generate_case_pptx.js"), "utf8");
const m = src.match(/const IMAGE_MODALITY_REGEX = \/(.*)\/([a-z]*);/);
if (!m) { console.log("FAIL: regex literal not found"); process.exit(1); }
const re = new RegExp(m[1], m[2]);
const yes = ["UGI endoscopy", "Abdominal sonography", "Colonoscopy", "Ultrasound", "Chest CT", "Echocardiography", "Bronchoscopy", "Mammography", "CT angio", "Angiography", "Fluoroscopy", "Gastroscopy", "Sigmoidoscopy", "Ultrasonography"];
const no = ["MRN", "Lab", "Laboratory data", "Gastroenterology consultation", "Gastrointestinal bleeding", "Angiotensin level", "Fluorouracil", "Echolalia"];
let fail = 0;
yes.forEach((x) => { if (!re.test(x)) { console.log("FAIL should match:", x); fail++; } });
no.forEach((x) => { if (re.test(x)) { console.log("FAIL should not match:", x); fail++; } });
console.log(fail ? `${fail} failure(s)` : `OK (${yes.length} match, ${no.length} non-match)`);
process.exit(fail ? 1 : 0);
