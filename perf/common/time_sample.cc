#include <bits/stdc++.h>
#include "timestamp.h"

using namespace std;

zjwang::perf::Timer timer;

int main(int argc, char **argv)
{
    double tsc_ghz;
    if (argc > 1)
    {
        tsc_ghz = stod(argv[1]);
        timer.init(tsc_ghz);
    }
    else
    {
        tsc_ghz = timer.init();
        // it'll be more precise if you wait a while and calibrate
        std::this_thread::sleep_for(std::chrono::seconds(1));
        tsc_ghz = timer.calibrate();
    }

    cout << std::setprecision(17) << "tsc_ghz: " << tsc_ghz << endl;

    // 1) Try binding to different cores with the same tsc_ghz at nearly the same time, see if the offsets are similar(not
    // necessary the same). If not, you're doomed: tsc of your machine's different cores are not synced up, don't share
    // TSCNS among threads then.
    //
    // 2) Try running test with the same tsc_ghz at different times, see if the offsets are similar(not necessary the
    // same). If you find them steadily go up/down at a fast speed, then your tsc_ghz is not precise enough, try
    // calibrating with a longer waiting time and test again.
    cout << "offset: " << timer.rdoffset() << endl;

    uint64_t rdns_latency;
    {
        const int N = 100;
        uint64_t before = timer.rdns();
        uint64_t tmp = 0;
        for (int i = 0; i < N - 1; i++)
        {
            tmp += timer.rdns();
        }
        uint64_t after = timer.rdns();
        rdns_latency = (after - before) / N;
        cout << "rdns_latency: " << rdns_latency << " tmp: " << tmp << endl;
    }

    {
        using zjwang::perf::ScopedTimer;
        ScopedTimer timer{{"test"}};
        std::this_thread::sleep_for(std::chrono::milliseconds(1000));
    }

    while (true)
    {
        uint64_t a = timer.rdns();
        uint64_t b = timer.rdsysns();
        uint64_t c = timer.rdns();
        int64_t a2b = b - a;
        int64_t b2c = c - b;
        bool good = a2b >= 0 && b2c >= 0;
        uint64_t rdsysns_latency = c - a - rdns_latency;
        cout << "a: " << a << ", b: " << b << ", c: " << c << ", a2b: " << a2b << ", b2c: " << b2c << ", good: " << good
             << ", rdsysns_latency: " << rdsysns_latency << endl;
        // std::this_thread::sleep_for(std::chrono::miliseconds(1000));
        auto expire = timer.rdns() + 1000000000;
        while (timer.rdns() < expire)
            ;
    }

    return 0;
}
