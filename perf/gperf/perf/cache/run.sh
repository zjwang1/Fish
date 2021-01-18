#! /bin/bash


#检测cache miss事件需要取消内核指针的禁用

gcc -O3 test.c -o test
gcc -O3 test2.c -o test2

sleep 3
sudo perf stat -e cache-misses ./test
perf report
sleep 15

sudo perf stat -e cache-misses ./test2
perf report