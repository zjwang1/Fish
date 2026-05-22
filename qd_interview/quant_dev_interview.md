# 高级 Quant Dev 面试模拟

---

## 第一轮：编程基础与 C++ 深度

### Q1: `std::move` 的本质

**问题：** 解释一下 C++ 中 `std::move` 的本质是什么？它真的"移动"了什么吗？

**考察点：**
- 右值引用（rvalue reference）
- `std::move` 只是一个类型转换（cast to rvalue reference），本身不做任何"移动"
- 移动语义（move semantics）与资源所有权转移
- move constructor / move assignment operator 的实现

---

### Q2: `std::shared_ptr` 的线程安全性

**问题：** `std::shared_ptr` 的线程安全性如何？引用计数是原子的，但对象本身呢？在多线程环境下你会怎么处理？

**考察点：**
- 引用计数（reference count）是 atomic 的
- 对象本身的访问**不是**线程安全的
- `std::atomic<std::shared_ptr>`（C++20）
- `std::mutex` 保护共享对象
- lock-free 设计思路

---

### Q3: Cache Line 与 False Sharing

**问题：** 什么是 cache line？False sharing 是什么？如何在高频交易系统中避免它？

**考察点：**
- CPU 缓存架构（L1 / L2 / L3）
- cache line 通常为 64 bytes
- False sharing：不同线程修改同一 cache line 上的不同变量，导致频繁 cache invalidation
- 解决方案：`alignas(64)` 、padding、`__cacheline_aligned`
- 结构体布局优化（hot/cold field separation）

---

### Q4: Lock-Free SPSC Queue

**问题：** 写一个 lock-free 的 SPSC（单生产者单消费者）队列。

**考察点：**
- Ring buffer 实现
- `std::atomic` 的 `memory_order_acquire` / `memory_order_release`
- 避免 false sharing（head 和 tail 分别对齐到不同 cache line）
- 无锁编程范式与 happens-before 关系

---

## 第二轮：数据结构与算法（量化场景）

### Q5: 滑动窗口中位数

**问题：** 如何高效计算一个滑动窗口内的中位数？时间复杂度是多少？

**考察点：**
- 两个堆（max-heap + min-heap）维护上下两半
- 平衡树（`std::multiset` / order-statistic tree）
- O(log n) 插入和删除
- 处理重复元素与窗口滑出

---

### Q6: 实时 VWAP 计算

**问题：** 给定一个实时的 tick 数据流，如何实时计算 VWAP（Volume Weighted Average Price）？如果需要支持时间窗口的 VWAP 呢？

**考察点：**
- 全局 VWAP：累计 `sum(price × volume) / sum(volume)`
- 滑动窗口 VWAP：deque 或 ring buffer 维护窗口内数据
- 增量计算（避免每次重新遍历）
- 浮点精度问题（避免累积误差，可用 Kahan summation）

---

### Q7: Order Book 数据结构设计

**问题：** 如何设计一个高效的 Order Book（订单簿）数据结构？支持 add、cancel、modify、match 操作。

**考察点：**
- **价格层级：** `std::map<Price, PriceLevel>` 或 sorted array（对于价格范围有限的情况）
- **每个价格层级内：** `std::list` / intrusive list 维护 FIFO 顺序
- **Order ID → Order 映射：** `std::unordered_map<OrderID, Order*>` 实现 O(1) 查找
- **时间复杂度：** add O(log N)、cancel O(1) amortized、match O(1) for best price
- **性能优化：** 内存池 / 对象池避免频繁 heap allocation、cache-friendly 布局

---

## 第三轮：系统设计与低延迟架构

### Q8: 低延迟交易系统设计

**问题：** 如何设计一个低延迟的交易系统？从网络到执行，每一层你会怎么优化？

**考察点：**

| 层次 | 优化手段 |
|------|----------|
| **网络层** | kernel bypass（DPDK / Solarflare OpenOnload）、FPGA、UDP multicast、busy polling |
| **OS 层** | CPU affinity / isolcpus、NUMA-aware memory allocation、huge pages、关闭 swap、禁用 irqbalance |
| **应用层** | lock-free 数据结构、避免动态内存分配（pre-allocate）、避免系统调用、hot path 无分支 |
| **编译层** | PGO（Profile-Guided Optimization）、LTO、`-O3 -march=native`、`likely/unlikely` hints |
| **测量** | `rdtsc`、hardware timestamps、关注延迟分布（p50/p99/p999）而非平均值 |

---

### Q9: 时间同步

**问题：** 你如何处理交易系统中的时间同步问题？

**考察点：**
- PTP（Precision Time Protocol）vs NTP — PTP 精度可达纳秒级
- Hardware timestamping（网卡级别时间戳）
- GPS clock 作为 grandmaster clock
- 交换机级时间戳（exchange-level timestamps）
- Clock drift 监控与补偿

---

### Q10: Hot-Cold Path Separation

**问题：** 什么是 "hot-cold path separation"？在交易系统中如何应用？

**考察点：**
- **热路径（Hot path）：** market data → signal generation → order submission — 极致优化，每一个 CPU cycle 都在计较
- **冷路径（Cold path）：** logging、risk check、reporting、position reconciliation — 异步处理
- 不同线程 / 不同 CPU core 隔离热冷路径
- 热路径上绝对不做 I/O、不申请内存、不加锁

---

## 第四轮：量化金融知识

### Q11: Black-Scholes 模型

**问题：** 解释一下 Black-Scholes 模型的核心假设和局限性。

**考察点：**

**核心假设：**
- 标的资产价格服从几何布朗运动（GBM）
- 波动率（σ）为常数
- 无风险利率（r）恒定
- 无交易成本、无税
- 可连续对冲

**局限性：**
- 实际市场中波动率不是常数 → volatility smile / skew
- 尾部风险被低估（fat tails）
- 不适用于美式期权（提前行权）
- 流动性假设不现实

---

### Q12: Greeks 与 Delta Hedging

**问题：** 什么是 Greeks？Delta hedging 的基本原理是什么？Gamma 风险如何管理？

**考察点：**
- **Delta (Δ)：** 期权价格对标的资产价格的一阶导数
- **Gamma (Γ)：** Delta 对标的资产价格的导数（二阶导）
- **Theta (Θ)：** 期权价格对时间的导数（时间衰减）
- **Vega (ν)：** 期权价格对波动率的敏感度
- **Rho (ρ)：** 期权价格对利率的敏感度
- Delta hedging：持有 -Δ 份标的资产来对冲期权头寸
- Gamma 风险：大 Gamma 意味着 Delta 变化快，需要频繁再平衡 → 交易成本增加
- Gamma scalping 策略

---

### Q13: 蒙特卡洛定价

**问题：** 如何用蒙特卡洛方法对一个路径依赖期权（如亚式期权）定价？如何提高模拟精度？

**考察点：**
- 模拟路径：离散化 GBM → `S(t+dt) = S(t) * exp((r - σ²/2)*dt + σ*sqrt(dt)*Z)`
- 随机数生成：Mersenne Twister / Sobol 序列（准蒙特卡洛）
- **方差缩减技术：**
  - 对偶变量法（Antithetic variates）
  - 控制变量法（Control variates）
  - 重要性采样（Importance sampling）
  - 分层采样（Stratified sampling）
- 收敛速度：标准 MC 为 O(1/√N)，准 MC 可达 O(1/N)

---

## 第五轮：概率与数学

### Q14: 连续正面问题

**问题：** 你抛一枚公平硬币，直到连续出现两次正面为止。期望抛多少次？

**解法：**
设状态：
- S₀：初始状态（没有连续 H）
- S₁：上一次是 H
- S₂：连续两次 H（终止）

递推关系：
- E₀ = 1 + ½·E₁ + ½·E₀
- E₁ = 1 + ½·0 + ½·E₀ （连续两个 H 则结束，否则回到 S₀）

解得：**E₀ = 6**

---

### Q15: 轮流掷骰子

**问题：** 两个人轮流掷骰子，先掷出 6 的人赢。先手的获胜概率是多少？

**解法：**
- 先手第一轮赢的概率：1/6
- 如果都没掷出 6（概率 5/6 × 5/6 = 25/36），回到等价的初始状态

P = 1/6 + (25/36)·P

P = (1/6) / (1 - 25/36) = (1/6) / (11/36) = **6/11 ≈ 0.545**

---

### Q16: Itô's Lemma

**问题：** 解释 Itô's Lemma，以及它和普通微积分链式法则的区别。

**考察点：**
- 普通链式法则：`df = f'(x)·dx`
- Itô's Lemma（随机微积分）：`df = f'(x)·dx + ½·f''(x)·(dx)²`
- 关键区别：布朗运动的二次变分 `(dW)² = dt`（非零！）
- 额外的 `½σ²f''` 项来自于此
- 应用：推导 Black-Scholes PDE、对数正态分布的推导

---

## 第六轮：Behavioral / System Thinking

### Q17: 性能优化经验

**问题：** 描述你做过的最有挑战性的性能优化项目。瓶颈是什么？你怎么定位和解决的？

**考察点：**
- Profiling 方法论：`perf`、Intel VTune、flamegraph
- 量化改进效果（延迟降低了多少？吞吐量提高了多少？）
- 权衡取舍（可读性 vs 性能、开发时间 vs 优化收益）
- 系统性思维 vs 过早优化

---

### Q18: 延迟毛刺排查

**问题：** 生产环境中你的交易系统出现了异常延迟毛刺（latency spike），你如何排查？

**排查清单：**

| 检查项 | 工具 / 方法 |
|--------|------------|
| GC 暂停（如有 Java 组件） | GC logs、`-XX:+PrintGCDetails` |
| Page fault / TLB miss | `perf stat`、`/proc/pid/status` 中的 `minflt/majflt` |
| Context switch | `/proc/pid/status`、`perf sched` |
| Network jitter | `tcpdump`、网卡统计、交换机延迟 |
| Kernel interrupt | `/proc/interrupts`、`/proc/softirqs` |
| CPU frequency scaling | `cpupower frequency-info`、确保 performance governor |
| NUMA cross-node access | `numastat`、`numactl --hardware` |
| 具体环节定位 | 时间戳埋点、`rdtsc` 打点 |

---

## 准备建议

1. **C++ 底层**：重点掌握内存模型、move 语义、模板元编程、lock-free 编程
2. **算法**：LeetCode 之外，关注量化场景特有的数据结构（order book、time series）
3. **系统设计**：理解从网卡到 CPU 的完整数据路径，能画出端到端的架构图
4. **量化金融**：至少掌握 BSM、Greeks、基本定价方法
5. **数学**：概率论（条件期望、马尔可夫链）、随机过程（布朗运动、Itô 积分）
6. **实战**：能讲清楚自己做过的项目，用数据说话
