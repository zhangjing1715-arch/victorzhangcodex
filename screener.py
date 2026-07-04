#!/usr/bin/env python3
"""盘前选股筛选器 (Premarket Stock Screener)

流程:
  1. 将 data/seed/ 下的新闻事件与候选股写入 SQLite 数据库 (data/screener.db)
  2. 按打分模型对候选股排序:
       总分 = 催化剂强度(0-5) + 板块顺风(0-3) + 动量(0-3) + 流动性(0-2) - 风险扣分(0-3)
  3. 分档: A级(>=9 重点关注) / B级(6-8 次选) / 观察(direction=watch) / 回避(direction=avoid)
  4. 生成 plans/<日期>_premarket_plan.md 盘前计划

用法:
  python3 screener.py [--plan-date YYYY-MM-DD]
"""

import argparse
import json
import sqlite3
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "screener.db"
SEED_DIR = ROOT / "data" / "seed"
PLANS_DIR = ROOT / "plans"

SCHEMA = """
CREATE TABLE IF NOT EXISTS news_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date TEXT NOT NULL,
    source TEXT,
    headline TEXT NOT NULL,
    symbols TEXT,
    sector TEXT,
    sentiment TEXT,
    impact INTEGER,
    note TEXT
);
CREATE TABLE IF NOT EXISTS candidates (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    sector TEXT,
    direction TEXT CHECK(direction IN ('long','short','watch','avoid')),
    last_close REAL,
    catalyst TEXT,
    catalyst_strength INTEGER,
    sector_tailwind INTEGER,
    momentum INTEGER,
    liquidity INTEGER,
    risk_penalty INTEGER,
    risk_note TEXT
);
"""


def load_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    news = json.loads((SEED_DIR / "news_events.json").read_text(encoding="utf-8"))
    conn.execute("DELETE FROM news_events")
    conn.executemany(
        "INSERT INTO news_events (event_date, source, headline, symbols, sector, sentiment, impact, note)"
        " VALUES (?,?,?,?,?,?,?,?)",
        [
            (n["event_date"], n["source"], n["headline"], ",".join(n["symbols"]),
             n["sector"], n["sentiment"], n["impact"], n["note"])
            for n in news
        ],
    )

    cands = json.loads((SEED_DIR / "candidates.json").read_text(encoding="utf-8"))
    conn.execute("DELETE FROM candidates")
    conn.executemany(
        "INSERT INTO candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (c["symbol"], c["name"], c["sector"], c["direction"], c["last_close"],
             c["catalyst"], c["catalyst_strength"], c["sector_tailwind"],
             c["momentum"], c["liquidity"], c["risk_penalty"], c["risk_note"])
            for c in cands
        ],
    )
    conn.commit()
    return conn


def screen(conn: sqlite3.Connection):
    rows = conn.execute(
        """
        SELECT symbol, name, sector, direction, last_close, catalyst, risk_note,
               catalyst_strength + sector_tailwind + momentum + liquidity - risk_penalty AS score
        FROM candidates
        ORDER BY score DESC
        """
    ).fetchall()
    tier_a = [r for r in rows if r[3] == "long" and r[7] >= 10]
    tier_b = [r for r in rows if r[3] == "long" and 6 <= r[7] < 10]
    watch = [r for r in rows if r[3] == "watch"]
    avoid = [r for r in rows if r[3] == "avoid"]
    return tier_a, tier_b, watch, avoid


def fmt_rows(rows) -> str:
    lines = ["| 代码 | 名称 | 板块 | 评分 | 催化剂 | 风险提示 |", "|---|---|---|---|---|---|"]
    for sym, name, sector, _d, close, catalyst, risk, score in rows:
        px = f"（7/2收盘 ${close}）" if close else ""
        lines.append(f"| **{sym}** | {name}{px} | {sector} | {score} | {catalyst} | {risk} |")
    return "\n".join(lines)


def build_plan(conn: sqlite3.Connection, plan_date: str) -> str:
    tier_a, tier_b, watch, avoid = screen(conn)
    news = conn.execute(
        "SELECT event_date, headline, note FROM news_events ORDER BY impact DESC, event_date"
    ).fetchall()
    news_lines = "\n".join(f"- **[{d}]** {h}\n  - {note}" for d, h, note in news)

    return f"""# 盘前交易计划 — {plan_date}（周一）

> 生成时间: {date.today().isoformat()}（周六，7/3 周五美股因独立日休市，本计划针对下一交易日 7/6 周一盘前）
> 数据库: `data/screener.db` ｜ 筛选脚本: `screener.py`

## 一、周末与上周关键新闻

{news_lines}

## 二、市场基调判断

- **宏观**: 非农大幅走弱（5.7万 vs 预期11.5万）→ 加息概率下降，利率敏感与防御板块受益；道指创新高说明资金未离场、只是换仓。
- **主线**: ①防御轮动（公用事业/医疗/必需消费）；②能源地缘溢价（Brent≈$98）；③国防股受以伊冲突提振。
- **风险**: 半导体两日跌逾12%动能破位，若继续下杀可能拖累大盘情绪；下周日历清淡，中东头条与油价主导方向，波动率预计升高。

## 三、A级重点关注（评分≥10，顺势做多）

{fmt_rows(tier_a) if tier_a else "（无）"}

## 四、B级次选（评分6-9，仓位减半）

{fmt_rows(tier_b) if tier_b else "（无）"}

## 五、观察名单（需盘前确认信号）

{fmt_rows(watch) if watch else "（无）"}

## 六、回避名单

{fmt_rows(avoid) if avoid else "（无）"}

## 七、执行纪律

1. **开盘前确认**: 周一盘前复核期货方向、油价（Brent/WTI）与中东周末头条；若出现停火巩固消息，能源/国防多头逻辑降级。
2. **仓位**: A级单票不超过总仓位15%，B级不超过8%；观察名单只允许试探仓（≤3%）。
3. **止损**: 事件驱动票（RIVN/AVAV）跌破周四放量K线低点即离场；ETF类跌破5日线减半。
4. **不接飞刀**: 半导体（NVDA/SOXX）在放量企稳前一律不做左侧抄底。
5. **假日后流动性**: 长周末后首个交易日开盘半小时点差和滑点偏大，避免开盘市价单追高。
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan-date", default="2026-07-06")
    args = ap.parse_args()

    conn = load_db()
    plan = build_plan(conn, args.plan_date)
    PLANS_DIR.mkdir(exist_ok=True)
    out = PLANS_DIR / f"{args.plan_date}_premarket_plan.md"
    out.write_text(plan, encoding="utf-8")
    print(f"已生成: {out.relative_to(ROOT)}")

    tier_a, tier_b, watch, avoid = screen(conn)
    for label, rows in [("A级", tier_a), ("B级", tier_b), ("观察", watch), ("回避", avoid)]:
        print(f"{label}: {', '.join(r[0] for r in rows) or '无'}")
    conn.close()


if __name__ == "__main__":
    main()
