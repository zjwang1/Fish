#pragma once
#include <unistd.h>
#include <fcntl.h>
#include <arpa/inet.h>
#include <netinet/tcp.h>
#include <string.h>
#include <limits>
#include <memory>

template <uint32_t RecvBufSize>
class SocketTcpConnection
{
public:
    SocketTcpConnection() = default;
    ~SocketTcpConnection() {
        Close("Socket connection destruct");
    }

    bool IsConnected() const { return fd_ != kFdPlaceholder; }

    void Close(const char *reason, bool check_errno = false) {
        if (fd_ >= 0) {
            SaveError(reason, check_errno);
            ::close(fd_);
            fd_ = kFdPlaceholder;
        }
    }

    bool Open(int fd) {
        fd_ = fd;
        head_ = tail_ = 0;

        int flags = fcntl(fd_, F_GETFL, 0);
        if (fcntl(fd_, F_SETFL, flags | O_NONBLOCK) < 0) {
            Close("fcntl O_NONBLOCK error", true);
            return false;
        }

        int yes = 1;
        if (setsockopt(fd_, IPPROTO_TCP, TCP_NODELAY, &yes, sizeof(yes)) < 0) {
            Close("setsockopt TCP_NODELAY error", true);
            return false;
        }
        return true;
    }
protected:
    template<uint32_t>
    friend class SocketTcpServer;

    void SaveError(const char* msg, bool check_errno) {
        snprintf(last_error_, sizeof(last_error_), "%s %s", msg, check_errno ? (const char*)strerror(errno) : "");
    }

    static constexpr int kFdPlaceholder = -1;
    int fd_ = kFdPlaceholder;
    char last_error_[64] = "";
    uint32_t head_;
    uint32_t tail_;
    char recvbuf_[RecvBufSize];
};

template<uint32_t RecvBufSize = 4096>
class SocketTcpServer
{
public:
    using TcpConnection = SocketTcpConnection<RecvBufSize>;
    SocketTcpServer () = default;
    ~SocketTcpServer() { Close("destruct"); }
    bool Init(const char *interface, const char *server_ip, uint16_t server_port) {
        listenfd_ = socket(AF_INET, SOCK_STREAM, 0);
        if (listenfd_ < 0) {
            SaveError("socket error");
            return false;
        }
        int flags = fcntl(listenfd_, F_GETFL, 0);
        if (fcntl(listenfd_, F_SETFL, flags | O_NONBLOCK) < 0) {
            Close("fcntl O_NONBLOCK error");
            return false;
        }
        int yes = 1;
        if (setsockopt(listenfd_, IPPROTO_TCP, TCP_NODELAY, &yes, sizeof(yes)) < 0) {
            Close("setsockopt TCP_NODELAY error");
            return false;
        }

        struct sockaddr_in local_addr;
        local_addr.sin_family = AF_INET;
        inet_pton(AF_INET, server_ip, &(local_addr.sin_addr));
        local_addr.sin_port = htons(server_port);
        bzero(&(local_addr.sin_zero), 8);

        if (bind(listenfd_, (struct sockaddr *)&local_addr, sizeof(local_addr)) < 0) {
            Close("bind error");
            return false;
        }

        if (listen(listenfd_, 5) < 0) {
            Close("listen error");
            return false;
        }
        return true;
    }

    bool accept2(TcpConnection &conn) {
        struct sockaddr_in client_addr;
        socklen_t addr_len = sizeof(client_addr);
        int fd = ::accept(listenfd_, (struct sockaddr *)&client_addr, &addr_len);
        if (fd < 0) {
            return false;
        }
        if (!conn.Open(fd)) {
            return false;
        }
        return true;
    }

    void Close(const char *reason) {
        if (listenfd_ >= 0) {
            SaveError(reason);
            ::close(listenfd_);
            listenfd_ = kFdPlaceholder;
        }
    }
    
private:
    void SaveError(const char* msg) { snprintf(last_error_, sizeof(last_error_), "%s %s", msg, strerror(errno)); }
    static constexpr int kFdPlaceholder = -1;
    int listenfd_ = kFdPlaceholder;
    char last_error_[64] = "";
};