# 盘前选股筛选系统 (Premarket Stock Screener)

基于"周末/隔夜新闻催化剂 + 板块轮动 + 动量确认"的盘前选股工作流。

## 结构

```
data/seed/news_events.json   # 新闻事件库（每个周末/盘前更新）
data/seed/candidates.json    # 候选股及各维度打分
data/screener.db             # SQLite 数据库（由脚本生成，不入库）
screener.py                  # 筛选脚本：建库 → 打分 → 生成盘前计划
plans/                       # 生成的盘前计划
```

## 打分模型

```
总分 = 催化剂强度(0-5) + 板块顺风(0-3) + 动量(0-3) + 流动性(0-2) - 风险扣分(0-3)
```

- **A级**（≥10 且方向为 long）: 重点关注，顺势做多
- **B级**（6-9）: 次选，仓位减半
- **watch**: 需盘前信号确认
- **avoid**: 回避

## 用法

```bash
# 1. 更新 data/seed/ 下的新闻与候选股
# 2. 运行筛选
python3 screener.py --plan-date 2026-07-06
# 3. 查看 plans/2026-07-06_premarket_plan.md
```

无第三方依赖（仅 Python 标准库 sqlite3/json）。
