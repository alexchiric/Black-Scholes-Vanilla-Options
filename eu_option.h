#ifndef EU_OPTION_H
#define EU_OPTION_H

#include <cctype>
#include <cmath>
#include <stdexcept>
#include <string>

#include "cdf.h"

// Black-Scholes-Merton price of a European option on an asset paying a
// continuous dividend yield q (q = 0 gives the classical Black-Scholes model).
//
//   d1 = [ ln(S/K) + (r - q + sigma^2/2) * T ] / (sigma * sqrt(T))
//   d2 = d1 - sigma * sqrt(T)
//
//   Call = S e^{-qT} N(d1)  - K e^{-rT} N(d2)
//   Put  = K e^{-rT} N(-d2) - S e^{-qT} N(-d1)
//
// Argument order is kept from the original code: (S, K, r, t, sigma, type [, q]).

enum class OptionType { Call, Put };

// Accepts "call"/"put" in any case, plus "c"/"p" and "1"/"0" (1 = call, 0 = put,
// the encoding used by the Python layer).
inline OptionType parse_option_type(const std::string& s) {
    std::string t;
    for (char c : s) t += static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    if (t == "call" || t == "c" || t == "1") return OptionType::Call;
    if (t == "put" || t == "p" || t == "0") return OptionType::Put;
    throw std::invalid_argument("Invalid option type '" + s + "'. Use 'call' or 'put'.");
}

// Throws std::invalid_argument when the inputs are outside the model's domain.
inline void validate_inputs(double S, double K, double t, double sigma) {
    if (!(S > 0.0) || !std::isfinite(S))         throw std::invalid_argument("S must be positive and finite");
    if (!(K > 0.0) || !std::isfinite(K))         throw std::invalid_argument("K must be positive and finite");
    if (!(t > 0.0) || !std::isfinite(t))         throw std::invalid_argument("t must be positive and finite");
    if (!(sigma > 0.0) || !std::isfinite(sigma)) throw std::invalid_argument("sigma must be positive and finite");
}

struct D1D2 {
    double d1;
    double d2;
};

inline D1D2 compute_d1_d2(double S, double K, double r, double t, double sigma, double q = 0.0) {
    const double sigma_sqrt_t = sigma * std::sqrt(t);
    const double d1 = (std::log(S / K) + (r - q + 0.5 * sigma * sigma) * t) / sigma_sqrt_t;
    return {d1, d1 - sigma_sqrt_t};
}

inline double eu_option(double S, double K, double r, double t, double sigma,
                        OptionType type, double q = 0.0) {
    validate_inputs(S, K, t, sigma);
    const D1D2 d = compute_d1_d2(S, K, r, t, sigma, q);
    const double disc_r = std::exp(-r * t);
    const double disc_q = std::exp(-q * t);

    if (type == OptionType::Call) {
        return S * disc_q * cdf(d.d1) - K * disc_r * cdf(d.d2);
    }
    return K * disc_r * cdf(-d.d2) - S * disc_q * cdf(-d.d1);
}

#endif
