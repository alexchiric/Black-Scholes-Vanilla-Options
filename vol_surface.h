#ifndef VOL_SURFACE_H
#define VOL_SURFACE_H

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <vector>

#include "eu_option.h"
#include "greeks.h"

// Implied volatility under the Black-Scholes-Merton model.
//
// Method: the model price is strictly increasing in sigma (vega > 0), so
//   f(sigma) = BS(sigma) - market_price
// has a single root inside a bracket [SIGMA_MIN, SIGMA_MAX]. We use Newton's method
// for speed and fall back to bisection whenever the Newton step leaves the current
// bracket (e.g. vega ~ 0 for deep ITM/OTM or very short-dated options), so the solver
// can neither diverge nor loop forever.
//
// Before solving, the market price is checked against the no-arbitrage bounds
//   call: max(S e^{-qT} - K e^{-rT}, 0) <= C <= S e^{-qT}
//   put : max(K e^{-rT} - S e^{-qT}, 0) <= P <= K e^{-rT}
// A price outside (or on the edge of) the bounds has no implied volatility and is
// reported through IVStatus instead of returning a meaningless number.

enum class IVStatus {
    Ok,
    BadInput,         // non-finite input, S/K/t <= 0 or negative price
    BelowIntrinsic,   // price below the no-arbitrage lower bound
    AboveUpperBound,  // price above the no-arbitrage upper bound
    NoTimeValue,      // price (numerically) equal to intrinsic value: sigma -> 0, not identifiable
    VolTooHigh,       // implied vol above SIGMA_MAX
    NoConvergence     // iteration cap reached (should not happen; kept as a safety net)
};

inline const char* iv_status_str(IVStatus s) {
    switch (s) {
        case IVStatus::Ok:              return "ok";
        case IVStatus::BadInput:        return "bad_input";
        case IVStatus::BelowIntrinsic:  return "below_intrinsic";
        case IVStatus::AboveUpperBound: return "above_upper_bound";
        case IVStatus::NoTimeValue:     return "no_time_value";
        case IVStatus::VolTooHigh:      return "vol_too_high";
        case IVStatus::NoConvergence:   return "no_convergence";
    }
    return "unknown";
}

struct IVResult {
    double iv;        // NaN unless status == Ok
    IVStatus status;
    int iterations;
};

namespace iv_const {
constexpr double SIGMA_MIN = 1e-6;   // 0.0001%
constexpr double SIGMA_MAX = 10.0;   // 1000%
constexpr int    MAX_ITER  = 100;
constexpr double TWO_PI    = 6.283185307179586476925286766559;
}  // namespace iv_const

inline IVResult implied_volatility_checked(double S, double K, double r, double t,
                                           OptionType type, double market_price, double q = 0.0) {
    const double nan = std::numeric_limits<double>::quiet_NaN();

    if (!std::isfinite(S) || !std::isfinite(K) || !std::isfinite(r) || !std::isfinite(t) ||
        !std::isfinite(q) || !std::isfinite(market_price) ||
        !(S > 0.0) || !(K > 0.0) || !(t > 0.0) || market_price < 0.0) {
        return {nan, IVStatus::BadInput, 0};
    }

    const bool   is_call = (type == OptionType::Call);
    const double fwd_s   = S * std::exp(-q * t);   // PV of the asset leg
    const double pv_k    = K * std::exp(-r * t);   // PV of the strike
    const double lower   = is_call ? std::max(fwd_s - pv_k, 0.0) : std::max(pv_k - fwd_s, 0.0);
    const double upper   = is_call ? fwd_s : pv_k;
    const double bound_tol = 1e-10 * std::max(1.0, S);  // tolerance for the bound checks
    const double conv_tol  = 1e-12 * std::max(1.0, S);  // tolerance on |BS(sigma) - price|

    if (market_price < lower - bound_tol) return {nan, IVStatus::BelowIntrinsic, 0};
    if (market_price > upper + bound_tol) return {nan, IVStatus::AboveUpperBound, 0};
    if (market_price <= lower + bound_tol) return {nan, IVStatus::NoTimeValue, 0};
    if (market_price >= upper - bound_tol) return {nan, IVStatus::VolTooHigh, 0};

    double lo = iv_const::SIGMA_MIN;
    double hi = iv_const::SIGMA_MAX;
    if (eu_option(S, K, r, t, lo, type, q) >= market_price) return {nan, IVStatus::NoTimeValue, 0};
    if (eu_option(S, K, r, t, hi, type, q) <= market_price) return {nan, IVStatus::VolTooHigh, 0};

    // Starting point: Brenner-Subrahmanyam at-the-money approximation, clipped to a sane range.
    // It only affects speed - correctness comes from the bracketing.
    double sigma = std::sqrt(iv_const::TWO_PI / t) * market_price / S;
    sigma = std::min(std::max(sigma, 0.05), 3.0);

    for (int i = 1; i <= iv_const::MAX_ITER; ++i) {
        const Greeks g = bs_all(S, K, r, t, sigma, type, q);
        const double f = g.price - market_price;
        if (std::fabs(f) <= conv_tol) return {sigma, IVStatus::Ok, i};

        // f is increasing in sigma: a positive residual means sigma is too high.
        if (f > 0.0) hi = sigma; else lo = sigma;

        double next = (g.vega > 1e-14) ? sigma - f / g.vega : nan;   // Newton step
        if (!(next > lo && next < hi)) next = 0.5 * (lo + hi);       // bisection fallback

        if (std::fabs(next - sigma) <= 1e-13 * std::max(1.0, sigma) || (hi - lo) <= 1e-14) {
            return {next, IVStatus::Ok, i};
        }
        sigma = next;
    }
    return {sigma, IVStatus::NoConvergence, iv_const::MAX_ITER};
}

// Convenience wrapper with the original signature: returns the implied vol, or NaN
// when none exists (inspect implied_volatility_checked for the reason).
inline double implied_volatility(double S, double K, double r, double t,
                                 OptionType type, double market_price, double q = 0.0) {
    return implied_volatility_checked(S, K, r, t, type, market_price, q).iv;
}

// Volatility smile: implied vol of every (strike, market price) pair for one expiry.
inline std::vector<IVResult> vol_smile(double S, double r, double t, OptionType type,
                                       const std::vector<double>& strikes,
                                       const std::vector<double>& market_prices, double q = 0.0) {
    if (strikes.size() != market_prices.size()) {
        throw std::invalid_argument("strikes and market_prices must have the same length");
    }
    std::vector<IVResult> out;
    out.reserve(strikes.size());
    for (std::size_t i = 0; i < strikes.size(); ++i) {
        out.push_back(implied_volatility_checked(S, strikes[i], r, t, type, market_prices[i], q));
    }
    return out;
}

#endif
