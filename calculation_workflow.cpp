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



    // Example option parameters
    double S = data[5];  // Stock price
    double K = data[0];  // Strike price
    double r = 0.05;   // Risk-free rate
    double t = data[2];    // Time to maturity (1 year)
    double sigma = data[1];  // Volatility
    double market_price = data[3]; //Current Option Price
    std::string option_type; //Declare the options type

    // Call or Put option
    if (data[4] == 1){
        option_type = "call";
    }
    else if(data[4] == 0){
        option_type = "put";
    }
    
    std::cout << option_type;

    // Calculate Greeks
    double price = eu_option(S, K, r, t, sigma, option_type);
    double delta_value = delta(S, K, r, t, sigma, option_type);
    double gamma_value = gamma(S, K, r, t, sigma, option_type);
    double vega_value = vega(S, K, r, t, sigma, option_type);
    double theta_value = theta(S, K, r, t, sigma, option_type);
    double rho_value = rho(S, K, r, t, sigma, option_type);
    
    // Print results
    std::cout << "Price: " << price << std::endl;
    std::cout << "Delta: " << delta_value << std::endl;
    std::cout << "Gamma: " << gamma_value << std::endl;
    std::cout << "Vega: " << vega_value << std::endl;
    std::cout << "Theta: " << theta_value << std::endl;
    std::cout << "Rho: " << rho_value << std::endl;

    return 0;

}
