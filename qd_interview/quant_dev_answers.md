# Quant Dev 面试 — 标准答案详解

---

## Q1: `std::move` 的本质

### 标准答案

`std::move` **本身不做任何移动操作**。它只是一个 `static_cast`，把左值（lvalue）强制转换为右值引用（rvalue reference），从而让编译器选择移动构造函数或移动赋值运算符（如果存在的话）。

**源码本质（简化版）：**
```cpp
template <typename T>
typename std::remove_reference<T>::type&& move(T&& arg) noexcept {
    return static_cast<typename std::remove_reference<T>::type&&>(arg);
}
```

**完整回答要点：**

1. **`std::move` 是一个无条件的 cast**：它不检查对象是否可以移动，只是告诉编译器"你可以把这个当右值来用"。
2. **真正的"移动"发生在移动构造函数/移动赋值运算符里**：通常是把源对象的资源指针"偷"过来，然后把源对象的指针置为 nullptr。
3. **移动之后源对象处于"有效但未指定"的状态（valid but unspecified）**：你可以析构它或赋新值，但不应该读取它的内容。
4. **如果类没有移动构造函数，`std::move` 后会退化为拷贝**：编译器会选择拷贝构造函数，不会报错。

**示例：**
```cpp
std::string a = "hello";
std::string b = std::move(a);  // a 被"移动"到 b
// 此时 a 处于有效但未指定状态（通常为空字符串）
// b == "hello"
```

**面试加分点：**
- 提到 `std::forward` 与 `std::move` 的区别：`forward` 是条件性转发（完美转发），`move` 是无条件转换
- 提到 move semantics 对容器操作（如 `push_back`、`emplace_back`）的性能提升
- 知道 `noexcept` 对移动操作的重要性（`std::vector` 扩容时，只有 `noexcept` 的移动构造函数才会被调用，否则退化为拷贝）

---

## Q2: `std::shared_ptr` 的线程安全性

### 标准答案

**引用计数是线程安全的，但被管理对象的访问不是。**

具体来说，`shared_ptr` 有三个层次的线程安全问题：

**1. 引用计数（Reference Count）— 线程安全 ✓**
```cpp
// 以下操作是线程安全的（引用计数用 atomic 实现）：
std::shared_ptr<Foo> global_ptr = std::make_shared<Foo>();

// 线程1：拷贝 shared_ptr
auto local1 = global_ptr;  // 引用计数原子 +1

// 线程2：析构 shared_ptr
local2.reset();  // 引用计数原子 -1
```

**2. shared_ptr 对象本身的读写 — 不是线程安全 ✗**
```cpp
std::shared_ptr<Foo> ptr = std::make_shared<Foo>();

// 两个线程同时修改同一个 shared_ptr 变量 → 数据竞争！
// 线程1：
ptr = another_ptr;
// 线程2：
ptr = yet_another_ptr;
```

**3. 被管理对象（pointee）的访问 — 不是线程安全 ✗**
```cpp
auto ptr = std::make_shared<std::vector<int>>();

// 线程1：
ptr->push_back(1);   // 修改被管理对象
// 线程2：
ptr->push_back(2);   // 数据竞争！
```

**解决方案：**

| 方案 | 适用场景 |
|------|----------|
| `std::mutex` 保护 | 最通用，保护 shared_ptr 自身和/或被管理对象 |
| `std::atomic<std::shared_ptr<T>>`（C++20） | 保护 shared_ptr 对象本身的并发读写 |
| `std::atomic_load / atomic_store`（C++11） | C++20 之前的替代方案 |
| 避免共享 — 按值传递 | 每个线程持有自己的 shared_ptr 拷贝 |
| 使用 immutable 对象 | 被管理对象只读，无需加锁 |

**面试加分点：**
- `std::make_shared` vs `new` + `shared_ptr`：`make_shared` 把控制块和对象放在同一块内存，减少一次 allocation，更 cache-friendly
- `weak_ptr` 的作用：打破循环引用、安全观察
- 在 HFT 系统中通常**避免 shared_ptr**，因为原子操作有开销，倾向于使用 unique_ptr 或 raw pointer + 手动生命周期管理

---

## Q3: Cache Line 与 False Sharing

### 标准答案

**Cache Line 基础：**

现代 CPU 不是按字节访问内存的，而是按 **cache line**（通常 64 bytes）为单位从主存加载到 CPU 缓存（L1/L2/L3）。CPU 缓存层次：

```
CPU Core 0          CPU Core 1
  ├─ L1 (32KB, ~1ns)  ├─ L1 (32KB, ~1ns)
  ├─ L2 (256KB, ~4ns)  ├─ L2 (256KB, ~4ns)
  └─────── L3 (shared, 8MB+, ~10ns) ──────┘
                    ↓
              Main Memory (~100ns)
```

**False Sharing 原理：**

当两个线程分别读写**不同的变量**，但这些变量恰好位于**同一个 cache line** 上时，就会发生 false sharing：

```
Cache Line (64 bytes):
[  counter_A  |  padding...  |  counter_B  ]
   Thread 1 写       ↑           Thread 2 写
                     ↑
              虽然是不同的变量，但在同一 cache line
              → 一个线程写入会 invalidate 另一个线程的 cache
              → 两个 core 不断通过 MESI 协议互相争夺这条 cache line
```

**性能影响：** False sharing 可以让多线程程序的性能**比单线程更差**，因为 cache line 在两个 core 之间不断"乒乓"。

**解决方案：**

```cpp
// ❌ 有 false sharing 风险
struct Counters {
    std::atomic<int64_t> counter_a;  // Thread 1 用
    std::atomic<int64_t> counter_b;  // Thread 2 用
    // counter_a 和 counter_b 在同一 cache line 上！
};

// ✅ 方案1：alignas 对齐
struct Counters {
    alignas(64) std::atomic<int64_t> counter_a;
    alignas(64) std::atomic<int64_t> counter_b;
};

// ✅ 方案2：手动 padding
struct Counters {
    std::atomic<int64_t> counter_a;
    char pad[64 - sizeof(std::atomic<int64_t>)];
    std::atomic<int64_t> counter_b;
};

// ✅ 方案3：C++17 hardware_destructive_interference_size
struct alignas(std::hardware_destructive_interference_size) AlignedCounter {
    std::atomic<int64_t> value;
};
```

**面试加分点：**
- 提到 MESI 协议（Modified / Exclusive / Shared / Invalid）
- 用 `perf c2c` 工具检测 false sharing
- 在 SPSC queue 中，head 和 tail 必须分别对齐到不同 cache line

---

## Q4: Lock-Free SPSC Queue

### 标准答案

```cpp
#include <atomic>
#include <array>
#include <optional>
#include <cstddef>

template <typename T, size_t Capacity>
class SPSCQueue {
public:
    bool push(const T& item) {
        const size_t curr_tail = tail_.load(std::memory_order_relaxed);
        const size_t next_tail = (curr_tail + 1) % Capacity;

        // 队列满了？
        if (next_tail == head_.load(std::memory_order_acquire)) {
            return false;
        }

        buffer_[curr_tail] = item;
        tail_.store(next_tail, std::memory_order_release);
        return true;
    }

    std::optional<T> pop() {
        const size_t curr_head = head_.load(std::memory_order_relaxed);

        // 队列空了？
        if (curr_head == tail_.load(std::memory_order_acquire)) {
            return std::nullopt;
        }

        T item = buffer_[curr_head];
        head_.store((curr_head + 1) % Capacity, std::memory_order_release);
        return item;
    }

private:
    std::array<T, Capacity> buffer_;

    // 关键：head 和 tail 对齐到不同 cache line，避免 false sharing
    alignas(64) std::atomic<size_t> head_{0};
    alignas(64) std::atomic<size_t> tail_{0};
};
```

**设计要点详解：**

1. **为什么不需要锁？**
   - 只有一个线程写 `tail_`（生产者），只有一个线程写 `head_`（消费者）
   - 不存在 write-write 竞争
   - 通过 `acquire-release` 语义保证 happens-before 关系

2. **Memory Order 解释：**
   - `memory_order_relaxed`：读自己独占的变量（head 只有消费者写，tail 只有生产者写）
   - `memory_order_acquire`：读对方的变量（确保看到对方之前的所有写入）
   - `memory_order_release`：写自己的变量（确保之前的所有写入对对方可见）

3. **避免 false sharing：**
   - `head_` 和 `tail_` 用 `alignas(64)` 分别对齐到不同 cache line

4. **容量浪费一个槽位：**
   - Ring buffer 中 `head == tail` 表示空，`(tail + 1) % Cap == head` 表示满
   - 牺牲一个槽位来区分空和满，避免额外的 size 计数器

**面试加分点：**
- 提到真实世界的实现（如 Folly's ProducerConsumerQueue、Boost.Lockfree）
- 讨论 `Capacity` 设为 2 的幂可以用位运算替代取模（`& (Capacity - 1)`）
- 讨论 MPMC（多生产者多消费者）队列的额外复杂性（需要 CAS 操作）

---

## Q5: 滑动窗口中位数

### 标准答案

**方法一：双堆法（最常用）**

维护两个堆：
- `max_heap`：存放较小的一半（堆顶 = 左半部分的最大值）
- `min_heap`：存放较大的一半（堆顶 = 右半部分的最小值）

```cpp
#include <queue>
#include <unordered_map>

class SlidingWindowMedian {
    std::priority_queue<int> max_heap;                             // 左半部分
    std::priority_queue<int, std::vector<int>, std::greater<>> min_heap;  // 右半部分
    std::unordered_map<int, int> to_remove;  // 延迟删除表
    int max_heap_size = 0, min_heap_size = 0;

    void balance() {
        // 保证 max_heap 的有效元素 >= min_heap 的有效元素
        if (max_heap_size > min_heap_size + 1) {
            min_heap.push(max_heap.top());
            max_heap.pop();
            max_heap_size--;
            min_heap_size++;
        } else if (min_heap_size > max_heap_size) {
            max_heap.push(min_heap.top());
            min_heap.pop();
            min_heap_size--;
            max_heap_size++;
        }
        // 清理堆顶的已删除元素
        prune(max_heap);
        prune(min_heap);
    }

    template <typename Heap>
    void prune(Heap& heap) {
        while (!heap.empty() && to_remove.count(heap.top()) && to_remove[heap.top()] > 0) {
            to_remove[heap.top()]--;
            if (to_remove[heap.top()] == 0) to_remove.erase(heap.top());
            heap.pop();
        }
    }

public:
    double getMedian() {
        if (max_heap_size > min_heap_size)
            return max_heap.top();
        return (max_heap.top() + min_heap.top()) / 2.0;
    }

    void addNum(int num) {
        if (max_heap.empty() || num <= max_heap.top()) {
            max_heap.push(num);
            max_heap_size++;
        } else {
            min_heap.push(num);
            min_heap_size++;
        }
        balance();
    }

    void removeNum(int num) {
        to_remove[num]++;
        if (num <= max_heap.top()) {
            max_heap_size--;
        } else {
            min_heap_size--;
        }
        balance();
    }
};
```

**时间复杂度：**
- 插入：O(log n)
- 删除：O(log n)（延迟删除）
- 获取中位数：O(1)

**方法二：`std::multiset`（代码更简洁）**

```cpp
class SlidingWindowMedian {
    std::multiset<int> window;
    std::multiset<int>::iterator mid;

public:
    void addNum(int num) {
        window.insert(num);
        if (window.size() == 1) {
            mid = window.begin();
        } else if (num < *mid) {
            if (window.size() % 2 == 0) --mid;  // 偶数个元素，mid 左移
        } else {
            if (window.size() % 2 != 0) ++mid;  // 奇数个元素，mid 右移
        }
    }

    void removeNum(int num) {
        auto it = window.find(num);
        if (it == mid) {
            // 需要先移动 mid 再删除
            if (window.size() % 2 != 0) ++mid;
            else --mid;
        } else if (*it < *mid) {
            if (window.size() % 2 != 0) ++mid;
        } else {
            if (window.size() % 2 == 0) --mid;
        }
        window.erase(it);
    }

    double getMedian() {
        if (window.size() % 2 != 0) return *mid;
        return (*mid + *std::next(mid)) / 2.0;
    }
};
```

---

## Q6: 实时 VWAP 计算

### 标准答案

**VWAP 公式：** `VWAP = Σ(Pᵢ × Vᵢ) / Σ(Vᵢ)`

**全局 VWAP（简单累计）：**

```cpp
class VWAP {
    double sum_pv = 0.0;  // Σ(price × volume)
    double sum_v = 0.0;   // Σ(volume)

public:
    void onTick(double price, double volume) {
        sum_pv += price * volume;
        sum_v += volume;
    }

    double getVWAP() const {
        return sum_v > 0 ? sum_pv / sum_v : 0.0;
    }
};
```

**滑动窗口 VWAP：**

```cpp
#include <deque>

struct Tick {
    int64_t timestamp;
    double price;
    double volume;
};

class WindowVWAP {
    std::deque<Tick> window_;
    double sum_pv_ = 0.0;
    double sum_v_ = 0.0;
    int64_t window_size_ns_;  // 窗口大小（纳秒）

public:
    explicit WindowVWAP(int64_t window_ns) : window_size_ns_(window_ns) {}

    void onTick(const Tick& tick) {
        // 加入新 tick
        window_.push_back(tick);
        sum_pv_ += tick.price * tick.volume;
        sum_v_ += tick.volume;

        // 移除过期 tick
        while (!window_.empty() &&
               tick.timestamp - window_.front().timestamp > window_size_ns_) {
            sum_pv_ -= window_.front().price * window_.front().volume;
            sum_v_ -= window_.front().volume;
            window_.pop_front();
        }
    }

    double getVWAP() const {
        return sum_v_ > 0 ? sum_pv_ / sum_v_ : 0.0;
    }
};
```

**浮点精度问题与 Kahan Summation：**

当累积大量浮点数时，普通的 `+=` 会产生累积误差。Kahan summation 通过一个补偿变量来减少误差：

```cpp
class KahanAccumulator {
    double sum_ = 0.0;
    double compensation_ = 0.0;  // 补偿项

public:
    void add(double value) {
        double y = value - compensation_;
        double t = sum_ + y;
        compensation_ = (t - sum_) - y;  // 抵消低位损失
        sum_ = t;
    }

    void subtract(double value) {
        add(-value);
    }

    double get() const { return sum_; }
};
```

**面试加分点：**
- 讨论 tick data 可能乱序到达 → 需要按 timestamp 排序或处理 late arrival
- Ring buffer 比 deque 更 cache-friendly，适合固定大小的窗口
- 在 HFT 中，VWAP 通常用 integer arithmetic（价格用 fixed-point 表示）来避免浮点开销

---

## Q7: Order Book 数据结构设计

### 标准答案

```cpp
#include <map>
#include <list>
#include <unordered_map>

using Price = int64_t;      // 定点数（如 price × 10000 → 避免浮点）
using OrderID = uint64_t;
using Quantity = int64_t;

struct Order {
    OrderID id;
    Price price;
    Quantity quantity;
    bool is_buy;
    std::list<Order*>::iterator position;  // 在价格层级链表中的位置
};

struct PriceLevel {
    Price price;
    Quantity total_quantity = 0;
    std::list<Order*> orders;  // FIFO 顺序
};

class OrderBook {
    // Bid side: 降序（最高价在前）
    std::map<Price, PriceLevel, std::greater<Price>> bids_;
    // Ask side: 升序（最低价在前）
    std::map<Price, PriceLevel> asks_;
    // Order ID → Order 快速查找
    std::unordered_map<OrderID, Order> orders_;

public:
    // *** Add Order: O(log N) ***
    void addOrder(OrderID id, Price price, Quantity qty, bool is_buy) {
        auto& order = orders_[id];
        order = {id, price, qty, is_buy, {}};

        auto& book = is_buy ? bids_ : asks_;
        auto& level = book[price];
        level.price = price;
        level.total_quantity += qty;
        level.orders.push_back(&orders_[id]);
        orders_[id].position = std::prev(level.orders.end());
    }

    // *** Cancel Order: O(1) amortized ***
    void cancelOrder(OrderID id) {
        auto it = orders_.find(id);
        if (it == orders_.end()) return;

        Order& order = it->second;
        auto& book = order.is_buy ? bids_ : asks_;
        auto level_it = book.find(order.price);

        level_it->second.total_quantity -= order.quantity;
        level_it->second.orders.erase(order.position);

        // 如果价格层级为空，删除之
        if (level_it->second.orders.empty()) {
            book.erase(level_it);
        }
        orders_.erase(it);
    }

    // *** Get Best Bid/Ask: O(1) ***
    Price getBestBid() const { return bids_.empty() ? 0 : bids_.begin()->first; }
    Price getBestAsk() const { return asks_.empty() ? 0 : asks_.begin()->first; }
    Price getSpread() const { return getBestAsk() - getBestBid(); }
};
```

**关键设计决策：**

| 决策 | 理由 |
|------|------|
| 价格用 `int64_t`（定点数） | 避免浮点精度问题和浮点运算开销 |
| `std::map` 存储价格层级 | 自动排序、O(log N) 插入、O(1) 最优价（`begin()`） |
| `std::list` 存储同价格订单 | O(1) 中间删除（cancel），维护 FIFO |
| `unordered_map` 做 ID 查找 | O(1) cancel/modify 查找 |
| 存 `iterator` 在 Order 里 | cancel 时不需要遍历链表，直接 O(1) 定位 |

**高性能版本优化：**
- 用 **内存池（memory pool / arena allocator）** 替代标准 allocator，避免频繁 `malloc/free`
- 用 **intrusive linked list** 替代 `std::list`，减少指针间接寻址
- 对于价格范围有限的市场，可以用 **数组索引** 替代 `std::map`（O(1) 查找）
- `std::unordered_map` 替换为 **open-addressing hash map**（如 robin_hood::unordered_map），更 cache-friendly

---

## Q8: 低延迟交易系统设计

### 标准答案

**端到端架构：**

```
Market Data Feed
      │ (UDP multicast / kernel bypass)
      ▼
┌─────────────────┐
│ Network Layer   │  DPDK / OpenOnload / FPGA NIC
│ (Packet Capture)│  Busy polling, no interrupt
└────────┬────────┘
         │
┌────────▼────────┐
│ Feed Handler    │  Protocol parsing (FIX/ITCH/OUCH)
│ (Decode)        │  Zero-copy deserialization
└────────┬────────┘
         │
┌────────▼────────┐
│ Strategy Engine │  Signal generation, alpha computation
│ (Decision)      │  Pre-computed lookup tables, branchless code
└────────┬────────┘
         │
┌────────▼────────┐
│ Order Manager   │  Order validation, risk check (pre-trade)
│ (Risk + Send)   │  Rate limiting, position limits
└────────┬────────┘
         │ (TCP / FIX / proprietary protocol)
         ▼
     Exchange
```

**每一层的优化手段（详解）：**

**1. 网络层 — 目标：亚微秒级**
- **Kernel bypass：** 传统 TCP/IP 经过内核协议栈有 ~10μs 开销。用 DPDK 或 Solarflare OpenOnload 绕过内核，数据直接从网卡到用户空间。
- **Busy polling：** 不用 `epoll/select`（有唤醒延迟），而是在一个独占 CPU core 上无限循环轮询网卡。
- **FPGA：** 把 feed handler 甚至策略逻辑放到 FPGA 上，tick-to-trade 可达纳秒级。

**2. OS 层 — 目标：消除 jitter**
- **CPU isolation：** `isolcpus` 内核参数把特定 CPU core 从调度器中隔离出来，专门给交易线程使用。
- **NUMA-aware：** 确保线程使用本地 NUMA node 的内存，避免跨 node 访问（延迟 ×2-3）。
- **Huge pages（2MB / 1GB）：** 减少 TLB miss，避免 page fault。
- **关闭不需要的东西：** swap off、irqbalance off、transparent huge pages off、frequency scaling off。

**3. 应用层 — 目标：每个 CPU cycle 都精打细算**
- **Pre-allocate everything：** 启动时分配好所有内存，运行时零 allocation。
- **Lock-free 数据结构：** SPSC queue 传递市场数据。
- **Avoid syscalls on hot path：** 不做任何 I/O、不加锁、不 log。
- **Branchless code：** 用 CMOV 或 lookup table 替代 if-else。
- **Data-oriented design：** 把热数据紧凑排列，最大化 cache 命中。

**4. 编译层 — 目标：榨干编译器**
- **PGO（Profile-Guided Optimization）：** 先 profile 真实负载，再用 profile 数据重新编译。
- **LTO（Link-Time Optimization）：** 跨编译单元优化。
- **`-O3 -march=native`：** 开启所有优化，针对当前 CPU 架构。
- **`likely/unlikely`：** 帮助编译器优化分支预测。

**面试加分点：**
- 能给出具体延迟数字：wire-to-wire < 1μs（FPGA），< 5μs（优化的 C++ 软件）
- 讨论 co-location 和 交易所距离的重要性
- 提到 timestamping 和延迟测量方法论

---

## Q9: 时间同步

### 标准答案

**为什么时间同步重要？**
- 交易系统需要精确知道事件发生的时间，用于延迟测量、事件排序、合规审计
- 多台服务器之间的时钟必须同步，否则无法比较跨机器的时间戳

**NTP vs PTP：**

| 特性 | NTP | PTP (IEEE 1588) |
|------|-----|-----------------|
| 精度 | 毫秒级（LAN）~ 几十毫秒（WAN） | 亚微秒级（硬件支持下可达纳秒级） |
| 实现 | 纯软件 | 需要硬件支持（网卡、交换机） |
| 成本 | 低 | 高（需要 PTP-capable 设备） |
| HFT 适用性 | ✗ | ✓ |

**PTP 工作原理（简化）：**
1. Master clock 广播 Sync 消息，附带发送时间 T1
2. Slave 记录接收时间 T2
3. Slave 发送 Delay_Req 消息，记录发送时间 T3
4. Master 记录接收时间 T4，回复 Delay_Resp
5. 计算 offset = ((T2 - T1) - (T4 - T3)) / 2
6. 计算 delay = ((T2 - T1) + (T4 - T3)) / 2

**Hardware Timestamping：**
- 网卡在物理层打时间戳，精度远高于软件时间戳
- 消除了内核协议栈、中断处理等带来的 jitter

**GPS Clock：**
- 用 GPS 接收器作为 PTP grandmaster clock 的时间源
- GPS 精度 ~10ns
- 需要天线能"看到天空"

**面试加分点：**
- 讨论 clock drift（时钟漂移）的监控：用 `chronyc tracking` 或 `phc2sys` 监控
- 提到 leap second（闰秒）的处理
- 交易所自己有 hardware timestamp，可以用来校准本地时钟

---

## Q10: Hot-Cold Path Separation

### 标准答案

**核心思想：** 把系统中延迟敏感的关键路径（hot path）和非关键路径（cold path）分离，分别用不同的策略优化。

**Hot Path — 定义与要求：**
```
Market Data → Decode → Signal Compute → Order Decision → Send Order
              ←────── 整个过程必须 < 5μs ──────→
```

在热路径上**绝对不能做的事情：**
- ❌ 内存分配（malloc/new）
- ❌ 系统调用（write/read/ioctl）
- ❌ 加锁（mutex/spinlock）
- ❌ I/O（log/file/network except order sending）
- ❌ 异常处理（try/catch）
- ❌ 虚函数调用（vtable lookup = cache miss risk）

**Cold Path — 异步处理：**
```
Hot Path Thread ──[lock-free queue]──► Cold Path Thread
                                        ├─ Logging
                                        ├─ Risk monitoring
                                        ├─ Position reconciliation
                                        ├─ PnL calculation
                                        ├─ Audit trail
                                        └─ Alerting
```

**实现架构：**

```cpp
// Hot path thread — 绑定到隔离的 CPU core
void hotPathThread() {
    setAffinity(CORE_1);  // CPU affinity

    while (running) {
        // Busy poll for market data
        auto md = pollMarketData();  // kernel bypass
        if (!md) continue;

        // Compute signal (all pre-allocated, no allocation)
        auto signal = strategy_.compute(md);

        // Send order if needed (pre-formatted buffer)
        if (signal.should_trade) {
            orderSender_.send(signal.order);
        }

        // Publish event to cold path (lock-free SPSC queue, non-blocking)
        eventQueue_.push({md, signal, rdtsc()});
    }
}

// Cold path thread — 在另一个 CPU core 上
void coldPathThread() {
    setAffinity(CORE_2);

    while (running) {
        auto event = eventQueue_.pop();
        if (!event) {
            std::this_thread::yield();
            continue;
        }

        logger_.log(event);
        riskMonitor_.update(event);
        pnlTracker_.update(event);
    }
}
```

**面试加分点：**
- 讨论 pre-trade risk check 是否在 hot path 上 → 通常简单的限制检查（position limit、rate limit）放在 hot path，复杂的风控在 cold path
- 提到 hot path 上使用 `[[likely]]` / `[[unlikely]]` 帮助分支预测
- 讨论 logging 的异步实现（如 spdlog async mode）

---

## Q11: Black-Scholes 模型

### 标准答案

**Black-Scholes 公式（欧式看涨期权）：**

```
C = S₀·N(d₁) - K·e^(-rT)·N(d₂)

其中：
d₁ = [ln(S₀/K) + (r + σ²/2)·T] / (σ·√T)
d₂ = d₁ - σ·√T

S₀ = 标的资产当前价格
K  = 行权价（strike price）
r  = 无风险利率
T  = 到期时间（年）
σ  = 波动率
N(·) = 标准正态分布的累积分布函数
```

**欧式看跌期权（通过 Put-Call Parity）：**
```
P = K·e^(-rT)·N(-d₂) - S₀·N(-d₁)
```

**五个核心假设：**

1. **几何布朗运动（GBM）：** 标的资产价格满足 `dS = μ·S·dt + σ·S·dW`
   - 意味着对数收益率 log(S(t)/S(0)) 服从正态分布
   - 价格本身服从对数正态分布 → 价格不能为负（✓）

2. **波动率恒定：** σ 不随时间或价格变化
   - 现实中不成立 → volatility smile/skew

3. **无风险利率恒定：** r 在期权存续期间不变

4. **完美市场假设：**
   - 无交易成本、无税
   - 无借贷限制（可以自由做多做空）
   - 可无限分割交易

5. **连续对冲：** 可以连续不断地调整对冲头寸
   - 现实中只能离散对冲 → hedging error

**局限性与改进：**

| 局限性 | 现实表现 | 改进模型 |
|--------|---------|---------|
| 波动率恒定 | Volatility smile/skew | Local Vol、Stochastic Vol（Heston）、SABR |
| 正态分布收益率 | Fat tails（肥尾） | Jump-diffusion（Merton）、Variance Gamma |
| 无法处理美式期权 | 提前行权 | Binomial tree、Finite Difference、Least-Squares MC |
| 连续对冲 | 离散对冲有误差 | 考虑 hedging frequency 的模型 |
| 无交易成本 | Bid-ask spread、手续费 | 带交易成本的对冲策略 |

---

## Q12: Greeks 与 Delta Hedging

### 标准答案

**五个 Greeks 详解：**

**Delta (Δ) = ∂C/∂S**
- 期权价格对标的资产价格的一阶导数
- 看涨期权 Delta ∈ [0, 1]，看跌期权 Delta ∈ [-1, 0]
- ATM（at-the-money）期权 Delta ≈ 0.5
- Delta 也可以近似理解为期权到期时 in-the-money 的概率

**Gamma (Γ) = ∂²C/∂S² = ∂Δ/∂S**
- Delta 的变化速率
- 所有期权的 Gamma > 0（无论 call 还是 put）
- ATM、近到期的期权 Gamma 最大
- Gamma 大 → Delta 变化快 → 需要频繁 rebalance

**Theta (Θ) = ∂C/∂t**
- 时间衰减（通常为负值 → 期权随时间流逝而贬值）
- Theta-Gamma 关系：`Θ ≈ -½·Γ·S²·σ²`（BSM 框架下）
- 买方 Theta < 0（每天损失时间价值），卖方 Theta > 0

**Vega (ν) = ∂C/∂σ**
- 期权价格对波动率的敏感度
- 所有期权的 Vega > 0
- ATM、远到期的期权 Vega 最大

**Rho (ρ) = ∂C/∂r**
- 期权价格对无风险利率的敏感度
- 通常影响最小

**Delta Hedging 操作：**

假设你卖出了 100 份 Delta=0.6 的看涨期权：
- 你的总 Delta = -100 × 0.6 = -60
- 你需要买入 60 股标的资产来对冲
- 组合 Delta = -60 + 60 = 0（Delta Neutral）

```
时间 t：
  卖出 100 calls，Delta = 0.6
  → 买入 60 股 → 组合 Delta = 0

时间 t+1：
  股价上涨 → Delta 变为 0.65
  → 需要再买 5 股（100 × 0.65 - 60 = 5）
  → 组合重新 Delta = 0

时间 t+2：
  股价下跌 → Delta 变为 0.55
  → 需要卖出 5 股（60 + 5 - 100 × 0.55 = 10 → 卖出 10 股）
```

**Gamma 风险管理：**

- **高 Gamma → Delta 变化快 → 需要频繁 rebalance → 交易成本高**
- 管理策略：
  1. **Gamma scalping：** 做多 Gamma（买入期权），通过 Delta hedging 在标的资产波动中获利
  2. **用期权对冲 Gamma：** 买入/卖出其他期权来抵消 Gamma 暴露
  3. **Theta-Gamma 权衡：** 做多 Gamma 意味着承担 Theta 成本（每天损失时间价值）

---

## Q13: 蒙特卡洛定价

### 标准答案

**以亚式期权（Asian Option）为例：**

亚式期权的 payoff 取决于标的资产在期权存续期间的**平均价格**，而非到期时的价格。

**基本流程：**

```cpp
#include <cmath>
#include <random>
#include <vector>

double priceAsianCall(
    double S0,        // 初始价格
    double K,         // 行权价
    double r,         // 无风险利率
    double sigma,     // 波动率
    double T,         // 到期时间（年）
    int n_steps,      // 时间步数
    int n_simulations // 模拟次数
) {
    double dt = T / n_steps;
    double drift = (r - 0.5 * sigma * sigma) * dt;
    double vol = sigma * std::sqrt(dt);
    double discount = std::exp(-r * T);

    std::mt19937 rng(42);
    std::normal_distribution<> normal(0.0, 1.0);

    double sum_payoffs = 0.0;

    for (int sim = 0; sim < n_simulations; ++sim) {
        double S = S0;
        double sum_S = 0.0;

        for (int step = 0; step < n_steps; ++step) {
            double Z = normal(rng);
            S *= std::exp(drift + vol * Z);
            sum_S += S;
        }

        double avg_price = sum_S / n_steps;
        double payoff = std::max(avg_price - K, 0.0);
        sum_payoffs += payoff;
    }

    return discount * sum_payoffs / n_simulations;
}
```

**方差缩减技术详解：**

**1. 对偶变量法（Antithetic Variates）：**
- 对每个随机数 Z，同时模拟 Z 和 -Z
- 两条路径的 payoff 取平均
- 减少约 50% 的方差

```cpp
// 正常路径用 Z
double S_pos = S0;
// 对偶路径用 -Z
double S_neg = S0;

for (int step = 0; step < n_steps; ++step) {
    double Z = normal(rng);
    S_pos *= exp(drift + vol * Z);
    S_neg *= exp(drift + vol * (-Z));
}
double payoff = 0.5 * (payoff_pos + payoff_neg);
```

**2. 控制变量法（Control Variates）：**
- 选一个与目标相关、但有解析解的变量作为"控制"
- 例：用几何平均亚式期权（有解析解）作为控制变量来修正算术平均亚式期权

```
估计值 = MC_arithmetic + c * (Analytical_geometric - MC_geometric)
```

**3. 准蒙特卡洛（Quasi-Monte Carlo）：**
- 用低差异序列（Sobol, Halton）替代伪随机数
- 收敛速度从 O(1/√N) 提升到 O(1/N)（理论上）
- 特别适合中等维度（< 几百维）的问题

---

## Q14: 连续正面问题

### 标准答案

**问题：** 抛公平硬币，直到连续出现两次正面（HH），期望抛多少次？

**方法：马尔可夫链状态转移**

定义状态：
- **S₀**：初始状态（上一次不是 H，或还没开始）
- **S₁**：上一次是 H（还差一个 H 就达成 HH）
- **S₂**：连续两次 H（终止状态）

状态转移：

```
          T (1/2)
    ┌──────────────┐
    ▼              │     H (1/2)           H (1/2)
  [S₀] ──────────────────► [S₁] ──────────────► [S₂] (终止)
    ▲                        │
    └────────────────────────┘
           T (1/2)
```

**列方程：**

设 E₀ = 从 S₀ 出发的期望步数，E₁ = 从 S₁ 出发的期望步数。

```
E₀ = 1 + (1/2)·E₀ + (1/2)·E₁     ... (1)
      ↑     ↑           ↑
    抛1次  掷出T→回S₀  掷出H→进S₁

E₁ = 1 + (1/2)·E₀ + (1/2)·0       ... (2)
      ↑     ↑           ↑
    抛1次  掷出T→回S₀  掷出H→到S₂(结束)
```

**求解：**

从 (2)：`E₁ = 1 + E₀/2`

代入 (1)：
```
E₀ = 1 + E₀/2 + (1/2)(1 + E₀/2)
E₀ = 1 + E₀/2 + 1/2 + E₀/4
E₀ = 3/2 + 3E₀/4
E₀/4 = 3/2
E₀ = 6
```

**答案：E₀ = 6**

**推广：** 连续 k 次正面的期望次数为 `E = 2^(k+1) - 2`
- k=1: E = 2
- k=2: E = 6
- k=3: E = 14

---

## Q15: 轮流掷骰子

### 标准答案

**问题：** A 和 B 轮流掷一个公平六面骰子，A 先掷。先掷出 6 的人赢。求 A 的获胜概率。

**解法一：几何级数**

```
P(A赢) = P(第1轮A掷出6) + P(前2人都没掷出6) × P(第3轮A掷出6) + ...

= 1/6 + (5/6)(5/6) × 1/6 + (5/6)²(5/6)² × 1/6 + ...

= (1/6) × [1 + (25/36) + (25/36)² + ...]

= (1/6) × 1/(1 - 25/36)

= (1/6) × (36/11)

= 6/11

≈ 0.5455
```

**解法二：递推方程**

设 P = A 的获胜概率。

第一轮：
- A 掷出 6（概率 1/6）→ A 赢
- A 没掷出 6（概率 5/6）→ 轮到 B
  - B 掷出 6（概率 1/6）→ B 赢
  - B 没掷出 6（概率 5/6）→ 回到和初始完全相同的状态

```
P = 1/6 + (5/6)(5/6) × P
P = 1/6 + 25/36 × P
P - 25P/36 = 1/6
11P/36 = 1/6
P = 36/(6×11) = 6/11
```

**答案：P(A赢) = 6/11 ≈ 54.55%**

先手确实有优势，但优势不大（比 50% 多约 4.5%）。

**面试追问：如果改成 N 面骰子？**

```
P = (1/N) / [1 - ((N-1)/N)²] = N / (2N - 1)
```

当 N → ∞ 时，P → 1/2（先手优势消失）。

---

## Q16: Itô's Lemma

### 标准答案

**Itô's Lemma 公式：**

设 `X(t)` 是一个 Itô 过程：`dX = μ·dt + σ·dW`

则对于二阶可微函数 `f(t, X)`，有：

```
df = (∂f/∂t)·dt + (∂f/∂X)·dX + (1/2)·(∂²f/∂X²)·(dX)²
```

由于 `(dW)² = dt`，`dt·dW = 0`，`(dt)² = 0`，所以 `(dX)² = σ²·dt`。

展开得：

```
df = [∂f/∂t + μ·(∂f/∂X) + (1/2)·σ²·(∂²f/∂X²)]·dt + σ·(∂f/∂X)·dW
```

**与普通微积分的关键区别：**

| | 普通微积分 | 随机微积分 |
|---|---|---|
| 链式法则 | `df = f'(x)·dx` | `df = f'(x)·dx + ½·f''(x)·(dx)²` |
| 二阶项 | `(dx)² ≈ 0`（可忽略） | `(dW)² = dt`（不可忽略！） |
| 原因 | 普通函数光滑 | 布朗运动处处不可微，路径有无限变分 |

**经典应用：推导 ln(S) 的动态**

设 `S` 满足 GBM：`dS = μ·S·dt + σ·S·dW`

令 `f(S) = ln(S)`，则：
- `f'(S) = 1/S`
- `f''(S) = -1/S²`

代入 Itô's Lemma：
```
d(ln S) = (1/S)·dS + (1/2)·(-1/S²)·(dS)²
        = (1/S)·(μ·S·dt + σ·S·dW) + (1/2)·(-1/S²)·σ²·S²·dt
        = μ·dt + σ·dW - (1/2)·σ²·dt
        = (μ - σ²/2)·dt + σ·dW
```

积分得：
```
ln(S(T)/S(0)) = (μ - σ²/2)·T + σ·W(T)
```

即 `ln(S(T)/S(0))` 服从正态分布 `N((μ - σ²/2)·T, σ²·T)`。

**这就是为什么 GBM 模型下价格是对数正态分布，而且 drift 不是 μ 而是 μ - σ²/2。** 这个 `-σ²/2` 正是 Itô correction term。

**面试加分点：**
- 这个结论直接用于蒙特卡洛模拟中的路径生成公式
- 推导 Black-Scholes PDE 需要对期权价格 V(S,t) 应用 Itô's Lemma
- 提到 Stratonovich 积分与 Itô 积分的区别（Stratonovich 保留普通链式法则，但 Itô 积分在金融中更常用因为其非预期性质）

---

## Q17: 性能优化经验（回答框架）

### 标准答案模板

面试官期望你用一个**真实的故事**回答，但要遵循 **STAR 框架**：

**Situation（背景）：**
> "在 XX 公司/项目中，我们的交易系统/数据管道的 p99 延迟是 XX μs/ms，业务要求降低到 XX μs/ms。"

**Task（任务）：**
> "我负责定位瓶颈并优化延迟。"

**Action（行动 — 这是重点）：**

1. **Profiling 定位瓶颈**
   - 用 `perf record` + `perf report` 生成 flamegraph
   - 用 `perf stat` 看 IPC（instructions per cycle）、cache miss rate、branch misprediction rate
   - 用 Intel VTune 做更细粒度分析

2. **瓶颈 & 解决方案**（举例）：
   - "发现 hot loop 中有大量 cache miss → 重新排列数据结构布局，把热字段打包到一起 → cache miss 降低了 60%"
   - "发现 mutex contention → 替换为 lock-free SPSC queue → p99 延迟降低了 3x"
   - "发现 memory allocation 是瓶颈 → 改为 pre-allocated ring buffer → 消除了所有 hot path 上的 malloc"
   - "发现分支预测失败率高 → 改用 branchless 算法 → 吞吐量提高了 40%"

3. **验证**
   - 用微基准测试（Google Benchmark）验证局部改进
   - 用端到端测试验证整体改进
   - 在生产环境中用 A/B 测试验证

**Result（结果 — 用数据说话）：**
> "最终 p99 延迟从 XX μs 降低到 XX μs，吞吐量提高了 XX%。"

**回答中要展示的素质：**
- 系统性思维：先测量，后优化，不做过早优化
- 数据驱动：用数字量化改进
- 权衡意识：讨论优化带来的 trade-off（如代码可读性下降）

---

## Q18: 延迟毛刺排查（回答框架）

### 标准答案

**排查方法论：由外到内、由粗到细**

**Step 1: 确认问题范围**
- 毛刺是偶发还是周期性的？
- 影响所有请求还是特定路径？
- 是否与特定时间段（如开盘、收盘）相关？
- 查看延迟分布（p50 正常但 p99 很高 → tail latency 问题）

**Step 2: 系统级排查**

```bash
# 1. 检查 CPU 频率是否被降频
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq
# 应该全部在最高频率，如果不是 → 设置 performance governor
cpupower frequency-set -g performance

# 2. 检查上下文切换
cat /proc/<pid>/status | grep voluntary_ctxt_switches
# 如果非自愿切换很多 → 可能线程被抢占

# 3. 检查 page fault
cat /proc/<pid>/status | grep -i fault
# majflt > 0 → 有 major page fault（从磁盘加载页面！）
# 解决：mlock + huge pages + disable swap

# 4. 检查中断
cat /proc/interrupts
# 看是否有中断打到了交易线程所在的 core
# 解决：irqaffinity 把中断移到其他 core

# 5. 检查 NUMA
numastat -p <pid>
# 看 other_node（远程 NUMA 访问）是否很多
# 解决：numactl --cpunodebind=0 --membind=0

# 6. 检查网络
ethtool -S <interface> | grep -i drop
# 看网卡是否有丢包
# tcpdump 抓包分析是否有 retransmission
```

**Step 3: 应用级排查**

```bash
# 7. 检查 GC（如有 Java/Python 组件）
# Java: -XX:+PrintGCDetails -XX:+PrintGCDateStamps
# 看 STW（Stop-The-World）暂停是否和延迟毛刺时间吻合

# 8. 时间戳埋点
# 在关键路径上用 rdtsc 打点，精确定位是哪个环节耗时
uint64_t t1 = rdtsc();
process_market_data();
uint64_t t2 = rdtsc();
generate_signal();
uint64_t t3 = rdtsc();
send_order();
uint64_t t4 = rdtsc();
// 记录 t2-t1, t3-t2, t4-t3，找到最慢的环节
```

**Step 4: 常见根因 & 解决方案**

| 根因 | 表现 | 解决方案 |
|------|------|---------|
| CPU frequency scaling | 周期性延迟 | `performance` governor，禁用 C-states |
| Page fault | 偶发大延迟（~ms 级） | `mlock()`、huge pages、swap off |
| NUMA remote access | 一致性偏高延迟 | `numactl` 绑定 CPU 和内存到同一 node |
| IRQ on hot core | 偶发延迟 | `irqaffinity` 迁移中断 |
| Context switch | 频繁小毛刺 | `isolcpus`、`SCHED_FIFO` |
| TLB miss | 持续偏高延迟 | huge pages（2MB/1GB） |
| Kernel timer | 周期性毛刺 | `nohz_full` 无滴答内核 |
| 竞争/锁 | 负载高时延迟增大 | lock-free 设计 |
| Log I/O | 偶发大延迟 | 异步 logging、log 到 tmpfs |

**面试加分点：**
- 提到用 `perf sched latency` 分析调度延迟
- 提到 `ftrace` 做内核级 tracing
- 讨论 "tail latency" 的系统性管理（Jeff Dean 的论文 "The Tail at Scale"）
