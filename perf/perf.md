# Perf

**na na na**, perf is interesting thing to do.

## 整体思路

### 纪录大量的事实
        
    1. 纪录软硬件配置
    2. 保存并组织性能结果
    3. 整理清楚命令调用，放在统一的shell里
    4. 纪录研究信息和相应的reference url
    
    
    性能测试的结果含义是不明确的，需要更多的信息来理解结果．
    
    所有的信息或许都是有用的．路上的一切都可以作为证据来支持特定的理论(观点), 也可以辩驳一些理论(观点).

### 测试框架(方法)可复用
    1. shell命令复用
    2. binary命令复用
    3. 测试使用的measure手段复用

### 使用多个工具搞清楚问题
    1. cpu tool
    2. cpu cache tool
    3. memory tool
    4. perf tool

## 性能调查概要
按照一个清晰的思路往下走

### 找到 指标 + 基线 + 目标
    指标: 客观的度量方法.(需要了解一下常用的指标)

    基线: 在优化前确定当前的性能等级，作为性能优化的起点.

    目标: 寻找完成同样任务的开源项目，找到性能最优的方案，作为一个合理的目标点.

### 追踪近似问题
    google大法: 看一下有没有现成的问题解决方案

    同事: 之前是否遇到过

### 启动调查
    分离问题，隔离环境.尽量减少当前系统的负载.

    一次只改变一件事.要确认真正的问题，每次只有一个变化会逐步收敛结果.

    始终在优化后重新测量.保持最新的perf测试结果, 以便下一轮迭代.

### record by record
    review 过程

    复用工作

## CPU

### 概念

1. 运行队列统计: 


## google benchmark工具
对一个代码片段做优化有奇效.

发现热点代码片段 -> benchmark找到base line -> 花里胡哨优化 -> 继续benchmark迭代

好的中文教程: https://www.cnblogs.com/apocelipes/p/10348925.html
### 要点:
一个benchmark任务的原型是```c++std::function<void(benchmark::State&)>```.

测试过程中可以用constexpr进行编译期数值计算，尽量避免运行时计算对测试结果的干扰.


对于不想测试的代码，可以通过启停state的计时器来处理. Like this: 
```c++
do_something();
state.PauseTiming();
do_else();
state.ResumeTiming();
```

通过指定参数来控制benchmark运行时参数. 提供了基础的整数序列传递. 其他对象的传递其实可以用全局变量来搞.
```c++
// In func scope:
auto x = state.range(0);
// ...

// while call func
BENCHMARK(func)->Arg(10);

// 考虑更多的参数，可以用Range来做

```

C++11后都支持传参
```c++
template <class ...ExtraArgs>
void BM_takes_args(benchmark::State& state, ExtraArgs&&... extra_args) {
  [...]
}
// Registers a benchmark named "BM_takes_args/int_string_test" that passes
// the specified values to `extra_args`.
BENCHMARK_CAPTURE(BM_takes_args, int_string_test, 42, std::string("abc"));
```

用模板控制同一个动作的多个实现
```c++
template <class Q> void BM_Sequential(benchmark::State& state) {
  Q q;
  typename Q::value_type v;
  for (auto _ : state) {
    for (int i = state.range(0); i--; )
      q.push(v);
    for (int e = state.range(0); e--; )
      q.Wait(&v);
  }
  // actually messages, not bytes:
  state.SetBytesProcessed(
      static_cast<int64_t>(state.iterations())*state.range(0));
}
BENCHMARK_TEMPLATE(BM_Sequential, WaitQueue<int>)->Range(1<<0, 1<<10);
```

多线程压测
```c++
static void BM_MultiThreaded(benchmark::State& state) {
  if (state.thread_index == 0) {
    // Setup code here.
  }
  for (auto _ : state) {
    // Run the test as normal.
  }
  if (state.thread_index == 0) {
    // Teardown code here.
  }
}
BENCHMARK(BM_MultiThreaded)->Threads(2);
```




