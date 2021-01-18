#include "tcp_server.h"

int main(int argc, char *argv[]) {
    SocketTcpServer<> server;
    server.Init("", "127.0.0.1", 12345);
    while (true) {

    }
    return 0;
}