from __future__ import annotations

# 新建会话时：用于生成 arXiv API 查询参数（第一个 OpenAI Prompt）
OPENAI_ARXIV_API_SYSTEM_PROMPT = (
    "你是 arXiv 检索参数生成助手。"
)

OPENAI_ARXIV_API_PROMPT_TEMPLATE = (
    "请为当前会话生成 arXiv 查询参数。\n"
    "功能: {feature_key}\n"
    "会话名: {thread_name}\n\n"
    "原始输入: {original_input}\n\n"
    "输出要求：\n"
    "1) 只输出 JSON，对象结构必须是："
    "{{\"arxiv\": {{\"categories\": [\"...\"], \"keywords\": [\"...\"], \"max_results\": 20}}}}\n"
    "2) categories 需使用 arXiv 分类（如 cs.AI/cs.LG），最多 2 个。\n"
    "3) keywords 提供英文关键词，最多 2 个。\n"
    "4) max_results 默认值使用 {default_max_results}。\n"
    "5) 禁止输出 Markdown 代码块。\n"
    "示例（仅示意内容，不要照抄）：\n"
    "输入：为我查询若干条基于transformer的大语言模型相关论文。\n"
    "输出(JSON)：{{\"arxiv\":{{\"categories\":[\"cs.AI\",\"cs.LG\"],\"keywords\":[\"large language model\",\"transformer\"],\"max_results\":40}}}}"
)


OPENAI_ARXIV_COMPARE_SYSTEM_PROMPT = (
    "你是论文相关性评估助手。"
    "你需要将候选论文摘要与用户原始输入进行对比，并严格按“相关性优先，其次创新性，最后时间新近度”的顺序打分与排序。"
)

OPENAI_ARXIV_COMPARE_PROMPT_TEMPLATE = (
    "请根据原始输入，评估候选论文是否匹配需求，并输出 JSON。\n"
    "原始输入: {original_input}\n"
    "候选论文(JSON数组): {papers_json}\n\n"
    "输出要求：\n"
    "1) 只输出 JSON，结构必须为："
    "{{\"summary\":\"...\",\"top_matches\":[{{\"id\":\"...\",\"title\":\"...\",\"reason\":\"...\",\"score\":0.0,\"score_details\":{{\"relevance\":0.0,\"recency\":0.0,\"novelty\":0.0,\"citation\":0.0}}}}],\"selected_ids\":[\"...\"]}}\n"
    "2) 对每篇论文按四个维度评分（0~1）：relevance(与原始输入相关性)、novelty(方法创新性)、recency(发布时间新近度)、citation(引用影响力)。\n"
    "3) 总分 score 也在 0~1，并按以下权重计算：score = {w_relevance}*relevance + {w_novelty}*novelty + {w_recency}*recency + {w_citation}*citation。\n"
    "4) 最终排序必须先看 relevance，再看 novelty，再看 recency；citation 仅作弱辅助，不可主导排序。\n"
    "5) 必须只保留并返回总分最高的 5 篇（top_matches 长度固定为 5，候选不足时按实际数量）。\n"
    "6) 如果 citation_count 缺失，请按 0.5 的中性分处理 citation 维度。\n"
    "7) 禁止输出 Markdown 代码块。"
)


OPENAI_ARXIV_ORGANIZE_SYSTEM_PROMPT = (
    "你是中文学术综述助手。"
    "请基于已筛选论文，输出结构化、可读性强的中文整理结果。"
    "行文与排序请严格遵循：相关性优先，其次创新性，最后时间新近度。"
)

OPENAI_ARXIV_ORGANIZE_PROMPT_TEMPLATE = (
    "请将第二个 prompt 的筛选结果和论文原始信息整理为中文 Markdown。\n"
    "原始需求: {original_input}\n"
    "评分权重: relevance={w_relevance}, novelty={w_novelty}, recency={w_recency}, citation={w_citation}\n"
    "第二个Prompt结果(JSON): {compare_result_json}\n"
    "论文数据(JSON数组): {papers_json}\n\n"
    "输出要求（必须全部满足）：\n"
    "1) 全部使用中文，不要输出英文说明。\n"
    "2) 输出清晰排版的 Markdown（标题、分节、项目符号），缩进统一使用两个空格。\n"
    "3) 对每篇论文都包含：\n"
    "   - 文章题目\n"
    "   - 发表时期（从 published 提取）\n"
    "   - 引用量（citation_count；若缺失写“未提供”）\n"
    "   - 文章摘要（精炼重述）\n"
    "   - 简要点评（2~3 句）\n"
    "   - 可直达链接（url）\n"
    "4) 先给一个“总体总结点评”，再分条列出论文；论文顺序必须按“相关性 > 创新性 > 时间”排列。\n"
    "5) 每篇论文的“简要点评”必须按同一顺序展开：先写相关性，再写创新性，最后写时间因素。\n"
    "6) 避免废话，重点突出与原始需求的相关性。\n"
    "7) 禁止输出 Markdown 代码块。\n\n"
    "输出模板（请严格按此结构）：\n"
    "# 论文筛选整理报告\n\n"
    "## 总体总结点评\n"
    "- （这里用中文写 3~5 条总结）\n\n"
    "## 论文清单\n"
    "### 论文 1：[题目]\n"
    "- 文章题目：[题目]\n"
    "- 发表时期：[时期]\n"
    "- 引用量：[引用量]\n"
    "- 文章摘要：\n"
    "  [中文摘要]\n"
    "- 简要点评：\n"
    "  [中文点评（2~3句）]\n"
    "- 可直达链接：[URL]\n\n"
    "### 论文 2：[题目]\n"
    "- 文章题目：[题目]\n"
    "- 发表时期：[时期]\n"
    "- 引用量：[引用量]\n"
    "- 文章摘要：\n"
    "  [中文摘要]\n"
    "- 简要点评：\n"
    "  [中文点评（2~3句）]\n"
    "- 可直达链接：[URL]\n"
)
