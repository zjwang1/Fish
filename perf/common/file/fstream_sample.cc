#include <fstream>

int main()
{
    {
        std::ofstream out("data", std::ios::app);
        out << "2";
        out.close();
    }
    return 0;
}