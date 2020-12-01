#pragma once

#include "../malloc/aligned_alloc.h"

#include <cassert>
#include <string>
#include <functional>
#include <iostream>
#include <fstream>

namespace zjwang
{
    namespace file
    {

        // 为了防止std::string的垃圾拷贝，采用char* 作为数据源. 用unique_ptr管理生命周期.
        using CharArray = std::unique_ptr<char[], zjwang::alloc::details::AlignedDeleter>;
        using ReadFileCallback = std::function<void(CharArray &&chars)>;
        static int ReadFileAllIn(const std::string &filename, ReadFileCallback &&callback)
        {
            std::ifstream f(filename);

            f.seekg(0, std::ios::end);
            auto fileSize = f.tellg();
            assert(fileSize >= 0);
            CharArray chars = zjwang::alloc::alignedArray<char> (fileSize);

            f.seekg(0);
            f.read(chars.get(), fileSize);

            // 设置终止符
            chars.get()[fileSize - 1L] =  '\0';

            callback(std::move(chars));
            return 0;
        }

        // ofstream has enough function, so don't need using this trash wrapper function.
        static int WriteFileAllIn(const std::string &filename, const std::string &data)
        {
            std::ofstream f(filename);
            f.write(data.data(), data.size());
            return 0;
        }

        

    } // namespace file
} // namespace zjwang