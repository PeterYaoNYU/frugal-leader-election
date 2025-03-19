#include <vector>
#include <thread>
#include <queue>
#include <functional>
#include <mutex>
#include <condition_variable>

class ThreadPool {
public:
    ThreadPool(size_t num_threads): stop(false) 
    {
        for (size_t i = 0; i < num_threads; ++i) {
            workers.emplace_back([this] {
                for (;;) {
                    std::function<void()> task;
                    {
                        std::unique_lock<std::mutex> lock(this->tasks_mutex);
                        this->cond_var.wait(lock, [this] { return this->stop || !this->tasks.empty(); });
                        if (this->stop && this->tasks.empty()) {
                            return;
                        }
                        task = std::move(this->tasks.front());
                        this->tasks.pop();
                    }
                    task();
                }
            });
        }
    }

    void enqueue(std::function<void()> task) {
        {
            std::unique_lock<std::mutex> lock(tasks_mutex);
            tasks.push(task);
        }
        cond_var.notify_one();
    }


    ~ThreadPool() {
        {
            std::unique_lock<std::mutex> lock(tasks_mutex);
            stop = true;
        }
        cond_var.notify_all();
        for (std::thread &worker : workers) {
            worker.join();
        }
    }


private:
    std::vector<std::thread> workers;
    std::queue<std::function<void()>> tasks;
    std::mutex tasks_mutex;
    std::condition_variable cond_var;
    bool stop;
}