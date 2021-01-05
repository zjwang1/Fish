#pragma once

#include "../malloc/aligned_alloc.h"

#include <sys/mman.h>

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
            assert(strlen(chars.get()) == static_cast<size_t>(fileSize) - 1L); 
            callback(std::move(chars));
            return 0;
        }

        // We will have a lot of chars(bytes), so let's get some helper function.
        // Anyway, our helper will be a really helpful funtion instead of fucking opod helper function.
        static int SplitCharArray(std::vector<size_t> &postions)
        {
            
        }




        // in cpp11 use &data[0] to get char* in std::string maybe is a dangerous operation, so this function is fucked.
        static int ReadFileAllIn(const std::string &filename, std::string &data)
        {
            data.clear();
            std::ifstream f(filename);

            f.seekg(0, std::ios::end);
            auto fileSize = f.tellg();
            assert(fileSize >= 0);
            data.resize(fileSize);

            f.seekg(0);
            f.read(&data[0], data.size());

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