# 幼儿园 ASR 文本清洗 Agent

这是一个保守型 CSV 清洗工作流，用于处理幼儿园课堂 ASR 文本。它优先跳过空文本、短语气词和高风险片段，再使用规则与词典修正明确错误，最后只把少量候选行送入 DeepSeek V4 Flash，并用守卫规则拒绝过度改写。

## 安装

```bash
cd /Users/sheny2/Workspace/KindyLab_ASR_Refinement/asr_refinement_agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 运行

默认配置会读取仓库内的小样例：

```bash
python main.py --disable-llm
```

处理当前工作区根目录的参考 CSV：

```bash
python main.py --disable-llm --input ../annotations_20260606_175302.csv
```

指定输入、输出和报告：

```bash
python main.py \
  --input ../annotations_20260606_175302.csv \
  --output outputs/output_cleaned.csv \
  --report outputs/quality_report.csv
```

启用 DeepSeek：

```bash
export DEEPSEEK_API_KEY="你的 API Key"
python main.py
```

也可以把 key 放在本地 `.env`：

```bash
DEEPSEEK_API_KEY="你的 API Key"
```

`.env` 已被 `.gitignore` 忽略。请不要把真实 key 写进 README、配置样例或提交历史。

如果没有设置 `DEEPSEEK_API_KEY`，系统会自动跳过 LLM，只执行规则、词典、格式校验和质量报告。

## 本地前端与真实链路

推荐用本地服务启动前端。这个服务会同时提供页面和 `/api/refine`，API key 只在服务端读取，不会写进浏览器代码：

```bash
python server.py --port 8787
```

然后访问：

```text
http://localhost:8787/frontend/
```

前端支持拖入或手动选择 CSV、Flash/Pro 模型切换、实时显示结果和当前行预览，并在页面底部预览原 CSV、输出 CSV 和质量报告。

如果页面由 `python server.py` 提供，会显示 `真实链路`，点击后会把 CSV 发给本地后端，由 Python 管线调用 DeepSeek。
如果页面由普通 `python3 -m http.server` 提供，会显示 `本地预检`，只在浏览器里执行规则、词典和候选路由模拟，不会调用 DeepSeek。

前端逻辑测试：

```bash
node tests/frontend_smoke.js
```

## 模型切换

默认模型是 `flash`，对应 `deepseek-v4-flash`：

```bash
python main.py --model flash
```

切换到 pro：

```bash
python main.py --model pro
```

也可以直接传入完整模型名：

```bash
python main.py --model deepseek-v4-pro
```

## 输出

- `outputs/output_cleaned.csv`：与输入同列名、同列顺序、同行数的清洗 CSV。
- `outputs/quality_report.csv`：逐行质量报告。
- `outputs/llm_cache.json`：LLM 文本缓存，避免重复调用。
- `outputs/llm_calls.jsonl`：LLM 调用日志。

系统只允许修改：

- `text_edited`
- `recognition_errors`

这些字段会保持不变：

- `annotator`
- `source_file`
- `audio_file`
- `label`
- `label_display`
- `label_type`
- `teacher_id`
- `timestamp`

## 候选选择规范

系统会按 SOP 生成 `sop_label`，用于说明该行是否值得进入 LLM：

- `0`：可保留，不消耗 LLM。
- `1`：可选润色，优先规则/词典，必要时按预算进入 LLM。
- `2`：严重影响理解，但只有可保守修正的片段进入 LLM。

质量报告中的 `llm_policy` 是实际路由：

- `KEEP`：保持原文。
- `RULE_ONLY`：只采用规则或词典修正。
- `OPTIONAL_LLM`：Label 1 候选，受调用比例预算控制。
- `MUST_LLM`：Label 2 中可保守修正的候选，仍受全局预算和 guard 约束。
- `HUMAN_REVIEW_ONLY`：多人重叠、不可读、疑似幻觉或多媒体材料，不让 LLM 猜测。
- `LLM_CAP_EXCEEDED`：超过配置的 LLM 调用比例，转人工复核。

错误类型写入 `error_types` 和 `primary_error_type`：

- `E1`：幼教领域词错误。
- `E2`：儿童语音识别问题。
- `E3`：同音/近音错误。
- `E4`：重复词。
- `E5`：标点或断句问题。
- `E6`：多人重叠。
- `E7`：整体不可读。
- `E8`：其他。

这些字段只写入质量报告，不会改变最终清洗 CSV 的列结构。

## 词典

词典位于 `dictionaries/`：

- `correction_map.yaml`：常见 ASR 错词。
- `domain_terms.yaml`：幼儿园课堂领域词。
- `name_aliases.yaml`：儿童姓名、昵称和教师称呼别名。

姓名词典默认不启用示例项。确认班级名单后，再把对应项的 `enabled` 改为 `true` 或追加新项。

## 质量控制

LLM 输出会被以下规则拦截：

- 新增内容比例过高。
- 删除内容比例过高。
- 编辑距离过大。
- 置信度低于阈值。
- 删除教师语气词或儿童表达。
- 新增说话人标签。

被拒绝的结果不会写入最终 CSV，会在质量报告中标记为 `LLM_REJECTED` 或 `HUMAN_REVIEW_REQUIRED`。
