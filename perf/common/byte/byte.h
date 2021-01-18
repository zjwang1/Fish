#pragma once

namespace zjwang
{
    /**
     * 定义一些字节与类型转换的函数
     */
    namespace byte
    {
        #define to_uint64(buffer,n) ((uint64_t)buffer[n+7] << 56 | (uint64_t)buffer[n+6] << 48 | (uint64_t)buffer[n+5] << 40  | (uint64_t)buffer[n+4] << 32 | (uint64_t) buffer[n+3] << 24 | (uint64_t)buffer[n+2] << 16 | (uint64_t)buffer[n+1] << 8  | (uint64_t)buffer[n])
    }

}