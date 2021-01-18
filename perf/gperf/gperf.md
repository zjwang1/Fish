# gperf

##　安装gperf
```bash
git clone https://github.com/gperftools/gperftools.git
cd gperftools
./autogen.sh
./configure
make -j8
sudo make install
```
## 使用CPU profiler
编译时链接 -lprofiler
运行时指定输出文件
用pprof美化结果
```bash
g++ [...] -o myprogram -lprofiler
CPUPROFILE=/tmp/profile ./myprogram # CPUPROFILE_FREQUENCY设置CPU的采样频率
pprof /tmp/profile --web
# pprof  ./test_capture test_capture.prof --pdf > prof.pdf 生成pdf格式的性能报告（层次调用节点有向图）
# ./test_capture test_capture.prof --text 生成文本格式的性能报告输出到控制台

```
## 使用说明
CPU profiler是基于采样工作的。所以采样次数影响着性能报告的准确性。如果采样次数过少，则你会发现同样的程序同样的数据，每次输出的性能报告中的热点都不一样。所以在我的实际应用中，通过循环运行测试程序函数，大幅度提高采样次数。这样才能获得一个稳定的准确的性能报告。

## 经验之谈
产品中启动一个专门监听外部命令的线程，接收到指定命令时开启和结束性能收集。比如监听一个本地Socket，在这个socket上接收到命令时就执行，并把输出也都反馈到这个本地socket中去。这样只要再写另外一个简单的读写这个socket的小程序，就可以很方便地实现动态控制服务器进程的效果。