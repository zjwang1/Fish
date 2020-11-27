#pragma once

#include <cassert>
#include <string>
#include <iostream>
#include <fstream>

namespace zjwang
{
    namespace file
    {
        // required at least cpp 11

        static int ReadFileAllIn(const std::string &filename, std::string &data)
        {
            data.clear();
            std::ifstream f(filename);
            f.seekg(0, std::ios::end);
            assert(f.tellg() >= 0);
            data.resize(f.tellg());
            f.seekg(0);
#if __cplusplus >= 201703L
            f.read(data.data(), data.size());
#else
            char *cstr = &data[0];
            f.read(cstr, data.size());
#endif
            return 0;
        }

        static int WriteFileAllIn(const std::string &filename, const std::string &data)
        {
            std::ofstream f(filename);
            f.write(data.data(), data.size());
            return 0;
        }

    } // namespace file
} // namespace zjwang