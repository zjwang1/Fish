#pragma once

#include <atomic>
#include <thread>

namespace zjwang
{

/**
 * @brief The Worker class owns task queue and executing thread.
 * In thread it tries to pop task from queue. If queue is empty then it tries
 * to steal task from the sibling worker. If steal was unsuccessful then spins
 * with one millisecond delay.
 */
template <typename Task, template<typename> class Queue>
class Worker
{
public:
    /**
     * @brief Worker Constructor.
     * @param queue_size Length of undelaying task queue.
     */
    explicit Worker(size_t queue_size);

    /**
     * @brief Move ctor implementation.
     */
    Worker(Worker&& rhs) noexcept;

    /**
     * @brief Move assignment implementaion.
     */
    Worker& operator=(Worker&& rhs) noexcept;

    /**
     * @brief start Create the executing thread and start tasks execution.
     * @param id Worker ID.
     * @param stealDonor Sibling worker to steal task from it.
     */
    void Start(size_t id, Worker* stealDonor);

    /**
     * @brief stop Stop all worker's thread and stealing activity.
     * Waits until the executing thread became finished.
     */
    void Stop();

    /**
     * @brief post Post task to queue.
     * @param handler Handler to be executed in executing thread.
     * @return true on success.
     */
    template <typename Handler>
    bool Post(Handler&& handler);

    /**
     * @brief steal Steal one task from this worker queue.
     * @param task Place for stealed task to be stored.
     * @return true on success.
     */
    bool Steal(Task& task);

    /**
     * @brief getWorkerIdForCurrentThread Return worker ID associated with
     * current thread if exists.
     * @return Worker ID.
     */
    static size_t GetWorkerIdForCurrentThread();

private:
    /**
     * @brief threadFunc Executing thread function.
     * @param id Worker ID to be associated with this thread.
     * @param stealDonor Sibling worker to steal task from it.
     */
    void ThreadFunc(size_t id, Worker* stealDonor);

    Queue<Task> mQueue;
    std::atomic<bool> mRunningFlag;
    std::thread mThread;
};


/// Implementation

namespace detail
{
    inline size_t* ThreadId()
    {
        static thread_local size_t tssId = -1u;
        return &tssId;
    }
}

template <typename Task, template<typename> class Queue>
inline Worker<Task, Queue>::Worker(size_t queueSize)
    : mQueue(queueSize)
    , mRunningFlag(true)
{
}

template <typename Task, template<typename> class Queue>
inline Worker<Task, Queue>::Worker(Worker&& rhs) noexcept
{
    *this = rhs;
}

template <typename Task, template<typename> class Queue>
inline Worker<Task, Queue>& Worker<Task, Queue>::operator=(Worker&& rhs) noexcept
{
    if (this != &rhs)
    {
        mQueue = std::move(rhs.mQueue);
        mRunningFlag = rhs.mRunningFlag.load();
        mThread = std::move(rhs.mThread);
    }
    return *this;
}

template <typename Task, template<typename> class Queue>
inline void Worker<Task, Queue>::Stop()
{
    mRunningFlag.store(false, std::memory_order_relaxed);
    mThread.join();
}

template <typename Task, template<typename> class Queue>
inline void Worker<Task, Queue>::Start(size_t id, Worker* stealDonor)
{
    mThread = std::thread(&Worker<Task, Queue>::ThreadFunc, this, id, stealDonor);
}

template <typename Task, template<typename> class Queue>
inline size_t Worker<Task, Queue>::GetWorkerIdForCurrentThread()
{
    return *detail::ThreadId();
}

template <typename Task, template<typename> class Queue>
template <typename Handler>
inline bool Worker<Task, Queue>::Post(Handler&& handler)
{
    return mQueue.Push(std::forward<Handler>(handler));
}

template <typename Task, template<typename> class Queue>
inline bool Worker<Task, Queue>::Steal(Task& task)
{
    return mQueue.Pop(task);
}

template <typename Task, template<typename> class Queue>
inline void Worker<Task, Queue>::ThreadFunc(size_t id, Worker* stealDonor)
{
    *detail::ThreadId() = id;

    Task handler;

    while (mRunningFlag.load(std::memory_order_relaxed))
    {
        if (mQueue.Pop(handler) || stealDonor->Steal(handler))
        {
            try
            {
                handler();
            }
            catch(...)
            {
                // suppress all exceptions
            }
        }
        else
        {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }
}

}
