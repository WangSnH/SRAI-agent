# Science Rearch Ai Agent

一个利用prompt和土豆服务器上简单训练来达到更好利用ai进行科研的工具:
- 友好的可视化交互界面
- 通过堆叠prompt和反复调用api引导ai更好的执行任务
- 较高的可拓展性和自主配置

ps：本项目希望通过堆叠prompt和合理的流程以及简单的微调引导廉价的模型达到更好的效果，可以把它理解为低配的skill。好处就是便宜，适合穷哥们。

## 运行
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -U pip
# 推荐：安装为可编辑包（会自动安装依赖）
pip install -e .
paperscout

# 或者：不安装包，直接运行（需要显式设置 PYTHONPATH）
# pip install -r requirements.txt
# PYTHONPATH=src python -m paperscout
```

## Acknowledge
目前还处于测试阶段
## 系统参数简介
在设置窗口的「系统参数」页面可调整初始化流程行为：

- `最终输出论文数量`：最终整理输出的论文条数。
- `arXiv API 输出论文数量`：实际抓取的论文上限。
- `权重 relevance/novelty/recency/citation`：相关性、创新性、时间新近性、引用的权重；系统会自动归一化。
- `语义筛选模型`：sentence-transformers 模型下拉选择（如 `BAAI/bge-large-en-v1.5`、`all-MiniLM-L6-v2`）。

## 预训练权重目录
- 语义筛选用的 sentence-transformers 预训练权重会统一下载到独立目录：
  - macOS: `~/Library/Application Support/PaperScout/pretrained_weights/sentence_transformers/`
  - 说明：程序会自动创建该目录，不会和代码目录混在一起。
- 如需改成项目内目录，可在启动前设置环境变量：
  - `export PAPERSCOUT_PRETRAINED_DIR="/Users/wangtan/Desktop/LLM_AGENT/pretrained_weights"`

## 使用说明（简版）
1. 启动程序后，点击右上角「设置」。
2. 进入「系统参数」，按需求调整数量参数、权重和ai模型的配置。
3. 点击「确认保存」。
4. 点击新建，在对话框里输入想要了解的领域即可自动爬取，爬取后转为一般的对话模型，会读取记忆并对话。
5. 新增中译英任务，可以自动判断并且翻译和按照要求修改润色

## Next steps
- 优化推荐算法
- 引入更多的功能
- 高度自主化设置
