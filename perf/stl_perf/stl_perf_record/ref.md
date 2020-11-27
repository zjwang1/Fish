# 进行perf时的引用

## google ref

1. 如何使用cache统计工具 :[https://www.geeksforgeeks.org/see-cache-statistics-linux/]

2. AVX512使用示例: [https://github.com/MengRao/str/blob/master/Str.h]

3. of course, simd is lovely tool in cpp. [https://stackoverflow.blog/2020/07/08/improving-performance-with-simd-intrinsics-in-three-use-cases/]

4. 分配对齐的内存 [https://stackoverflow.com/questions/12942548/making-stdvector-allocate-aligned-memory/12942652#12942652]  vector分配的地址，默认是4字节对齐，而simd要求的对齐往往是8字节对齐.