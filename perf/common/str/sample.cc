#include <cassert>
#include <cstring>
#include <string>
#include <unordered_map>
#include "str.h"
#include "../timer/timestamp.h"


constexpr static size_t N = 1e9;
int main(int argc, char * argv[])
{
    auto lbd = [] (uint64_t start, uint64_t end) { std::cout << "cost :[" << (end - start) / 1000 << "]us \n";};
    // for std::string compare
    {
        const std::string s{"123456789abcdef"};
        //bool flag;
        zjwang::perf::ScopedTimer timer{{"test std::string"}, lbd};
        for (size_t i = 0; i < N; ++i)
        {
            assert(!strncmp(s.c_str(), "123456789abcdef", 15));
        }
    }

    // for Str compare
    {
        zjwang::string::Str<15> str{"123456789abcdef"};
        zjwang::perf::ScopedTimer timer{{"test std::string"}, lbd};
        for (size_t i = 0; i < N; ++i)
        {
            assert(str == "123456789abcdef");
        }
    } 
}