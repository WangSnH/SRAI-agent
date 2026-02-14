# Science Rearch Ai Agent

一个利用prompt和土豆服务器上简单训练来达到更好利用ai进行科研的工具:
- 友好的可视化交互界面
- 通过堆叠prompt和反复调用api引导ai更好的执行任务
- 较高的可拓展性和自主配置

## Run
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m paperscout
```

## Acknowledge
目前还处于测试阶段，仅仅包含了从arxiv上爬取并排序，显示关键信息的功能

## 系统参数简介
在设置窗口的「系统参数」页面可调整初始化流程行为：

- `最终输出论文数量`：最终整理输出的论文条数。
- `arXiv API 输出论文数量`：实际抓取的论文上限。
- `权重 relevance/novelty/recency/citation`：相关性、创新性、时间新近性、引用的权重；系统会自动归一化。
- `语义筛选模型`：sentence-transformers 模型下拉选择（如 `BAAI/bge-large-en-v1.5`、`all-MiniLM-L6-v2`）。

## 使用说明（简版）
1. 启动程序后，点击右上角「设置」。
2. 进入「系统参数」，按需求调整数量参数、权重和语义筛选模型。
3. 点击「确认保存」。
4. 点击新建，在对话框里输入想要了解的领域即可自动爬取，爬取后转为一般的对话模型，会读取记忆并对话。

## Next steps
- 优化推荐算法
- 引入更多的功能
- 高度自主化设置
