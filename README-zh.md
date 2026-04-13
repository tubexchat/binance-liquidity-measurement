# bliq

**币安 USDT-M 永续合约流动性测量 CLI 工具。**

bliq 从币安获取实时订单簿数据，计算一系列流动性指标，并将结果持久化到 SQLite 中以便进行进一步分析。它专为量化研究员、做市商和需要在建仓前量化执行成本的交易者而设计。

## 特性

- **一键快照**：支持任何 USDT-M 永续合约的即时抓取
- **批量扫描**：覆盖全市场 500+ 交易对的全面扫描
- **多维指标**：计算价差 (Spread)、深度 (Depth)、订单簿不平衡度 (OBI)、滑点阶梯 (Slippage Ladder) 以及容量 (Capacity) 指标
- **实时大单检测**：通过 WebSocket `aggTrades` 流进行实时鲸鱼行为追踪
- **反向大单扫描器**：集成 Telegram 预警，检测逆势吸筹信号
- **Docker 部署**：支持一键式容器化环境搭建
- **SQLite 持久化**：采用 WAL 模式，平衡写入性能与并发读取
- **灵活配置**：通过 YAML 进行精细化配置（包括深度区间、滑点级别、OBI 层级、重试策略等）
- **频率限制感知**：具备自动退避和重试机制，确保 API 调用的稳定性

## 快速开始

### 前提条件

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)

### 安装

```bash
git clone https://github.com/<your-org>/bliq.git
cd bliq
uv sync
```

### 单个交易对快照

```bash
uv run bliq snapshot --symbols BTCUSDT
```

### 多个交易对快照

```bash
uv run bliq snapshot --symbols BTCUSDT,ETHUSDT,SOLUSDT
```

### 从文件加载交易对

```yaml
# symbols.yaml
symbols:
  - BTCUSDT
  - ETHUSDT
  - SOLUSDT
```

```bash
uv run bliq snapshot --from-file symbols.yaml
```

## 大单检测 (Whale Detection)

### 实时观察模式

实时监控指定交易对的鲸鱼活动信号：

```bash
uv run bliq watch --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 8 --large-trade 30000
```

检测 5 种核心信号类型：

| 信号 | 描述 |
|--------|-------------|
| **OBI Shift** | 两次快照间订单簿不平衡度的突然变化 |
| **Depth Pulse** | 特定价格区间的深度异常激增（3 倍以上） |
| **Cap Asymmetry** | 单向容量占据绝对主导（买卖比 > 3x） |
| **Large Trade** | 单笔成交额超过预设阈值 |
| **CVD Surge** | 累积成交量差 (CVD) 在 5 分钟窗口内显著激增 |

可选项：

| 参数 | 默认值 | 描述 |
|------|---------|-------------|
| `--interval` | 10s | 订单簿快照频率 |
| `--large-trade` | $50,000 | 大额交易报警阈值 |
| `--cvd-surge` | $200,000 | CVD 激增报警阈值 |

### 反向大单扫描器 (集成 Telegram 预警)

扫描市场热点，寻找“订单簿看跌 + 突然出现大量买单”的反向吸筹信号：

```bash
# 单次扫描
uv run bliq scan-whales --top-n 20

# 每 5 分钟循环运行
uv run bliq scan-whales --top-n 20 --loop 5
```

检测逻辑：
1. 获取 24h 行情，选取价格变动前 20 的交易对
2. 对每个交易对：获取当前订单簿 + 近期 `aggTrades`
3. 识别特征：OBI 为负（卖家主导）但存在大额买单成交
4. 发送 Markdown 格式的预警消息至 Telegram

需要配置环境变量：`TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`。

## Docker 部署

### 基础设置

1. 在项目根目录下创建 `.env` 文件：

```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

2. 一键部署：

```bash
./deploy.sh
```

该脚本会将代码同步到服务器，构建 Docker 镜像，并启动一个每 5 分钟扫描一次的容器。

### 手动 Docker 命令

```bash
docker compose up -d --build    # 启动
docker compose logs -f          # 查看日志
docker compose down             # 停止
```

## 指标说明

### 相对价差 (Relative Spread, bps)

```
(best_ask - best_bid) / mid_price * 10000
```

衡量盘口挂单的紧凑程度。数值越低，流动性越好。

### 深度区间 (Depth Bands)

统计中间价上下百分比梯度内的累积 USDT 流动性：

| 区间 | 描述 |
|------|-------------|
| +/-0.1% | 紧贴盘口的流动性 |
| +/-0.5% | 近端盘口深度 |
| +/-1.0% | 中端深度 |
| +/-2.0% | 远端深度 |

### 订单簿不平衡度 (OBI)

```
OBI = (sum(bid_qty) - sum(ask_qty)) / (sum(bid_qty) + sum(ask_qty))
```

计算前 5、10 和 20 档的 OBI。取值范围 `[-1, +1]`。正值表示买盘更重。

### 滑点阶梯 (Slippage Ladder)

模拟在不同名义价值下的市价单，报告预计的滑点（单位：bps）：

| 名义价值 (USDT) |
|-----------------|
| 1,000 |
| 5,000 |
| 10,000 |
| 50,000 |
| 100,000 |
| 500,000 |
| 1,000,000 |

买侧和卖侧将分别进行独立模拟。

### 20 bps 容量 (Capacity @ 20 bps)

在滑点超过 20 bps 之前能够执行的最大名义价值（USDT）。该指标是评估头寸规模最具参考价值的数据点。

## 示例输出

```
                           Liquidity Snapshot
┏━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ symbol  ┃      mid ┃ spread(bps) ┃  obi_5 ┃ cap_buy($) ┃ cap_sell($) ┃
┡━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ BTCUSDT │ 71,684.1 │        0.01 │ +0.392 │    419,066 │   1,100,420 │
│ ETHUSDT │ 2,217.91 │        0.05 │ -0.287 │    342,971 │     239,759 │
│ SOLUSDT │    82.18 │        1.22 │ -0.009 │  5,420,937 │   7,335,869 │
└─────────┴──────────┴─────────────┴────────┴────────────┴─────────────┘
```

## 配置指南

所有参数均可通过 `config/default.yaml` 或自定义 YAML 文件进行调整：

```bash
uv run bliq snapshot --symbols BTCUSDT --config my-config.yaml
```

核心配置项：

| 配置板块 | 控制内容 |
|---------|----------|
| `metrics.depth_pcts` | 深度区间百分比 |
| `metrics.obi_levels` | OBI 计算的档位数 |
| `metrics.slippage_levels_usdt` | 滑点阶梯的名义价值 |
| `metrics.max_slippage_bps` | 容量计算的滑点阈值（默认 20 bps） |
| `data.rate_limit_weight_per_min` | 币安 API 权重预算 |
| `data.max_concurrent_requests` | 并发请求限制 |

完整参考请查阅 [`config/default.yaml`](config/default.yaml)。

## 架构设计

```
src/bliq/
  cli/          CLI 入口点 (Typer)
  data/         币安 REST 客户端, WebSocket 客户端, 速率限制器, SQLite 存储
  metrics/      纯度指标函数 (价差、深度、OBI、滑点、鲸鱼信号)
  modes/        执行模式 (snapshot, watch, contrarian scan)
  notify/       Telegram 通知模块
  infra/        配置、日志、错误处理
```

设计原则上将数据获取、指标计算和持久化进行了严格分层。指标函数是**纯函数** —— 接收 `OrderBook` 并返回类型化结果，便于测试和组合应用。

## 路线图 (Roadmap)

| 阶段 | 状态 | 描述 |
|-----------|--------|-------------|
| M1 | 已完成 | `snapshot` —— 静态订单簿指标 |
| M2 | 已完成 | `watch` —— 通过 WebSocket 进行实时鲸鱼检测 |
| M3 | 已完成 | `scan-whales` —— 具备 Telegram 预警的反向扫描器 + Docker 部署 |
| M4 | 计划中 | `analyze` —— 历史趋势、跨交易对对比、复合 `liquidity_score` |

## 开发

```bash
uv run pytest                    # 单元测试 + 集成测试
uv run ruff check src tests      # 代码检查
uv run ruff format src tests     # 代码格式化
```

连接币安 API 的集成测试为可选：

```bash
uv run pytest -m integration
```

## 许可证

[Apache License 2.0](LICENSE)
