#ifndef VOL_SURFACE_H
#define VOL_SURFACE_H

#include <cmath>
#include <string>
#include <stdexcept>

#include "greeks.h"
#include "eu_option.h"

double implied_volatility(double S, double K, double r, double t, string option_type, double market_price){
    // Calculate the Black-Scholes Implied Volatilies using the Newton-Raphson method
    double sigma = 0.2; // Initial Guess
    double tolerance = 0.01; // Convergence Tolerance
    int max_iterations = 100; // Max Iterations

    //Use Newton-Raphson root-finding method
    for (int i = 0; i <= max_iterations; i++){
        double price = eu_option(S, K, r, t, sigma, option_type);
        double vega_value = vega(S, K, r, t, sigma, option_type);

        //Newton-Raphson Model sigma_1 = sigma_0 - f(sigma)/f'(sigma)
        double diff = price - market_price;
        sigma -= diff / vega_value;

        if (abs(diff) < tolerance) {
            return sigma;
        }
        else {
            throw std::invalid_argument("Could not reach convergence.");
        }
    }

}
#endif