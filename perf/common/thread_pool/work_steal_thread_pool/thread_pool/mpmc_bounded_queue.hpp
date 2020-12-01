// Copyright (c) 2010-2011 Dmitry Vyukov. All rights reserved.
//
// Redistribution and use in source and binary forms, with or without
// modification, are permitted provided
// that the following conditions are met:
//
//   1. Redistributions of source code must retain the above copyright notice,
//   this list of
//      conditions and the following disclaimer.
//
//   2. Redistributions in binary form must reproduce the above copyright
//   notice, this list
//      of conditions and the following disclaimer in the documentation and/or
//      other materials
//      provided with the distribution.
//
// THIS SOFTWARE IS PROVIDED BY DMITRY VYUKOV "AS IS" AND ANY EXPRESS OR IMPLIED
// WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
// MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO
// EVENT
// SHALL DMITRY VYUKOV OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
// INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
// LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
// OR
// PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
// LIABILITY,
// WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
// OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
// ADVISED OF
// THE POSSIBILITY OF SUCH DAMAGE.
//
// The views and conclusions contained in the software and documentation are
// those of the authors and
// should not be interpreted as representing official policies, either expressed
// or implied, of Dmitry Vyukov.

#pragma once

#include <atomic>
#include <type_traits>
#include <vector>
#include <stdexcept>

namespace zjwang
{

/**
 * @brief The MPMCBoundedQueue class implements bounded
 * multi-producers/multi-consumers lock-free queue.
 * Doesn't accept non-movable types as T.
 * Inspired by Dmitry Vyukov's mpmc queue.
 * http://www.1024cores.net/home/lock-free-algorithms/queues/bounded-mpmc-queue
 */
template <typename T>
class MPMCBoundedQueue
{
    static_assert(
        std::is_move_constructible<T>::value, "Should be of movable type");

public:
    /**
     * @brief MPMCBoundedQueue Constructor.
     * @param size Power of 2 number - queue length.
     * @throws std::invalid_argument if size is bad.
     */
    explicit MPMCBoundedQueue(size_t size);

    /**
     * @brief Move ctor implementation.
     */
    MPMCBoundedQueue(MPMCBoundedQueue&& rhs) noexcept;

    /**
     * @brief Move assignment implementaion.
     */
    MPMCBoundedQueue& operator=(MPMCBoundedQueue&& rhs) noexcept;

    /**
     * @brief Push Push data to queue.
     * @param data Data to be Pushed.
     * @return true on success.
     */
    template <typename U>
    bool Push(U&& data);

    /**
     * @brief Pop Pop data from queue.
     * @param data Place to store Popped data.
     * @return true on sucess.
     */
    bool Pop(T& data);

private:
    struct Cell
    {
        std::atomic<size_t> sequence;
        T data;

        Cell() = default;

        Cell(const Cell&) = delete;
        Cell& operator=(const Cell&) = delete;

        Cell(Cell&& rhs)
            : sequence(rhs.sequence.load()), data(std::move(rhs.data))
        {
        }

        Cell& operator=(Cell&& rhs)
        {
            sequence = rhs.sequence.load();
            data = std::move(rhs.data);

            return *this;
        }
    };

private:
    typedef char Cacheline[64];

    Cacheline pad0;
    std::vector<Cell> mBuffer;
    /* const */ size_t mBufferMask;
    Cacheline pad1;
    std::atomic<size_t> mEnqueuePos;
    Cacheline pad2;
    std::atomic<size_t> mDequeuePos;
    Cacheline pad3;
};


/// Implementation

template <typename T>
inline MPMCBoundedQueue<T>::MPMCBoundedQueue(size_t size)
    : mBuffer(size), mBufferMask(size - 1), mEnqueuePos(0),
      mDequeuePos(0)
{
    bool size_is_power_of_2 = (size >= 2) && ((size & (size - 1)) == 0);
    if(!size_is_power_of_2)
    {
        throw std::invalid_argument("buffer size should be a power of 2");
    }

    for(size_t i = 0; i < size; ++i)
    {
        mBuffer[i].sequence = i;
    }
}

template <typename T>
inline MPMCBoundedQueue<T>::MPMCBoundedQueue(MPMCBoundedQueue&& rhs) noexcept
{
    *this = rhs;
}

template <typename T>
inline MPMCBoundedQueue<T>& MPMCBoundedQueue<T>::operator=(MPMCBoundedQueue&& rhs) noexcept
{
    if (this != &rhs)
    {
        mBuffer = std::move(rhs.mBuffer);
        mBufferMask = std::move(rhs.mBufferMask);
        mEnqueuePos = rhs.mEnqueuePos.load();
        mDequeuePos = rhs.mDequeuePos.load();
    }
    return *this;
}

template <typename T>
template <typename U>
inline bool MPMCBoundedQueue<T>::Push(U&& data)
{
    Cell* cell;
    size_t pos = mEnqueuePos.load(std::memory_order_relaxed);
    for(;;)
    {
        cell = &mBuffer[pos & mBufferMask];
        size_t seq = cell->sequence.load(std::memory_order_acquire);
        intptr_t dif = (intptr_t)seq - (intptr_t)pos;
        if(dif == 0)
        {
            if(mEnqueuePos.compare_exchange_weak(
                   pos, pos + 1, std::memory_order_relaxed))
            {
                break;
            }
        }
        else if(dif < 0)
        {
            return false;
        }
        else
        {
            pos = mEnqueuePos.load(std::memory_order_relaxed);
        }
    }

    cell->data = std::forward<U>(data);

    cell->sequence.store(pos + 1, std::memory_order_release);

    return true;
}

template <typename T>
inline bool MPMCBoundedQueue<T>::Pop(T& data)
{
    Cell* cell;
    size_t pos = mDequeuePos.load(std::memory_order_relaxed);
    for(;;)
    {
        cell = &mBuffer[pos & mBufferMask];
        size_t seq = cell->sequence.load(std::memory_order_acquire);
        intptr_t dif = (intptr_t)seq - (intptr_t)(pos + 1);
        if(dif == 0)
        {
            if(mDequeuePos.compare_exchange_weak(
                   pos, pos + 1, std::memory_order_relaxed))
            {
                break;
            }
        }
        else if(dif < 0)
        {
            return false;
        }
        else
        {
            pos = mDequeuePos.load(std::memory_order_relaxed);
        }
    }

    data = std::move(cell->data);

    cell->sequence.store(
        pos + mBufferMask + 1, std::memory_order_release);

    return true;
}

}
