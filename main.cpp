// Small command-line demo of the pricing core (build with `make demo`).
// For batch work use bs_engine (see bs_engine.cpp) or the Python layer.

#include <iostream>

#include "eu_option.h"
#include "greeks.h"
#include "vol_surface.h"

int main() {
    // Example: 2-day AAPL call
    const double S = 230.76;           // spot
    const double K = 230.0;            // strike
    const double r = 0.05;             // risk-free rate
    const double q = 0.0;              // dividend yield
    const double t = 2.0 / 365.0;      // time to expiry in years (ACT/365)
    const double market_price = 2.20;  // observed option price
    const OptionType type = OptionType::Call;

    const IVResult iv = implied_volatility_checked(S, K, r, t, type, market_price, q);
    std::cout << "Implied volatility : ";
    if (iv.status != IVStatus::Ok) {
        std::cout << "n/a (" << iv_status_str(iv.status) << ")\n";
        return 1;
    }
    std::cout << iv.iv << "  (" << iv.iterations << " iterations)\n";

    const Greeks g = bs_all(S, K, r, t, iv.iv, type, q);
    std::cout << "Price              : " << g.price << "\n"
              << "Delta              : " << g.delta << "\n"
              << "Gamma              : " << g.gamma << "\n"
              << "Vega  (per 1 vol pt): " << g.vega / 100.0 << "\n"
              << "Theta (per day)    : " << g.theta / 365.0 << "\n"
              << "Rho   (per 1% rate): " << g.rho / 100.0 << "\n";
    return 0;
}
