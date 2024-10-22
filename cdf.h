#ifndef CDF_H
#define CDF_H

#include <array>
#include <cmath>

// Function to calculate the CDF of the normal distribution using the approximation
double cdf(double x){
    // Precomputed constants for scaling the approximation
    const std::array<double, 5> a = {0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429};
    
    // Calculate the components
    double n = (1.0 / std::sqrt(2 * M_PI)) * std::exp(-0.5 * std::pow(x, 2));  // Normal PDF n(x)
    double t = 1.0 / (1.0 + 0.2316419 * std::abs(x));  // t(x)
    double N = 0.0;  // Initialize sum

    // Sum the approximation series
    for (int i = 0; i < 5; i++) {
        N += a[i] * std::pow(t, i + 1);
    }

    // Calculate N(x) for x >= 0
    N = 1.0 - n * N;

    // If x is negative, use symmetry N(-x)
    if (x >= 0) {
        return N;
    } else {
        return 1.0 - N;
    }
}

#endif
