#! /bin/bash
#g++ -std=c++11 -O3 sample.cc -o 11_sample

# 据说C++17可以直接分配
g++ -std=c++17 -m64 -O3 -march=native sample.cc -o 17_sample
