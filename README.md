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

## Next steps
- 优化推荐算法
- 引入更多的功能
- 高度自主化设置
