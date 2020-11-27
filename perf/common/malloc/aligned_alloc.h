#pragma once
#include <cassert>
#include <cstring>

#include <vector>
#include <memory>
#include <algorithm>


namespace zjwang
{
    namespace alloc
    {
        namespace details
        {
            // Unfortunately, VC++ doesn't support std::aligned_alloc from C++/17 spec:
            // https://developercommunity.visualstudio.com/content/problem/468021/c17-stdaligned-alloc缺失.html

            // Allocate aligned block of memory
            inline void *alignedMalloc(size_t size, size_t alignment)
            {
#ifdef _MSC_VER
                return _aligned_malloc(size, alignment);
#else
                return aligned_alloc(alignment, size);
#endif
            }

            // Free aligned block of memory
            inline void alignedFree(void *pointer)
            {
#ifdef _MSC_VER
                _aligned_free(pointer);
#else
                free(pointer);
#endif
            }

            // Changes the size of the memory block pointed to by memblock. The function may move the memory block to a new location
            inline void *alignedRealloc(void *memblock, size_t size, size_t alignment)
            {
                // It's only used by stb_image.
#ifdef _MSC_VER
                return _aligned_realloc(memblock, size, alignment);
#else
                // Unfortunately, aligned_realloc is only available on Windows. Implementing a workaround:
                // https://stackoverflow.com/a/9078627/126995
                void *const reallocated = realloc(memblock, size);
                const bool isAligned = (0 == (((size_t)reallocated) % alignment));
                if (isAligned || nullptr == reallocated)
                    return reallocated;

                void *const copy = aligned_alloc(alignment, size);
                if (nullptr == copy)
                {
                    free(reallocated);
                    return nullptr;
                }
                memcpy(copy, reallocated, size);
                free(reallocated);
                return copy;
#endif
            }

            // Enables std::unique_ptr to release aligned memory, without using a custom deleter which would double the size of the smart pointer.
            struct AlignedDeleter
            {
                inline void operator()(void *pointer)
                {
                    alignedFree(pointer);
                }
            };
        } // namespace details
        // Allocate and return block of memory aligned by at least 32 bytes. This does not call constructors, the memory is uninitialized. Destructors aren't called, either.
        // If that's not what you want, you can wrap alignedMalloc/alignedFree into custom allocator, and use std::vector instead: https://stackoverflow.com/a/12942652/126995
        // 一个比较安全的方案管理raw pointer
        template <class T>
        inline std::unique_ptr<T[], details::AlignedDeleter> alignedArray(size_t size)
        {
            const size_t minimumAlignment = 32;
            const size_t align = std::max(alignof(T), minimumAlignment);

            if (size <= 0)
                throw std::invalid_argument("alignedArray() function doesn't support zero-length arrays.");
            T *const pointer = (T *)details::alignedMalloc(size * sizeof(T), align);
            if (nullptr == pointer)
                throw std::bad_alloc();

            return std::unique_ptr<T[], details::AlignedDeleter>{pointer};
        }

    } // namespace alloc
} // namespace zjwang