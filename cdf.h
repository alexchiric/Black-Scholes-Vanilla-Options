#ifndef CDF_H
#define CDF_H

#include <cmath>

// Standard normal density and cumulative distribution function.
//
// N(x) is computed from the complementary error function,
//     N(x) = 0.5 * erfc(-x / sqrt(2)),
// which is accurate to machine precision on the whole real line (the previous
// Abramowitz-Stegun polynomial had an absolute error of about 7.5e-8).

namespace bs_const {
constexpr double INV_SQRT_2   = 0.70710678118654752440;  // 1 / sqrt(2)
constexpr double INV_SQRT_2PI = 0.39894228040143267794;  // 1 / sqrt(2*pi)
}  // namespace bs_const

// phi(x): standard normal probability density
inline double pdf(double x) {
    return bs_const::INV_SQRT_2PI * std::exp(-0.5 * x * x);
}

// N(x): standard normal cumulative distribution function
inline double cdf(double x) {
    return 0.5 * std::erfc(-x * bs_const::INV_SQRT_2);
}

#endif
