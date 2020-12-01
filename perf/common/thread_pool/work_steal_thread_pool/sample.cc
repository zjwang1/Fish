#include "thread_pool.hpp"
#include <functional>
#include <future>
#include <vector>
#include <cassert>

static std::function<int()> func = []() {
    for (size_t i = 0; i < 10000000; i++)
        ;
    return 0;
};

constexpr static size_t numTasks = 1000000;

int main()
{
    zjwang::ThreadPool threadPool;
    std::vector<std::future<int>> results;
    results.reserve(numTasks);
    for (size_t i = 0; i < numTasks; ++i)
    {
        std::packaged_task<int()> t(func);
        results.emplace_back(t.get_future());
        threadPool.Post(t);
    }
    for (auto &result : results)
    {
        assert(0 == result.get());
    }
    return 0;
}