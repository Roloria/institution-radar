# 同类项目分析与本项目优化（2026-09）

## 一、调研对象

| 项目 | 类型 | 核心长处 |
|------|------|----------|
| [Dataroma](https://www.dataroma.com/) | 免费 Web（行业标杆） | 精选 ~83 位超级投资者；**个股透视**（查看某公司被哪些大师持有/买卖）；季度调仓活动流；reported price 与持仓成本参考 |
| [WhaleWisdom](https://whalewisdom.com/) | 订阅制 | 全量 13F/13D/Insider；**Overlap Matrix 机构持仓重叠矩阵**；Combined Holdings / **Double-Down 聚合视图**；回测、Excel 插件、API |
| [dokson/hedge-fund-tracker](https://github.com/dokson/hedge-fund-tracker) | 开源 Python | 13F/13D/Form4 多文件类型跟踪，AI 洞察摘要 |
| [ahwurm/13f-dashboard-hosted](https://github.com/ahwurm/13f-dashboard-hosted) | 开源 Streamlit | 13F 全管线 + 交互仪表盘，持仓随时间演变 |
| [toddwschneider/sec-13f-filings](https://github.com/toddwschneider/sec-13f-filings)（[13f.info](https://13f.info)） | 开源 Web | 极致的 13F 浏览体验、全文检索 |
| [dgunning/edgartools](https://github.com/dgunning/edgartools) | 开源库 | EDGAR Python 工具链，QoQ 对比、持仓历史 |
| [quantskills](https://github.com/quantskills/quantskills) | 开源（A 股） | **龙虎榜席位标签 → 次日关注清单**；北向行为与资金**共识/分歧**分析 |
| [tick-stock-panel](https://github.com/shy3130/tick-stock-panel) / [TradingAgents-astock](https://github.com/simonlin1212/TradingAgents-astock) | 开源（A 股） | 自托管选股+监控+回测工作台；主力/大单/解禁减持质押监控 |

## 二、本项目 vs 同类：差距

我们已有的长处（独特定位）：**全球 13F + 国内机构（龙虎榜/北向/股东/涨停）+ 7×24 快讯** 三合一；爬虫+自动更新+推送提醒闭环；自托管。

欠缺的高价值能力（按策略价值排序）：
1. **共识信号**（Dataroma 个股透视 + WhaleWisdom Double-down）：单看"巴菲特买了什么"价值有限，"≥3 家机构同季同向买入同一标的"才是强信号——原版只有按机构的视图，没有跨机构聚合。
2. **个股透视**：输入任意股票看全部机构的持有与变动（Dataroma 招牌功能）。
3. **A股联动关注清单**（quantskills 思想）：龙虎榜/北向/涨停数据只是罗列，没有形成"今天该看什么"的行动清单。
4. **公开可访问的快照站点**：数据只在本地，无法随时查看或分享。

## 三、本次优化落地

| 优化 | 对标 | 实现 |
|------|------|------|
| 🎯 共识信号页 | WhaleWisdom Double-down / Dataroma activity | `signals.py` 聚合 18 家机构同季变动：净买入机构数、新增/清仓计数、合计增减市值、机构明细；≥3 家同向自动生成告警 |
| 🔍 个股透视 | Dataroma per-stock view | `/api/stock?q=` 任意股票 → 全部机构最新持仓、变动、幅度、股数 |
| 📋 A 股今日关注 | quantskills 次日关注清单 | 信号页联动板块：北向近5日净买、龙虎榜净买榜、连板天梯 |
| 🌐 公开快照站 | — | `scripts/build_static.py` 从本地库生成静态快照 → GitHub Pages 公开访问 |

**Roadmap（后续可做）**：机构重叠矩阵（WhaleWisdom）、13D/G 与 Insider 数据（hedge-fund-tracker）、龙虎榜席位标签画像、 Reported price 持仓成本线、快照站自动化定时部署。

## 四、投资策略价值说明（如何用）

- **共识增持 + 净买入机构数 ≥3**：机构 Research 强共振，优先查看新增（新进建仓往往伴随催化剂）；配合个股透视确认是"加仓"还是"新建仓"。
- **共识清仓/减持 ≥2**：负面排除信号，持仓前检查目标股票是否在列。
- **13F 共识 × A 股联动**：13F 中概共识（如 BABA/PDD）与北向连续净买、龙虎榜机构席位净买共振时信号更强。
- **时滞提醒**：13F 有 45 天披露时滞且为季度末持仓，快讯/龙虎榜/北向是日频数据——两者结合看"机构季末观点 vs 当前市场行为"是否一致。
- 以上为研究辅助信号，不构成投资建议。
