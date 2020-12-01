#! /bin/bash

## 进行perf的自动化脚本

# 查看cpu cache L1~L3的大小
cat /sys/devices/system/cpu/cpu0/cache/index1/size
cat /sys/devices/system/cpu/cpu0/cache/index2/size
cat /sys/devices/system/cpu/cpu0/cache/index3/size

#　同样的方法
lscpu

# 下载cachestat
sudo apt-get install linux-tools-common linux-tools-generic
wget https://raw.githubusercontent.com/brendangregg/perf-tools/master/fs/cachestat
chmod +x cachestat
sudo ./cachestat