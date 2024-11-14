#ifndef VOL_SURFACE_H
#define VOL_SURFACE_H

#include <cmath>
#include <string>
#include <stdexcept>
#include <vector>

#include "greeks.h"
#include "eu_option.h"

double implied_volatility(double S, double K, double r, double t, string option_type, double market_price) {
    const double EPSILON = 1e-3; // Convergence tolerance: how close the calculated price must be to the market price
    float sigma = 0.4; //Initial Sigma Guess
    double price = eu_option(S, K, r, t, sigma, option_type); //Initial Price under current sigma guess

    // Iterative process to adjust sigma (volatility) until the price is close enough to the market price
    while (fabs(price - market_price) > EPSILON) {
        // Calculate the vega (first derivative of the option price with respect to sigma)
        double vega_value = vega(S, K, r, t, sigma, option_type); // Corrected from sigma_init to sigma

        // Newton-Raphson update step: adjust sigma using the difference between market price and calculated price
        sigma += (market_price - price) / vega_value;

        // Recalculate the option price with the updated sigma value
        price = eu_option(S, K, r, t, sigma, option_type);
    }

    return sigma;
}

double vol_smile(double S, double K, double r, double t, string option_type, double market_price) {

    return 
}
#endif