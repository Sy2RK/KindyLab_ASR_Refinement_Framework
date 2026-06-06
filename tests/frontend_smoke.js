const assert = require("node:assert/strict");
const app = require("../frontend/app.js");

const headers = app.REQUIRED_COLUMNS;
const row = {
  annotator: "tester",
  source_file: "classroom",
  audio_file: "000001.wav",
  label: "teacher_1",
  label_display: "T1",
  label_type: "teacher",
  teacher_id: "1",
  text_edited: "  我在金木区吗  ",
  recognition_errors: "",
  timestamp: "2026-06-06 20:00:00",
};

const csv = app.serializeCsv(headers, [row]);
const parsed = app.parseCsv(csv);
assert.deepEqual(parsed.headers, headers);
assert.equal(parsed.rows.length, 1);
assert.equal(parsed.rows[0].text_edited, row.text_edited);

const result = app.processRow(parsed.rows[0], {
  rowId: 1,
  punctuation: true,
  domain: true,
  names: false,
  modelName: "deepseek-v4-pro",
});
assert.equal(result.row.text_edited, "我在积木区吗？");
assert.equal(result.row.audio_file, row.audio_file);
assert.match(result.row.recognition_errors, /金木->积木\[常见错词修正\]/);
assert.equal(result.report.action, "DICT_FIXED");
assert.equal(result.report.model_name, "deepseek-v4-pro");

const unchangedReport = {
  ...result.report,
  row_id: 2,
  original_text: "嗯",
  final_text: "嗯",
  notes: "",
};
const modifiedRows = app.modifiedReportRows([result.report, unchangedReport]);
assert.equal(modifiedRows.length, 1);
assert.equal(modifiedRows[0].row_id, "1");

const outputCsv = app.serializeCsv(headers, [result.row]);
const outputParsed = app.parseCsv(outputCsv);
assert.deepEqual(outputParsed.headers, headers);
assert.equal(outputParsed.rows[0].text_edited, "我在积木区吗？");

assert.throws(() => app.validateHeaders(["text_edited"]), /缺少必要字段/);
assert.ok(app.REPORT_HEADERS.includes("model_name"));
console.log("frontend_smoke OK");
