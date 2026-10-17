#ifndef GREEKS_H
#define GREEKS_H

#include <cmath>

#include "cdf.h"
#include "eu_option.h"

// Closed-form Black-Scholes-Merton Greeks (continuous dividend yield q).
//
// Units are the raw analytic ones - the Python/UI layer rescales for display:
//   delta : dV/dS                         (per 1.00 of spot)
//   gamma : d2V/dS2
//   vega  : dV/dsigma                     (per 1.00 = 100 vol points; divide by 100 for "per 1%")
//   theta : dV/d(calendar time) = -dV/dT  (per year; divide by 365 for "per day")
//   rho   : dV/dr                         (per 1.00 = 100%; divide by 100 for "per 1%")
//
//   delta_call = e^{-qT} N(d1)             delta_put = -e^{-qT} N(-d1)
//   gamma      = e^{-qT} phi(d1) / (S sigma sqrt(T))
//   vega       = S e^{-qT} phi(d1) sqrt(T)
//   theta_call = -S e^{-qT} phi(d1) sigma / (2 sqrt(T)) - r K e^{-rT} N(d2)  + q S e^{-qT} N(d1)
//   theta_put  = -S e^{-qT} phi(d1) sigma / (2 sqrt(T)) + r K e^{-rT} N(-d2) - q S e^{-qT} N(-d1)
//   rho_call   =  K T e^{-rT} N(d2)        rho_put   = -K T e^{-rT} N(-d2)

struct Greeks {
    double price;
    double delta;
    double gamma;
    double vega;
    double theta;
    double rho;
};

// Price and all Greeks in one pass (d1, d2 and the discount factors computed once).
inline Greeks bs_all(double S, double K, double r, double t, double sigma,
                     OptionType type, double q = 0.0) {
    validate_inputs(S, K, t, sigma);
    const D1D2 d = compute_d1_d2(S, K, r, t, sigma, q);
    const double sqrt_t = std::sqrt(t);
    const double disc_r = std::exp(-r * t);
    const double disc_q = std::exp(-q * t);
    const double phi_d1 = pdf(d.d1);

    Greeks g{};
    g.gamma = disc_q * phi_d1 / (S * sigma * sqrt_t);
    g.vega  = S * disc_q * phi_d1 * sqrt_t;
    const double decay = -S * disc_q * phi_d1 * sigma / (2.0 * sqrt_t);

    if (type == OptionType::Call) {
        g.price = S * disc_q * cdf(d.d1) - K * disc_r * cdf(d.d2);
        g.delta = disc_q * cdf(d.d1);
        g.theta = decay - r * K * disc_r * cdf(d.d2) + q * S * disc_q * cdf(d.d1);
        g.rho   = K * t * disc_r * cdf(d.d2);
    } else {
        g.price = K * disc_r * cdf(-d.d2) - S * disc_q * cdf(-d.d1);
        g.delta = -disc_q * cdf(-d.d1);
        g.theta = decay + r * K * disc_r * cdf(-d.d2) - q * S * disc_q * cdf(-d.d1);
        g.rho   = -K * t * disc_r * cdf(-d.d2);
    }
    return g;
}

// Single-Greek helpers with the original names and argument order.
inline double delta(double S, double K, double r, double t, double sigma, OptionType type, double q = 0.0) {
    return bs_all(S, K, r, t, sigma, type, q).delta;
}
inline double gamma(double S, double K, double r, double t, double sigma, OptionType type, double q = 0.0) {
    return bs_all(S, K, r, t, sigma, type, q).gamma;
}
inline double vega(double S, double K, double r, double t, double sigma, OptionType type, double q = 0.0) {
    return bs_all(S, K, r, t, sigma, type, q).vega;
}
inline double theta(double S, double K, double r, double t, double sigma, OptionType type, double q = 0.0) {
    return bs_all(S, K, r, t, sigma, type, q).theta;
}
inline double rho(double S, double K, double r, double t, double sigma, OptionType type, double q = 0.0) {
    return bs_all(S, K, r, t, sigma, type, q).rho;
}

#endif
