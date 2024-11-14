#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <string>

#include "cdf.h"
#include "eu_option.h"
#include "greeks.h"
#include "vol_surface.h"


int main() {
    std::ifstream file("temp.bin", std::ios::binary);
    
    if (!file) {
        std::cerr << "Unable to open file!" << std::endl;
        return 1;  // Error exit if the file can't be opened
    }

    file.seekg(0, std::ios::end);
    std::streampos fileSize = file.tellg();
    file.seekg(0, std::ios::beg);  // Move the pointer back to the beginning

    size_t numElements = fileSize / sizeof(double);

    // Create a vector to hold the data
    std::vector<double> data(numElements);

    // Read the file into the vector
    file.read(reinterpret_cast<char*>(data.data()), fileSize);

    //Close file
    file.close();


    return 0;

}
