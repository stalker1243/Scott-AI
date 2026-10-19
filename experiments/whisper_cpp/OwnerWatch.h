#pragma once
// The worker stops itself if its real parent dies, including during model loading.
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdlib>
#include <mutex>
#include <stdexcept>
#include <thread>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <tlhelp32.h>
#else
#include <unistd.h>
#ifdef __linux__
#include <cerrno>
#include <poll.h>
#include <sys/syscall.h>
#endif
#endif

class OwnerWatch {
    struct Resource {
#ifdef _WIN32
        HANDLE handle = nullptr;
        ~Resource() { if (handle && handle != INVALID_HANDLE_VALUE) CloseHandle(handle); }
#else
        int descriptor = -1;
        ~Resource() { if (descriptor >= 0) close(descriptor); }
#endif
    } resource_;
    std::uint32_t pid_ = 0;
    std::mutex mutex_;
    std::condition_variable changed_;
    bool stopping_ = false;
    std::thread thread_;

    bool alive() const {
#ifdef _WIN32
        return WaitForSingleObject(resource_.handle, 0) == WAIT_TIMEOUT;
#else
        // Only the kernel parent relation is checked; a reused unrelated PID
        // cannot acquire this child. Nothing ever signals the parent process.
        if (static_cast<std::uint32_t>(getppid()) != pid_) return false;
#ifdef __linux__
        if (resource_.descriptor >= 0) {
            pollfd descriptor = {resource_.descriptor, POLLIN, 0};
            const auto result = poll(&descriptor, 1, 0);
            return result == 0 || (result < 0 && errno == EINTR);
        }
#endif
        return true;
#endif
    }

public:
    explicit OwnerWatch(std::uint32_t expected = 0) {
#ifdef _WIN32
        Resource snapshot;
        snapshot.handle = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if (snapshot.handle == INVALID_HANDLE_VALUE) throw std::runtime_error("owner_unavailable");
        PROCESSENTRY32W entry = {};
        entry.dwSize = sizeof(entry);
        if (Process32FirstW(snapshot.handle, &entry)) {
            do {
                if (entry.th32ProcessID == GetCurrentProcessId()) {
                    pid_ = entry.th32ParentProcessID;
                    break;
                }
            } while (Process32NextW(snapshot.handle, &entry));
        }
        if (!pid_ || (expected && expected != pid_)) throw std::runtime_error("owner_mismatch");
        resource_.handle = OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid_);
        FILETIME owner_start, worker_start, exit_time, kernel_time, user_time;
        if (!resource_.handle ||
            !GetProcessTimes(resource_.handle, &owner_start, &exit_time, &kernel_time, &user_time) ||
            !GetProcessTimes(GetCurrentProcess(), &worker_start, &exit_time, &kernel_time, &user_time) ||
            CompareFileTime(&owner_start, &worker_start) > 0)
            throw std::runtime_error("owner_unavailable");
        // The retained handle anchors the original process, even after PID reuse.
#else
        pid_ = static_cast<std::uint32_t>(getppid());
        if (!pid_ || (expected && expected != pid_)) throw std::runtime_error("owner_mismatch");
#if defined(__linux__) && defined(SYS_pidfd_open)
        resource_.descriptor = static_cast<int>(syscall(SYS_pidfd_open, pid_, 0));
#endif
        if (static_cast<std::uint32_t>(getppid()) != pid_) throw std::runtime_error("owner_unavailable");
#endif
        if (!alive()) throw std::runtime_error("owner_unavailable");
        thread_ = std::thread([this] {
            for (;;) {
                if (!alive()) std::_Exit(4);
                std::unique_lock<std::mutex> lock(mutex_);
                if (changed_.wait_for(lock, std::chrono::milliseconds(50), [this] { return stopping_; })) return;
            }
        });
    }
    ~OwnerWatch() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            stopping_ = true;
        }
        changed_.notify_all();
        if (thread_.joinable()) thread_.join();
    }
    OwnerWatch(const OwnerWatch &) = delete;
    OwnerWatch & operator=(const OwnerWatch &) = delete;
    std::uint32_t pid() const { return pid_; }
    const char * mode() const {
#ifdef _WIN32
        return "windows_handle";
#elif defined(__linux__)
        return resource_.descriptor >= 0 ? "linux_pidfd" : "posix_parent";
#else
        return "posix_parent";
#endif
    }
};
