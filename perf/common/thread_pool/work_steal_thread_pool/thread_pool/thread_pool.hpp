#pragma once

#include "fixed_function.hpp"
#include "mpmc_bounded_queue.hpp"
#include "worker.hpp"

#include <functional>
#include <atomic>
#include <memory>
#include <stdexcept>
#include <vector>

namespace zjwang
{

template <typename Task, template<typename> class Queue>
class ThreadPoolImpl;


using ThreadPool = ThreadPoolImpl<FixedFunction<void(), 128>,
                                  MPMCBoundedQueue>;

/**
 * @brief The ThreadPool class implements thread pool pattern.
 * It is highly scalable and fast.
 * It is header only.
 * It implements both work-stealing and work-distribution balancing
 * startegies.
 * It implements cooperative scheduling strategy for tasks.
 */
template <typename Task, template<typename> class Queue>
class ThreadPoolImpl {
public:

    /**
     * @brief ThreadPool Construct and start new thread pool.
     * @param threadNum Thread numbers.
     * @param BufferSize Bounded Queue Buffer size.
     */    
    ThreadPoolImpl(size_t threadNum = 16, size_t BufferSize = 1024 * 4):
        mWorkers(threadNum),
        mNextWorker(0)
    {
        for(auto& workerPtr : mWorkers)
        {
            workerPtr.reset(new Worker<Task, Queue>(BufferSize));
        }
        for(size_t i = 0; i < mWorkers.size(); ++i)
        {
            Worker<Task, Queue>* stealDonor =
                                    mWorkers[(i + 1) % mWorkers.size()].get();
            mWorkers[i]->Start(i, stealDonor);
        }
    }

    /**
     * @brief Don't use copy constructor.
     */
    ThreadPoolImpl(ThreadPoolImpl& rhs) = delete;

    /**
     * @brief Don't use copy assignment.
     */
    ThreadPoolImpl& operator=(ThreadPoolImpl& rhs) = delete;

    /**
     * @brief Move ctor implementation.
     */
    ThreadPoolImpl(ThreadPoolImpl&& rhs) noexcept
    {
        *this = rhs;
    }

     /**
     * @brief Move assignment implementaion.
     */
    ThreadPoolImpl& operator=(ThreadPoolImpl&& rhs) noexcept
    {
        if (this != &rhs)
        {
            mWorkers = std::move(rhs.mWorkers);
            mNextWorker = rhs.mNextWorker.load();
        }
        return *this;
    }

    /**
     * @brief ~ThreadPool Stop all workers and destroy thread pool.
     */
    ~ThreadPoolImpl()
    {
        for (auto& workerPtr : mWorkers)
        {
            workerPtr->Stop();
        }
    }

    /**
     * @brief post Try post job to thread pool.
     * @param handler Handler to be called from thread pool worker. It has
     * to be callable as 'handler()'.
     * @return 'true' on success, false otherwise.
     * @note All exceptions thrown by handler will be suppressed.
     */
    template <typename Handler>
    bool TryPost(Handler&& handler)
    {
        return getWorker().Post(std::forward<Handler>(handler));
    }

    /**
     * @brief post Post job to thread pool.
     * @param handler Handler to be called from thread pool worker. It has
     * to be callable as 'handler()'.
     * @throw std::overflow_error if worker's queue is full.
     * @note All exceptions thrown by handler will be suppressed.
     */
    template <typename Handler>
    void Post(Handler&& handler)
    {
        const auto ok = TryPost(std::forward<Handler>(handler));
        if (!ok)
        {
            throw std::runtime_error("thread pool queue is full");
        }
    }

private:
    Worker<Task, Queue>& getWorker()
    {
        auto id = Worker<Task, Queue>::GetWorkerIdForCurrentThread();

        if (id > mWorkers.size())
        {
            id = mNextWorker.fetch_add(1, std::memory_order_relaxed) %
                mWorkers.size();
        }

        return *mWorkers[id];
    }

    std::vector<std::unique_ptr<Worker<Task, Queue>>> mWorkers;
    std::atomic<size_t> mNextWorker;
};

}
