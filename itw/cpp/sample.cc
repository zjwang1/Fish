#include <tuple>
#include <vector>
#include <iostream>

// std::tuple<int32_t, std::vector<int32_t>> f() {
auto f() {
    std::vector<int32_t> v{1, 2, 3, 4};
    return std::make_tuple(4, std::move(v));
}
int main() {
    auto [rtn, v] = f();
    std::cout << "rtn is " << rtn << ", v[0] is " << v[0] << "\n";
    return 0;
}