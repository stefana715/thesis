# TASKS.md — Claude Code 任务清单

> 请先阅读根目录的 CLAUDE.md 了解项目全貌，再按以下顺序执行任务。
> 每完成一个任务，在对应条目前标注 ✅ 并简要说明输出文件路径。

---

## 阶段 0：项目熟悉（先做这一步）

- [ ] 阅读 `CLAUDE.md`，确认理解项目定位
- [ ] 扫描 `src/`、`code/`、`notebooks/` 目录，列出所有现有脚本及其功能
- [ ] 扫描 `data/` 和 `outputs/` 目录，列出所有现有数据文件及其内容摘要
- [ ] 扫描 `configs/` 目录，列出所有配置文件
- [ ] 确认 pipeline 当前可以从头到尾运行（如不能，记录卡点）

完成后输出一份简短的**项目现状报告**，包含：现有脚本清单、数据清单、pipeline 是否可运行。

---

## 阶段 1：敏感性分析脚本（优先级最高）

### 1.1 网格尺寸敏感性

- [ ] 创建 `src/sensitivity/grid_size_sensitivity.py`
- [ ] 功能：用 250m / 500m / 750m / 1000m 四种网格尺寸重跑网格聚合
- [ ] 每种网格输出：occupied grids 数量、mean_solar_score 分布统计、high_potential_ratio 分布统计
- [ ] 输出汇总 CSV 到 `outputs/sensitivity/grid_size_comparison.csv`
- [ ] 生成对比箱线图到 `figure/fig06_grid_size_sensitivity.png`

### 1.2 阈值敏感性

- [ ] 创建 `src/sensitivity/threshold_sensitivity.py`
- [ ] 功能：用 q50 / q55 / q60 / q66 / q70 / q75 / q80 多个分位数阈值重跑高潜力分类
- [ ] 每个阈值输出：高潜力建筑数量、高潜力建筑占比、grid 层面 high_potential_ratio 均值
- [ ] 输出汇总 CSV 到 `outputs/sensitivity/threshold_comparison.csv`
- [ ] 生成阈值-数量曲线图到 `figure/fig07_threshold_sensitivity.png`

### 1.3 高度代理敏感性

- [ ] 创建 `src/sensitivity/height_proxy_sensitivity.py`
- [ ] 功能：对建筑高度估值施加 ±10%、±20%、±30% 扰动，重跑评分
- [ ] 输出：扰动后的 mean score 变化、高潜力建筑数量变化
- [ ] 输出汇总 CSV 到 `outputs/sensitivity/height_proxy_comparison.csv`
- [ ] 生成扰动-变化关系图到 `figure/fig_height_sensitivity.png`

---

## 阶段 2：核心论文图表生成（共 8 张）

### 2.1 研究区域地图
- [ ] 创建 `src/visualization/fig01_study_area.py`
- [ ] 内容：长沙全域边界 + 提取后的城市核心区叠加显示
- [ ] 要求：标注比例尺、指北针、图例
- [ ] 输出到 `figure/fig01_study_area.png`（300 dpi）

### 2.2 建筑评分直方图
- [ ] 创建 `src/visualization/fig02_score_distribution.py`
- [ ] 内容：18,855 栋建筑的 solar_potential_score 频率直方图
- [ ] 要求：标注 q33 (41.797) 和 q66 (45.513) 两条垂直切割线，标注 low/medium/high 区域
- [ ] 输出到 `figure/fig02_score_distribution.png`（300 dpi）

### 2.3 高潜力建筑空间分布
- [ ] 创建 `src/visualization/fig03_building_classification.py`
- [ ] 内容：地图上用三种颜色标注 low / medium / high 建筑
- [ ] 输出到 `figure/fig03_building_classification.png`（300 dpi）

### 2.4 网格均分热力图
- [ ] 创建 `src/visualization/fig04_grid_mean_score.py`
- [ ] 内容：500m 网格 mean_solar_score choropleth 地图
- [ ] 要求：连续色带（如 YlOrRd），标注比例尺和图例
- [ ] 输出到 `figure/fig04_grid_mean_score.png`（300 dpi）

### 2.5 高潜力比率热力图
- [ ] 创建 `src/visualization/fig05_high_potential_ratio.py`
- [ ] 内容：500m 网格 high_potential_ratio choropleth 地图
- [ ] 输出到 `figure/fig05_high_potential_ratio.png`（300 dpi）

### 2.6 网格尺寸敏感性对比图
- [ ] 在阶段 1.1 中已生成 `figure/fig06_grid_size_sensitivity.png`
- [ ] 确认图表清晰、可用于论文

### 2.7 阈值敏感性曲线
- [ ] 在阶段 1.2 中已生成 `figure/fig07_threshold_sensitivity.png`
- [ ] 确认图表清晰、可用于论文

### 2.8 方法流程总图
- [ ] 创建 `src/visualization/fig08_methodology_flowchart.py`
- [ ] 内容：从 OSM 数据获取 → 高度代理 → 核心区提取 → 建筑评分 → q66 分类 → 网格聚合 的全流程示意图
- [ ] 可以用 matplotlib + 手动绘制，或者生成 SVG
- [ ] 输出到 `figure/fig08_methodology_flowchart.png`（300 dpi）

---

## 阶段 3：规划指标转换层

- [ ] 创建 `src/planning/planning_metrics.py`
- [ ] 功能：
  - 从高潜力建筑提取可部署屋顶面积（footprint area × 利用系数，如 0.6-0.7）
  - 估算年发电量：可部署面积 × 太阳能面板效率 × 长沙年均太阳辐照量
  - 估算 CO₂ 减排量：年发电量 × 电网排放因子
  - 识别优先部署网格（high_potential_ratio 排名前 N%）
- [ ] 输出汇总表到 `outputs/planning_metrics_summary.csv`
- [ ] 输出优先网格列表到 `outputs/priority_grids.csv`

---

## 阶段 4：外部验证（如有条件）

- [ ] 创建 `src/validation/benchmark_comparison.py`
- [ ] 选取 2-3 个小区域，用 pvlib 逐栋模拟作为基准
- [ ] 对比快速筛选结果与基准结果的排名一致性（Spearman 相关系数）
- [ ] 输出对比结果到 `outputs/validation/benchmark_results.csv`
- [ ] 生成对比散点图到 `figure/fig_validation_scatter.png`

> 注意：这一步需要更详细的辐照数据，如果条件不允许，可以先跳过，在论文中列为 future work。

---

## 阶段 5：论文文本辅助

- [ ] 基于以上所有输出，协助撰写 Methods 章节草稿 → `docs/draft_methods.md`
- [ ] 基于所有图表和数据，协助撰写 Results 章节草稿 → `docs/draft_results.md`
- [ ] 协助撰写 Discussion 章节草稿 → `docs/draft_discussion.md`

写作要求：
- 使用英文学术论文风格
- 定位为 rapid screening framework
- 不要 overclaim 物理精度
- 强调 reproducible, open-data, planning-oriented

---

## 执行顺序建议

```
阶段 0（熟悉项目）
  ↓
阶段 1（敏感性分析） ← 最优先，产出新数据
  ↓
阶段 2（图表生成） ← 有了数据就可以画图
  ↓
阶段 3（规划指标） ← 增强论文实用性
  ↓
阶段 4（外部验证） ← 如有条件
  ↓
阶段 5（论文写作） ← 所有数据和图表就绪后
```

---

## 注意事项

1. **不要修改现有 pipeline 的核心评分逻辑**，它已经验证通过
2. 所有新脚本放在 `src/` 对应子目录下
3. 参数尽量从 `configs/` 读取，不要硬编码
4. 图表统一 300 dpi，字体大小适合期刊排版（标题 14pt，标签 12pt，刻度 10pt）
5. 每个脚本都要有 docstring 和基本的 logging
