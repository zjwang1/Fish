#include "file.h"
#include "../timer/timestamp.h"

#include <cstring>

int main()
{
    auto lbd = [] (uint64_t start, uint64_t end) { std::cout << "cost :[" << (end - start) / 1000 << "]us \n";};
    // std::string to char * base example
    {
        std::string str = "some" ;
        char *cstr = &str[0];
        std::cout << strlen(cstr) << "\n";
        std::cout << "new str is " << str.size() << "\n";
    }
    {
        std::string data;
        zjwang::file::ReadFileAllIn("a", data);
    }
    {
        // write data in file
        constexpr size_t N = 1000 * 1000 * 1024;
        std::string data;
        for (size_t i = 0; i < N; ++i)
        {
            data += '1';
        }
        zjwang::perf::ScopedTimer timer{{"test std::string"} , lbd};
        zjwang::file::WriteFileAllIn("a", data);
    }
    {
        std::string data;
        zjwang::perf::ScopedTimer timer{{"test std::string"} , lbd};
        zjwang::file::ReadFileAllIn("a", data);
    }
    return 0;
}