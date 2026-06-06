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
  const REPORT_HEADERS = [
    "row_id",
    "audio_file",
    "timestamp",
    "label_type",
    "original_text",
    "final_text",
    "sop_label",
    "error_types",
    "primary_error_type",
    "llm_policy",
    "selector_reason",
    "selection_score",
    "guard_decision",
    "action",
    "issue_tags",
    "used_llm",
    "model_name",
    "confidence",
    "need_human_review",
    "notes",
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
  const ERROR_TYPE_PRIORITY = ["E7", "E6", "E2", "E1", "E3", "E4", "E5", "E8"];
  const POLICY_PRIORITY = {
    HUMAN_REVIEW_ONLY: 5,
    LLM_CAP_EXCEEDED: 4,
    MUST_LLM: 3,
    OPTIONAL_LLM: 2,
    RULE_ONLY: 1,
    KEEP: 0,
  };
  const ERROR_TYPE_TAGS = {
    E1: "DOMAIN_TERM_ERROR",
    E2: "CHILD_UNCLEAR",
    E3: "HOMOPHONE_ERROR",
    E4: "REPEATED_WORDS",
    E5: "PUNCTUATION_ERROR",
    E6: "MULTI_SPEAKER_OVERLAP",
    E7: "UNREADABLE_SENTENCE",
    E8: "OTHER_ASR_ERROR",
  };
  const REPEATED_TOKENS = ["老师", "今天", "开始", "小朋友", "孩子", "你们", "我们", "排队", "材料"];
  const SEVERE_DOMAIN_PATTERNS = ["建狗区", "建够区", "建构狗", "低狗区"];
  const CHILD_SPEECH_PATTERNS = ["滑花梯", "还花花体", "花花体", "滑滑体"];
  const UNREADABLE_PATTERNS = ["无法识别", "听不清", "不清楚", "今天们", "积积老师", "好了去"];
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
    {
      annotator: "demo",
      source_file: "中一班_区域活动_demo",
      audio_file: "000004.wav",
      label: "teacher_1",
      label_display: "T1",
      label_type: "teacher",
      teacher_id: "1",
      text_edited: "老师今天建狗区",
      recognition_errors: "",
      timestamp: "2026-06-06 20:00:06",
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
    if (looksMultiSpeaker(text, row.label_type || "")) {
      tags.add("MULTI_SPEAKER_OVERLAP");
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

  function looksMultiSpeaker(text, labelType) {
    if (labelType === "teacher") {
      return false;
    }
    const questionCount = (text.match(/[？?]/g) || []).length;
    const answerMarkers = (text.match(/老师|小朋友|孩子|你们|我们|他说|她说/g) || []).length;
    const speakerPrefixes = (text.match(/(老师|教师|幼儿|儿童|学生)[:：]/g) || []).length;
    return speakerPrefixes >= 2 || (text.length > 90 && questionCount >= 3 && answerMarkers >= 2) || (text.includes("同时") && (text.includes("说话") || text.includes("讲话")));
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

  function detectErrorTypes(row, classification) {
    const text = String(row.text_edited || "").trim();
    const errors = String(row.recognition_errors || "");
    const tags = new Set(classification.tags);
    const types = new Set();
    const issueTags = new Set();
    let severity = 0;

    if (tags.has("MULTI_SPEAKER_OVERLAP") || looksMultiSpeaker(text, row.label_type || "")) {
      types.add("E6");
      severity = Math.max(severity, 2);
    }
    if (looksUnreadable(text, tags)) {
      types.add("E7");
      severity = Math.max(severity, 2);
    }
    if (looksDomainError(text, errors)) {
      types.add("E1");
      severity = Math.max(severity, SEVERE_DOMAIN_PATTERNS.some((pattern) => text.includes(pattern)) ? 2 : 1);
    }
    if (looksChildSpeechError(row, text, errors)) {
      types.add("E2");
      severity = Math.max(severity, ["还花花体", "花花体"].some((pattern) => text.includes(pattern)) ? 2 : 1);
    }
    if (looksHomophoneError(text, errors)) {
      types.add("E3");
      severity = Math.max(severity, 1);
    }
    const repeatSeverity = repeatedSeverity(text);
    if (repeatSeverity) {
      types.add("E4");
      severity = Math.max(severity, repeatSeverity);
    }
    if (looksPunctuationError(text)) {
      types.add("E5");
      severity = Math.max(severity, 1);
    }
    if (!types.size && errors.trim()) {
      types.add("E8");
      severity = Math.max(severity, 1);
    }

    types.forEach((type) => {
      if (ERROR_TYPE_TAGS[type]) issueTags.add(ERROR_TYPE_TAGS[type]);
    });
    return {
      errorTypes: Array.from(types).sort(),
      primaryErrorType: primaryErrorType(types),
      issueTags: Array.from(issueTags).sort(),
      severity,
    };
  }

  function primaryErrorType(types) {
    return ERROR_TYPE_PRIORITY.find((type) => types.has(type)) || Array.from(types).sort()[0] || "";
  }

  function looksUnreadable(text, tags) {
    if (tags.has("HALLUCINATION_RISK")) return false;
    if (UNREADABLE_PATTERNS.some((pattern) => text.includes(pattern))) return true;
    const compact = compactText(text);
    if (compact.length < 10) return false;
    return (compact.match(/那个好了|好了去|们玩那个|去积/g) || []).length >= 2;
  }

  function looksDomainError(text, errors) {
    const domainWrongTerms = DOMAIN_TERMS.map(([wrong]) => wrong);
    return domainWrongTerms.some((term) => text.includes(term)) || SEVERE_DOMAIN_PATTERNS.some((pattern) => text.includes(pattern)) || /领域|术语|积木|建构|低结构|纸巾筒/.test(errors);
  }

  function looksChildSpeechError(row, text, errors) {
    if (CHILD_SPEECH_PATTERNS.some((pattern) => text.includes(pattern))) return true;
    return ["student", "child", "unknown"].includes(row.label_type || "") && /儿童|发音|不清/.test(errors);
  }

  function looksHomophoneError(text, errors) {
    const correctionWrongTerms = CORRECTION_MAP.map(([wrong]) => wrong);
    return correctionWrongTerms.some((term) => text.includes(term)) || /同音|近音|错词|错字/.test(errors) || /兰色|篮色|排对|金木|收才料/.test(text);
  }

  function repeatedSeverity(text) {
    if (/(.{1,4})\1{2,}/.test(text)) return 2;
    const adjacentRepeats = REPEATED_TOKENS.filter((token) => text.includes(token + token)).length;
    return adjacentRepeats > 0 ? 1 : 0;
  }

  function looksPunctuationError(text) {
    const compact = compactText(text);
    return compact.length >= 18 && (!/[。！？!?]/.test(text) || /([。！？；，、])\1+/.test(text));
  }

  function assessCandidatePolicy(row, classification, errorAnalysis, changedByRules, currentText) {
    const tags = new Set(classification.tags);
    const errorTypes = new Set(errorAnalysis.errorTypes);
    const text = String(currentText || "").trim();
    const compact = compactText(text);
    const score = scoreCandidate(row, text, errorAnalysis);
    let sopLabel = "0";
    let llmPolicy = changedByRules ? "RULE_ONLY" : "KEEP";
    let reason = "clear or rule-only Label 0 segment";

    if (tags.has("EMPTY_TEXT") || tags.has("SHORT_BACKCHANNEL") || tags.has("NOISE_ONLY")) {
      return { sopLabel: "0", llmPolicy: "KEEP", selectorReason: "low-value Label 0 segment", selectionScore: score };
    }
    if (errorTypes.has("E6") || errorTypes.has("E7") || tags.has("MEDIA_MATERIAL") || tags.has("MULTI_SPEAKER_OVERLAP") || tags.has("HALLUCINATION_RISK") || tags.has("NEEDS_HUMAN_REVIEW")) {
      return { sopLabel: "2", llmPolicy: "HUMAN_REVIEW_ONLY", selectorReason: "high-risk or non-recoverable segment", selectionScore: score };
    }
    if (!errorTypes.size) {
      return { sopLabel, llmPolicy, selectorReason: reason, selectionScore: score };
    }

    sopLabel = errorAnalysis.severity >= 2 ? "2" : "1";
    if (changedByRules && sopLabel === "1") {
      llmPolicy = "RULE_ONLY";
      reason = "Label 1 issue resolved by rules or dictionaries";
    } else if (sopLabel === "2" && ["E1", "E2", "E3", "E4", "E5"].some((type) => errorTypes.has(type))) {
      llmPolicy = compact.length >= 6 && text.length <= 220 ? "MUST_LLM" : "HUMAN_REVIEW_ONLY";
      reason = "Label 2 refinable ASR error";
    } else {
      llmPolicy = compact.length >= 12 && text.length <= 220 ? "OPTIONAL_LLM" : "RULE_ONLY";
      reason = "Label 1 optional refinement candidate";
    }
    return { sopLabel, llmPolicy, selectorReason: reason, selectionScore: score };
  }

  function scoreCandidate(row, text, errorAnalysis) {
    const base = { E7: 1, E6: 0.96, E2: 0.92, E1: 0.88, E3: 0.82, E4: 0.68, E5: 0.56, E8: 0.4 };
    let score = base[errorAnalysis.primaryErrorType] || 0;
    if (row.label_type === "teacher") score += 0.05;
    if (text.length >= 35) score += 0.05;
    if (String(row.recognition_errors || "").trim()) score += 0.03;
    if (errorAnalysis.severity >= 2) score += 0.08;
    return Math.min(score, 1).toFixed(4);
  }

  function processRow(row, options) {
    const original = { ...row };
    const output = { ...row };
    const classification = classifyRow(row);
    const errorAnalysis = detectErrorTypes(row, classification);
    const issueTags = Array.from(new Set([...classification.tags, ...errorAnalysis.issueTags])).sort();
    const report = {
      row_id: options.rowId,
      audio_file: row.audio_file || "",
      timestamp: row.timestamp || "",
      label_type: row.label_type || "",
      original_text: row.text_edited || "",
      final_text: row.text_edited || "",
      sop_label: "0",
      error_types: errorAnalysis.errorTypes.join("|"),
      primary_error_type: errorAnalysis.primaryErrorType,
      llm_policy: "KEEP",
      selector_reason: "",
      selection_score: "",
      guard_decision: "",
      action: classification.action,
      issue_tags: issueTags.join("|"),
      used_llm: "false",
      model_name: options.modelName || "deepseek-v4-flash",
      confidence: "",
      need_human_review: classification.needReview ? "true" : "false",
      notes: "",
    };

    if (classification.action === "SKIP") {
      const policy = assessCandidatePolicy(row, classification, errorAnalysis, false, output.text_edited || "");
      Object.assign(report, {
        sop_label: policy.sopLabel,
        llm_policy: policy.llmPolicy,
        selector_reason: policy.selectorReason,
        selection_score: policy.selectionScore,
      });
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
    const policy = assessCandidatePolicy(row, classification, errorAnalysis, changed, current);
    Object.assign(report, {
      sop_label: policy.sopLabel,
      llm_policy: policy.llmPolicy,
      selector_reason: policy.selectorReason,
      selection_score: policy.selectionScore,
      need_human_review: policy.llmPolicy === "HUMAN_REVIEW_ONLY" ? "true" : report.need_human_review,
    });
    if (policy.llmPolicy === "HUMAN_REVIEW_ONLY") {
      report.action = "HUMAN_REVIEW_REQUIRED";
      report.issue_tags = Array.from(new Set([...report.issue_tags.split("|").filter(Boolean), "NEEDS_HUMAN_REVIEW"])).sort().join("|");
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
      sop_label: item.sop_label,
      error_types: item.error_types,
      primary_error_type: item.primary_error_type,
      llm_policy: item.llm_policy,
      selector_reason: item.selector_reason,
      selection_score: item.selection_score,
      guard_decision: item.guard_decision,
      action: item.action,
      issue_tags: item.issue_tags,
      used_llm: item.used_llm,
      model_name: item.model_name,
      confidence: item.confidence,
      need_human_review: item.need_human_review,
      notes: item.notes,
    }));
  }

  function modifiedReportRows(report) {
    return reportToRows(report).filter((item) => item.original_text !== item.final_text);
  }

  function policyHitRows(report) {
    return reportToRows(report)
      .filter((item) => {
        const policy = item.llm_policy || "KEEP";
        return item.sop_label !== "0" || Boolean(item.error_types) || !["KEEP", "RULE_ONLY"].includes(policy);
      })
      .sort(comparePolicyRows);
  }

  function comparePolicyRows(left, right) {
    const leftPolicy = POLICY_PRIORITY[left.llm_policy] || 0;
    const rightPolicy = POLICY_PRIORITY[right.llm_policy] || 0;
    if (leftPolicy !== rightPolicy) {
      return rightPolicy - leftPolicy;
    }
    const leftError = errorPriorityIndex(left.primary_error_type || firstErrorType(left.error_types));
    const rightError = errorPriorityIndex(right.primary_error_type || firstErrorType(right.error_types));
    if (leftError !== rightError) {
      return leftError - rightError;
    }
    return Number(left.row_id || 0) - Number(right.row_id || 0);
  }

  function firstErrorType(value) {
    return String(value || "")
      .split("|")
      .filter(Boolean)[0] || "";
  }

  function errorPriorityIndex(value) {
    const index = ERROR_TYPE_PRIORITY.indexOf(value);
    return index === -1 ? ERROR_TYPE_PRIORITY.length : index;
  }

  function emptyMetrics() {
    return { changed: 0, skipped: 0, review: 0, labels: {}, errors: {} };
  }

  function countPolicyMetrics(metrics, report) {
    const label = report.sop_label || "0";
    metrics.labels[label] = (metrics.labels[label] || 0) + 1;
    String(report.error_types || "")
      .split("|")
      .filter(Boolean)
      .forEach((type) => {
        metrics.errors[type] = (metrics.errors[type] || 0) + 1;
      });
  }

  function formatCountMap(values, prefix) {
    const entries = Object.keys(values)
      .sort()
      .map((key) => `${prefix}${key}: ${values[key]}`);
    return entries.length ? entries.join(" · ") : "-";
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
    const changesWrap = document.getElementById("changesWrap");
    const modifiedCount = document.getElementById("modifiedCount");
    const policyWrap = document.getElementById("policyWrap");
    const policyCount = document.getElementById("policyCount");
    const tabs = Array.from(document.querySelectorAll(".tab"));
    const modelOptions = Array.from(document.querySelectorAll(".model-option"));
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
      modelName: "deepseek-v4-flash",
      metrics: emptyMetrics(),
    };

    function setStatus(text) {
      statusChip.textContent = text;
    }

    function options() {
      return {
        punctuation: document.getElementById("punctuationToggle").checked,
        domain: document.getElementById("domainToggle").checked,
        names: document.getElementById("nameToggle").checked,
        modelName: state.modelName,
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
      state.metrics = emptyMetrics();
      setStatus("已加载");
      processBtn.disabled = rows.length === 0;
      processBtn.textContent = "开始本地预检";
      resetBtn.disabled = false;
      downloadCsvBtn.disabled = true;
      downloadReportBtn.disabled = true;
      updateProgress(0, rows.length);
      updateCurrentPreview(null);
      renderChanges();
      renderPolicyHits();
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
      state.metrics = emptyMetrics();
      setStatus("本地预检中");
      processBtn.disabled = true;
      pauseBtn.disabled = false;
      downloadCsvBtn.disabled = true;
      downloadReportBtn.disabled = true;
      renderChanges();
      renderPolicyHits();
      processChunk();
    }

    function processChunk() {
      if (state.paused) {
        setStatus("已暂停");
        processBtn.disabled = false;
        processBtn.textContent = "继续预检";
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
        countPolicyMetrics(state.metrics, result.report);
        updateCurrentPreview({ index, original: state.originalRows[index], output: result.row, report: result.report });
      }
      state.currentIndex = end;
      updateProgress(state.currentIndex, state.originalRows.length);
      renderChanges();
      renderPolicyHits();
      if (state.currentIndex < state.originalRows.length) {
        setTimeout(processChunk, 10);
      } else {
        state.processing = false;
        setStatus("本地完成");
        processBtn.disabled = false;
        processBtn.textContent = "重新预检";
        pauseBtn.disabled = true;
        downloadCsvBtn.disabled = false;
        downloadReportBtn.disabled = false;
        renderChanges();
        renderPolicyHits();
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
      document.getElementById("labelDistribution").textContent = formatCountMap(state.metrics.labels, "L");
      document.getElementById("errorDistribution").textContent = formatCountMap(state.metrics.errors, "");
    }

    function updateCurrentPreview(payload) {
      if (!payload) {
        document.getElementById("currentRowId").textContent = "row_id: -";
        document.getElementById("currentOriginal").textContent = "";
        document.getElementById("currentOutput").textContent = "";
        document.getElementById("currentAction").textContent = "WAITING";
        document.getElementById("currentTags").textContent = "-";
        document.getElementById("currentPolicy").textContent = "Label - / -";
        document.getElementById("currentErrors").textContent = "-";
        return;
      }
      document.getElementById("currentRowId").textContent = `row_id: ${payload.index + 1}`;
      document.getElementById("currentOriginal").textContent = payload.original.text_edited || "(空文本)";
      document.getElementById("currentOutput").textContent = payload.output.text_edited || "(空文本)";
      document.getElementById("currentAction").textContent = payload.report.action;
      document.getElementById("currentTags").textContent = payload.report.issue_tags || "-";
      document.getElementById("currentPolicy").textContent = `Label ${payload.report.sop_label || "-"} / ${payload.report.llm_policy || "-"}`;
      document.getElementById("currentErrors").textContent = payload.report.error_types || "-";
    }

    function renderChanges() {
      const changedRows = modifiedReportRows(state.report.filter(Boolean));
      modifiedCount.textContent = `${changedRows.length} 条`;
      if (!changedRows.length) {
        changesWrap.innerHTML = '<p class="empty-state"></p>';
        return;
      }
      changesWrap.innerHTML = changedRows
        .map(
          (row) => `
            <article class="diff-item">
              <div class="diff-meta">
                <code>row_id: ${escapeHtml(row.row_id)}</code>
                <span>${escapeHtml(row.audio_file || "")}</span>
                <span>${escapeHtml(row.action || "")}</span>
                <span>Label ${escapeHtml(row.sop_label || "-")}</span>
                <span>${escapeHtml(row.llm_policy || "-")}</span>
                <span>${escapeHtml(row.error_types || "-")}</span>
              </div>
              <div class="diff-grid">
                <pre class="diff-before"><span>-</span>${escapeHtml(row.original_text || "(空文本)")}</pre>
                <pre class="diff-after"><span>+</span>${escapeHtml(row.final_text || "(空文本)")}</pre>
              </div>
              <p class="diff-notes">${escapeHtml(row.notes || "")}</p>
            </article>
          `
        )
        .join("");
    }

    function renderPolicyHits() {
      const rows = policyHitRows(state.report.filter(Boolean));
      policyCount.textContent = `${rows.length} 条`;
      if (!rows.length) {
        policyWrap.innerHTML = '<p class="empty-state"></p>';
        return;
      }
      policyWrap.innerHTML = rows
        .map((row) => {
          const hot = ["HUMAN_REVIEW_ONLY", "LLM_CAP_EXCEEDED", "MUST_LLM"].includes(row.llm_policy);
          const outputLine = row.original_text !== row.final_text ? `<small>输出：${escapeHtml(row.final_text || "(空文本)")}</small>` : "";
          const reason = [row.selector_reason, row.notes].filter(Boolean).join("；");
          return `
            <article class="policy-item">
              <div class="policy-meta">
                <code>row_id: ${escapeHtml(row.row_id)}</code>
                <span class="policy-badge ${hot ? "policy-hot" : ""}">Label ${escapeHtml(row.sop_label || "-")}</span>
                <span class="policy-badge ${hot ? "policy-hot" : ""}">${escapeHtml(row.llm_policy || "-")}</span>
                <span class="policy-badge">${escapeHtml(row.error_types || "-")}</span>
                <span class="policy-badge">${escapeHtml(row.action || "-")}</span>
              </div>
              <div class="policy-text">
                <p>${escapeHtml(row.original_text || "(空文本)")}</p>
                ${outputLine}
                <small>${escapeHtml(reason)}</small>
              </div>
            </article>
          `;
        })
        .join("");
    }

    function renderPreview() {
      const rows = state.activeTab === "original" ? state.originalRows : state.activeTab === "output" ? state.outputRows : reportToRows(state.report.filter(Boolean));
      const headers = state.activeTab === "report" ? REPORT_HEADERS : state.headers;
      if (!rows.length) {
        tableWrap.innerHTML = '<p class="empty-state"></p>';
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
      const headers = isReport ? REPORT_HEADERS : state.headers;
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
        processBtn.textContent = "开始本地预检";
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
      state.metrics = emptyMetrics();
      state.paused = false;
      state.processing = false;
      processBtn.disabled = state.originalRows.length === 0;
      processBtn.textContent = "开始本地预检";
      pauseBtn.disabled = true;
      downloadCsvBtn.disabled = true;
      downloadReportBtn.disabled = true;
      setStatus(state.originalRows.length ? "已重置" : "等待 CSV");
      updateProgress(0, state.originalRows.length);
      updateCurrentPreview(null);
      renderChanges();
      renderPolicyHits();
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
    modelOptions.forEach((button) => {
      button.addEventListener("click", () => {
        state.modelName = button.dataset.model;
        modelOptions.forEach((item) => {
          const isActive = item === button;
          item.classList.toggle("active", isActive);
          item.setAttribute("aria-checked", isActive ? "true" : "false");
        });
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
    detectErrorTypes,
    assessCandidatePolicy,
    cleanText,
    normalizePunctuation,
    applyDictionary,
    processRow,
    reportToRows,
    modifiedReportRows,
    policyHitRows,
    emptyMetrics,
    DEMO_ROWS,
    REQUIRED_COLUMNS,
    REPORT_HEADERS,
  };
});
