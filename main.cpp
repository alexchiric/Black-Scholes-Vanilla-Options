#include <iostream>
#include <math.h>
#include <array>

#include "cdf.h"
#include "eu_option.h"
#include "greeks.h"
#include "vol_surface.h"

using namespace std;

int main() {
    // Example option parameters
    double S = 100.0;  // Stock price
    double K = 100.0;  // Strike price
    double r = 0.05;   // Risk-free rate
    double t = 0.007937;    // Time to maturity (1 year)
    double sigma = 0.2;  // Volatility
    double market_price = 130.75;
    std::string option_type = "call";  // Call or Put option

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

    double implied_vol = implied_volatility(S, K, r, t, option_type, market_price);

    std::cout << "Implied Volatility: " << implied_vol << std::endl;

    return 0;
}