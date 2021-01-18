# perf

## 简介
perf是一款linux内置的性能分析工具，随着内核发布，也被称为perf_events, perf tools, PCL(Performance Counters for Linux), 发布于Linux kernel version 2.6.31, perf是怎么工作的呢？perf如何使用？本文是来介绍一下。

perf官方wiki的介绍是：Linux profiling with performance counters

Perf可以解决高级性能和故障排除，它可以分析(当然目前我也只是用来进行cpu性能分析)：

为什么内核消耗CPU高, 代码的位置在哪里？
什么代码引起了CPU 2级cache未命中？
CPU是否消耗在内存I/O上？
哪些代码分配内存，分配了多少？
什么触发了TCP重传？
某个内核函数是否正在被调用，调用频率多少？
线程释放CPU的原因？


## perf拉满搞火焰图
```bash
perf record -F 99 -a -g -- sleep 60 <binary cmd>
# 脚本从dalao的github里找.
perf script |./stackcollapse-perf.pl|./flamegraph.pl > fg_output.svg
```

## perf查看cache命中
1. 测cache miss事件需要取消内核指针的禁用
```bash 
sudo sh -c " echo 1 > /proc/sys/kernel/kptr_restrict"
```
