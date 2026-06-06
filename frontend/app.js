(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.KindyLabRefinement = api;
  }
})(typeof window !== "undefined" ? window : null, function () {
  "use strict";

  const REQUIRED_COLUMNS = [
    "annotator",
    "source_file",
    "audio_file",
    "label",
    "label_display",
    "label_type",
    "teacher_id",
    "text_edited",
    "recognition_errors",
    "timestamp",
  ];

  const IMMUTABLE_COLUMNS = [
    "annotator",
    "source_file",
    "audio_file",
    "label",
    "label_display",
    "label_type",
    "teacher_id",
    "timestamp",
  ];

  const BACKCHANNELS = new Set(["嗯", "恩", "啊", "哦", "噢", "呃", "诶", "哎", "唉", "好", "对", "是", "不是", "没有", "可以", "行"]);
  const QUESTION_ENDINGS = ["吗", "嘛", "好不好", "对不对", "对吧", "是不是", "行不行", "可以吗", "有没有", "什么呀", "什么啊", "什么呢", "哪里呢", "哪儿呢", "怎么呢", "怎么做呢", "怎么样", "怎么做", "多少", "哪一个"];
  const QUESTION_WORDS = ["什么", "哪里", "哪儿", "几", "怎么", "为什么", "谁"];
  const MEDIA_KEYWORDS = ["儿歌", "动画片", "播放", "歌词", "广播", "音频", "音乐", "故事机", "火箭发射", "即将关闭", "谨防夹伤"];
  const DEMO_ROWS = [
    {
      annotator: "demo",
      source_file: "中一班_区域活动_demo",
      audio_file: "000001.wav",
      label: "teacher_1",
      label_display: "T1",
      label_type: "teacher",
      teacher_id: "1",
      text_edited: "  我在金木区吗  ",
      recognition_errors: "",
      timestamp: "2026-06-06 20:00:00",
    },
    {
      annotator: "demo",
      source_file: "中一班_区域活动_demo",
      audio_file: "000002.wav",
      label: "student",
      label_display: "学生",
      label_type: "student",
      teacher_id: "",
      text_edited: "嗯",
      recognition_errors: "",
      timestamp: "2026-06-06 20:00:02",
    },
    {
      annotator: "demo",
      source_file: "中一班_区域活动_demo",
      audio_file: "000003.wav",
      label: "teacher_1",
      label_display: "T1",
      label_type: "teacher",
      teacher_id: "1",
      text_edited: "这个地结构材料可以怎么玩",
      recognition_errors: "",
      timestamp: "2026-06-06 20:00:04",
    },
  ];

  const CORRECTION_MAP = [
    ["垫脚", "踮脚", "常见错词修正"],
    ["插座子", "擦桌子", "常见错词修正"],
    ["金木", "积木", "常见错词修正"],
    ["排对", "排队", "常见错词修正"],
    ["收才料", "收材料", "常见错词修正"],
  ];

  const DOMAIN_TERMS = [
    ["地结构材料", "低结构材料", "领域词修正"],
    ["低节构材料", "低结构材料", "领域词修正"],
    ["低结构的材料", "低结构材料", "领域词修正"],
    ["纸今筒", "纸巾筒", "领域词修正"],
    ["只今筒", "纸巾筒", "领域词修正"],
    ["建构去", "建构区", "领域词修正"],
    ["美工去", "美工区", "领域词修正"],
    ["语言去", "语言区", "领域词修正"],
    ["科学去", "科学区", "领域词修正"],
    ["泥巴去", "泥巴区", "领域词修正"],
    ["小木庄", "小木桩", "领域词修正"],
    ["小木装", "小木桩", "领域词修正"],
  ];

  const NAME_ALIASES = [
    ["小鸡", "小纪", "姓名修正"],
    ["第一", "一一", "姓名修正"],
    ["叔叔", "书书", "姓名修正"],
  ];

  function parseCsv(text) {
    const content = text.replace(/^\uFEFF/, "");
    const rows = [];
    let row = [];
    let field = "";
    let inQuotes = false;

    for (let i = 0; i < content.length; i += 1) {
      const char = content[i];
      const next = content[i + 1];
      if (inQuotes) {
        if (char === '"' && next === '"') {
          field += '"';
          i += 1;
        } else if (char === '"') {
          inQuotes = false;
        } else {
          field += char;
        }
        continue;
      }
      if (char === '"') {
        inQuotes = true;
      } else if (char === ",") {
        row.push(field);
        field = "";
      } else if (char === "\n") {
        row.push(field);
        rows.push(row);
        row = [];
        field = "";
      } else if (char !== "\r") {
        field += char;
      }
    }
    if (field.length > 0 || row.length > 0) {
      row.push(field);
      rows.push(row);
    }
    const headers = rows.shift() || [];
    const objects = rows
      .filter((cells) => cells.length > 1 || cells[0] !== "")
      .map((cells) => {
        const item = {};
        headers.forEach((header, index) => {
          item[header] = cells[index] || "";
        });
        return item;
      });
    return { headers, rows: objects };
  }

  function serializeCsv(headers, rows) {
    const lines = [headers.map(escapeCsv).join(",")];
    rows.forEach((row) => {
      lines.push(headers.map((header) => escapeCsv(row[header] || "")).join(","));
    });
    return `\uFEFF${lines.join("\n")}\n`;
  }

  function escapeCsv(value) {
    const stringValue = String(value ?? "");
    if (/[",\r\n]/.test(stringValue)) {
      return `"${stringValue.replace(/"/g, '""')}"`;
    }
    return stringValue;
  }

  function validateHeaders(headers) {
    const missing = REQUIRED_COLUMNS.filter((column) => !headers.includes(column));
    if (missing.length > 0) {
      throw new Error(`CSV 缺少必要字段：${missing.join(", ")}`);
    }
  }

  function compactText(text) {
    return String(text || "").replace(/[\s，,。.!！?？；;：:、]+/g, "");
  }

  function mergeErrorNotes(existing, notes) {
    const seen = new Set();
    const merged = [];
    String(existing || "")
      .replace(/；/g, ";")
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean)
      .forEach((note) => {
        if (!seen.has(note)) {
          seen.add(note);
          merged.push(note);
        }
      });
    notes.forEach((note) => {
      if (note && !seen.has(note)) {
        seen.add(note);
        merged.push(note);
      }
    });
    return merged.join("; ");
  }

  function classifyRow(row) {
    const text = String(row.text_edited || "").trim();
    const compact = compactText(text);
    const tags = new Set();
    let action = "UNCHANGED";
    let needReview = false;

    if (!text) {
      tags.add("EMPTY_TEXT");
      return { action: "SKIP", tags: Array.from(tags), needReview };
    }
    if (compact.length <= 4 && BACKCHANNELS.has(compact)) {
      tags.add("SHORT_BACKCHANNEL");
      return { action: "SKIP", tags: Array.from(tags), needReview };
    }
    if (/^[哈呵嘿嘻]+[。！？!?]*$/.test(compact) || /^[啊呀哇呜嗷]+[。！？!?]*$/.test(compact)) {
      tags.add("NOISE_ONLY");
      return { action: "SKIP", tags: Array.from(tags), needReview };
    }
    if (MEDIA_KEYWORDS.some((keyword) => text.includes(keyword))) {
      tags.add("MEDIA_MATERIAL");
      needReview = true;
    }
    if (text.length > 220) {
      tags.add("SEGMENT_TOO_LONG");
      needReview = true;
    }
    if ((row.label_type === "student" || row.label_type === "unknown") && text.length > 140) {
      tags.add("HALLUCINATION_RISK");
      needReview = true;
    }
    if (tags.size === 0) {
      tags.add("VALID_TEACHING_TEXT");
    }
    if (needReview) {
      tags.add("NEEDS_HUMAN_REVIEW");
      action = "HUMAN_REVIEW_REQUIRED";
    }
    return { action, tags: Array.from(tags), needReview };
  }

  function cleanText(text, options) {
    let current = String(text || "");
    const notes = [];
    const spaced = current
      .replace(/[\t\r\n\u00a0]+/g, " ")
      .replace(/ {2,}/g, " ")
      .replace(/\s*([，。！？；：、])\s*/g, "$1")
      .replace(/\s+([,.!?;:])/g, "$1")
      .trim();
    if (spaced !== current) {
      current = spaced;
      notes.push("[空格清理]");
    }
    if (options.punctuation) {
      const normalized = normalizePunctuation(current);
      if (normalized !== current) {
        current = normalized;
        notes.push("[标点修正]");
      }
    }
    return { text: current, notes };
  }

  function normalizePunctuation(text) {
    let current = text.replace(/\?/g, "？").replace(/!/g, "！").replace(/;/g, "；");
    current = current.replace(/([。！？；，、])\1+/g, "$1");
    current = current.replace(/，([。！？])/g, "$1").replace(/([。！？])，/g, "$1");
    const compact = compactText(current);
    if (!current || /[。！？!?…]$/.test(current) || compact.length <= 4) {
      return current;
    }
    if (QUESTION_ENDINGS.some((ending) => compact.endsWith(ending)) || QUESTION_WORDS.some((word) => compact.endsWith(word))) {
      return `${current}？`;
    }
    return current;
  }

  function applyDictionary(text, entries) {
    let current = text;
    const notes = [];
    entries
      .slice()
      .sort((a, b) => b[0].length - a[0].length)
      .forEach(([wrong, correct, type]) => {
        if (wrong && wrong !== correct && current.includes(wrong)) {
          current = current.split(wrong).join(correct);
          notes.push(`${wrong}->${correct}[${type}]`);
        }
      });
    return { text: current, notes };
  }

  function processRow(row, options) {
    const original = { ...row };
    const output = { ...row };
    const classification = classifyRow(row);
    const report = {
      row_id: options.rowId,
      audio_file: row.audio_file || "",
      timestamp: row.timestamp || "",
      label_type: row.label_type || "",
      original_text: row.text_edited || "",
      final_text: row.text_edited || "",
      action: classification.action,
      issue_tags: classification.tags.join("|"),
      used_llm: "false",
      confidence: "",
      need_human_review: classification.needReview ? "true" : "false",
      notes: "",
    };

    if (classification.action === "SKIP") {
      return { row: output, report, changed: false, skipped: true };
    }

    const notes = [];
    let current = output.text_edited || "";
    const clean = cleanText(current, options);
    current = clean.text;
    notes.push(...clean.notes);

    const baseDict = [...CORRECTION_MAP, ...(options.domain ? DOMAIN_TERMS : []), ...(options.names ? NAME_ALIASES : [])];
    const dictResult = applyDictionary(current, baseDict);
    current = dictResult.text;
    notes.push(...dictResult.notes);

    const changed = current !== original.text_edited;
    if (changed) {
      output.text_edited = current;
      output.recognition_errors = mergeErrorNotes(output.recognition_errors, notes);
      report.action = notes.some((note) => note.includes("[姓名修正]")) ? "NAME_FIXED" : notes.some((note) => note.includes("[领域词修正]") || note.includes("[常见错词修正]")) ? "DICT_FIXED" : "RULE_FIXED";
    }
    report.final_text = current;
    report.notes = notes.join("; ");
    validateImmutable(original, output);
    return { row: output, report, changed, skipped: false };
  }

  function validateImmutable(original, output) {
    IMMUTABLE_COLUMNS.forEach((column) => {
      if ((original[column] || "") !== (output[column] || "")) {
        throw new Error(`不可修改字段被改变：${column}`);
      }
    });
  }

  function reportToRows(report) {
    return report.map((item) => ({
      row_id: String(item.row_id),
      audio_file: item.audio_file,
      timestamp: item.timestamp,
      label_type: item.label_type,
      original_text: item.original_text,
      final_text: item.final_text,
      action: item.action,
      issue_tags: item.issue_tags,
      used_llm: item.used_llm,
      confidence: item.confidence,
      need_human_review: item.need_human_review,
      notes: item.notes,
    }));
  }

  function initBrowserApp() {
    const fileInput = document.getElementById("fileInput");
    const dropZone = document.getElementById("dropZone");
    const processBtn = document.getElementById("processBtn");
    const demoBtn = document.getElementById("demoBtn");
    const pauseBtn = document.getElementById("pauseBtn");
    const resetBtn = document.getElementById("resetBtn");
    const downloadCsvBtn = document.getElementById("downloadCsvBtn");
    const downloadReportBtn = document.getElementById("downloadReportBtn");
    const statusChip = document.getElementById("statusChip");
    const tableWrap = document.getElementById("tableWrap");
    const tabs = Array.from(document.querySelectorAll(".tab"));
    const state = {
      headers: [],
      originalRows: [],
      outputRows: [],
      report: [],
      activeTab: "original",
      paused: false,
      processing: false,
      currentIndex: 0,
      filename: "output_cleaned.csv",
      metrics: { changed: 0, skipped: 0, review: 0 },
    };

    function setStatus(text) {
      statusChip.textContent = text;
    }

    function options() {
      return {
        punctuation: document.getElementById("punctuationToggle").checked,
        domain: document.getElementById("domainToggle").checked,
        names: document.getElementById("nameToggle").checked,
      };
    }

    function loadFile(file) {
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const parsed = parseCsv(String(reader.result || ""));
          validateHeaders(parsed.headers);
          hydrateCsv(parsed.headers, parsed.rows, file.name.replace(/\.csv$/i, "_cleaned.csv"));
        } catch (error) {
          setStatus("格式错误");
          tableWrap.innerHTML = `<p class="empty-state">${escapeHtml(error.message)}</p>`;
        }
      };
      reader.readAsText(file, "utf-8");
    }

    function hydrateCsv(headers, rows, filename) {
      state.headers = headers;
      state.originalRows = rows;
      state.outputRows = rows.map((row) => ({ ...row }));
      state.report = [];
      state.currentIndex = 0;
      state.filename = filename;
      state.metrics = { changed: 0, skipped: 0, review: 0 };
      setStatus("已加载");
      processBtn.disabled = rows.length === 0;
      processBtn.textContent = "开始清洗";
      resetBtn.disabled = false;
      downloadCsvBtn.disabled = true;
      downloadReportBtn.disabled = true;
      updateProgress(0, rows.length);
      updateCurrentPreview(null);
      renderPreview();
    }

    function startProcessing() {
      if (state.processing || state.originalRows.length === 0) {
        return;
      }
      state.processing = true;
      state.paused = false;
      state.currentIndex = 0;
      state.outputRows = state.originalRows.map((row) => ({ ...row }));
      state.report = [];
      state.metrics = { changed: 0, skipped: 0, review: 0 };
      setStatus("处理中");
      processBtn.disabled = true;
      pauseBtn.disabled = false;
      downloadCsvBtn.disabled = true;
      downloadReportBtn.disabled = true;
      processChunk();
    }

    function processChunk() {
      if (state.paused) {
        setStatus("已暂停");
        processBtn.disabled = false;
        processBtn.textContent = "继续清洗";
        return;
      }
      const chunkSize = 90;
      const end = Math.min(state.currentIndex + chunkSize, state.originalRows.length);
      for (let index = state.currentIndex; index < end; index += 1) {
        const result = processRow(state.originalRows[index], { ...options(), rowId: index + 1 });
        state.outputRows[index] = result.row;
        state.report[index] = result.report;
        if (result.changed) state.metrics.changed += 1;
        if (result.skipped) state.metrics.skipped += 1;
        if (result.report.need_human_review === "true") state.metrics.review += 1;
        updateCurrentPreview({ index, original: state.originalRows[index], output: result.row, report: result.report });
      }
      state.currentIndex = end;
      updateProgress(state.currentIndex, state.originalRows.length);
      if (state.currentIndex < state.originalRows.length) {
        setTimeout(processChunk, 10);
      } else {
        state.processing = false;
        setStatus("完成");
        processBtn.disabled = false;
        processBtn.textContent = "重新清洗";
        pauseBtn.disabled = true;
        downloadCsvBtn.disabled = false;
        downloadReportBtn.disabled = false;
        renderPreview();
      }
    }

    function updateProgress(done, total) {
      const percent = total ? Math.round((done / total) * 100) : 0;
      document.getElementById("progressLabel").textContent = `${done} / ${total} 行`;
      document.getElementById("progressPercent").textContent = `${percent}%`;
      document.getElementById("progressFill").style.width = `${percent}%`;
      document.getElementById("totalRows").textContent = String(total);
      document.getElementById("changedRows").textContent = String(state.metrics.changed);
      document.getElementById("skippedRows").textContent = String(state.metrics.skipped);
      document.getElementById("reviewRows").textContent = String(state.metrics.review);
    }

    function updateCurrentPreview(payload) {
      if (!payload) {
        document.getElementById("currentRowId").textContent = "row_id: -";
        document.getElementById("currentOriginal").textContent = state.originalRows.length ? "点击开始清洗后显示实时行内容" : "尚未加载文件";
        document.getElementById("currentOutput").textContent = state.originalRows.length ? "等待处理" : "尚未生成输出";
        document.getElementById("currentAction").textContent = "WAITING";
        document.getElementById("currentTags").textContent = "-";
        return;
      }
      document.getElementById("currentRowId").textContent = `row_id: ${payload.index + 1}`;
      document.getElementById("currentOriginal").textContent = payload.original.text_edited || "(空文本)";
      document.getElementById("currentOutput").textContent = payload.output.text_edited || "(空文本)";
      document.getElementById("currentAction").textContent = payload.report.action;
      document.getElementById("currentTags").textContent = payload.report.issue_tags || "-";
    }

    function renderPreview() {
      const rows = state.activeTab === "original" ? state.originalRows : state.activeTab === "output" ? state.outputRows : reportToRows(state.report.filter(Boolean));
      const headers = state.activeTab === "report" ? ["row_id", "audio_file", "timestamp", "label_type", "original_text", "final_text", "action", "issue_tags", "used_llm", "confidence", "need_human_review", "notes"] : state.headers;
      if (!rows.length) {
        tableWrap.innerHTML = '<p class="empty-state">上传 CSV 后，这里会显示前 120 行预览。</p>';
        return;
      }
      const previewRows = rows.slice(0, 120);
      const html = [
        "<table>",
        "<thead><tr>",
        ...headers.map((header) => `<th>${escapeHtml(header)}</th>`),
        "</tr></thead><tbody>",
        ...previewRows.map((row, index) => {
          const changed = state.activeTab === "output" && state.originalRows[index] && state.originalRows[index].text_edited !== row.text_edited;
          return `<tr class="${changed ? "changed" : ""}">${headers.map((header) => `<td>${escapeHtml(row[header] || "")}</td>`).join("")}</tr>`;
        }),
        "</tbody></table>",
      ].join("");
      tableWrap.innerHTML = html;
    }

    function downloadCsv(kind) {
      const isReport = kind === "report";
      const headers = isReport ? ["row_id", "audio_file", "timestamp", "label_type", "original_text", "final_text", "action", "issue_tags", "used_llm", "confidence", "need_human_review", "notes"] : state.headers;
      const rows = isReport ? reportToRows(state.report.filter(Boolean)) : state.outputRows;
      const csv = serializeCsv(headers, rows);
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = isReport ? "quality_report.csv" : state.filename;
      link.click();
      URL.revokeObjectURL(url);
    }

    fileInput.addEventListener("change", (event) => {
      const file = event.target.files && event.target.files[0];
      if (file) loadFile(file);
    });
    demoBtn.addEventListener("click", () => {
      hydrateCsv(REQUIRED_COLUMNS, DEMO_ROWS.map((row) => ({ ...row })), "demo_cleaned.csv");
    });
    ["dragenter", "dragover"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.add("dragging");
      });
    });
    ["dragleave", "drop"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.remove("dragging");
      });
    });
    dropZone.addEventListener("drop", (event) => {
      const file = event.dataTransfer.files && event.dataTransfer.files[0];
      if (file) loadFile(file);
    });
    processBtn.addEventListener("click", () => {
      if (state.paused) {
        state.paused = false;
        processBtn.disabled = true;
        processChunk();
      } else {
        processBtn.textContent = "开始清洗";
        startProcessing();
      }
    });
    pauseBtn.addEventListener("click", () => {
      state.paused = true;
      pauseBtn.disabled = true;
    });
    resetBtn.addEventListener("click", () => {
      state.outputRows = state.originalRows.map((row) => ({ ...row }));
      state.report = [];
      state.currentIndex = 0;
      state.metrics = { changed: 0, skipped: 0, review: 0 };
      state.paused = false;
      state.processing = false;
      processBtn.disabled = state.originalRows.length === 0;
      processBtn.textContent = "开始清洗";
      pauseBtn.disabled = true;
      downloadCsvBtn.disabled = true;
      downloadReportBtn.disabled = true;
      setStatus(state.originalRows.length ? "已重置" : "等待 CSV");
      updateProgress(0, state.originalRows.length);
      updateCurrentPreview(null);
      renderPreview();
    });
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        state.activeTab = tab.dataset.tab;
        tabs.forEach((item) => {
          item.classList.toggle("active", item === tab);
          item.setAttribute("aria-selected", item === tab ? "true" : "false");
        });
        renderPreview();
      });
    });
    downloadCsvBtn.addEventListener("click", () => downloadCsv("output"));
    downloadReportBtn.addEventListener("click", () => downloadCsv("report"));
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", initBrowserApp);
  }

  return {
    parseCsv,
    serializeCsv,
    validateHeaders,
    classifyRow,
    cleanText,
    normalizePunctuation,
    applyDictionary,
    processRow,
    reportToRows,
    DEMO_ROWS,
    REQUIRED_COLUMNS,
  };
});
