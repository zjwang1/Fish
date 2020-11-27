#include "file.h"
#include "../timer/timestamp.h"
#include "../thread_pool/easy_thread_pool.h"

#include <cstring>

int main()
{
    // use multiple threads for read/write file
    constexpr size_t threadNum = 4;
    zjwang::thread::ThreadPool pool{threadNum};
    auto lbd = [](uint64_t start, uint64_t end) { std::cout << "cost :[" << (end - start) / 1000 << "]us \n"; };
    constexpr size_t N = 1024 * 1024 * 1024;

    // std::string to char * base example
    {
        std::string str = "some";
        char *cstr = &str[0];
        std::cout << strlen(cstr) << "\n";
        std::cout << "new str is " << str.size() << "\n";
    }
    {
        // write data in file
        zjwang::perf::ScopedTimer timer{{"test std::string"}, lbd};
        std::vector<std::future<int>> results;
        for (size_t i = 0; i < threadNum; ++i)
        {
            results.emplace_back(pool.enqueue([i]() {
                std::string data;
                for (size_t idx = 0; idx < N; ++idx)
                {
                    data += '1';
                }
                zjwang::file::WriteFileAllIn(std::to_string(i), data);
                return 0;
            }));
        }
        for (auto &&result : results)
        {
            result.get();
        }
    }
    {
        // callback func
        using namespace zjwang::file;
        auto callback = [](CharArray &&chars) {
            size_t fileSize = strlen(chars.get());
            std::cout << "file content size is " << fileSize << "\n";
            //std::string s{chars.get()};
            //std::cout << "s size is " << s.size() << "\n";
            //std::cout << "chars[0] is " << chars.get()[0] << "\n";
        };
        zjwang::perf::ScopedTimer timer{{"test std::string"}, lbd};
        zjwang::file::ReadFileAllIn("1", std::move(callback));
    }
    /*{
        zjwang::perf::ScopedTimer timer{{"test std::string"}, lbd};
        std::vector<std::future<int>> results;
        for (size_t i = 0; i < threadNum; ++i)
        {
            results.emplace_back(pool.enqueue([i]() {
                std::string data;
                zjwang::file::ReadFileAllIn(std::to_string(i), data);
                return 0;
            }));
        }
        for (auto &&result : results)
        {
            result.get();
        }
    }*/
    return 0;
}