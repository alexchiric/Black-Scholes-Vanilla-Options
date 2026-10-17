// Self-contained test suite for the pricing core (no external framework).
// Build and run with:  make test-core
//
// Reference values were produced by an independent closed-form implementation in
// Python (statistics.NormalDist) and, where noted, are the textbook values.

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <random>
#include <string>
#include <vector>

#include "../eu_option.h"
#include "../greeks.h"
#include "../vol_surface.h"

static int g_checks = 0;
static int g_failures = 0;

static void check_close(const char* name, double got, double want, double abs_tol, double rel_tol = 0.0) {
    ++g_checks;
    const double err = std::fabs(got - want);
    if (!(err <= abs_tol + rel_tol * std::fabs(want))) {   // also fails on NaN
        ++g_failures;
        std::printf("FAIL  %-58s got=%.12g want=%.12g err=%.3g\n", name, got, want, err);
    }
}

static void check_true(const char* name, bool cond) {
    ++g_checks;
    if (!cond) {
        ++g_failures;
        std::printf("FAIL  %s\n", name);
    }
}

// Deterministic uniform [0,1) from the raw mt19937 stream (independent of the std library).
struct Rng {
    std::mt19937 gen;
    explicit Rng(std::uint32_t seed) : gen(seed) {}
    double u() { return static_cast<double>(gen()) / 4294967296.0; }
    double in(double a, double b) { return a + (b - a) * u(); }
};

static const OptionType CALL = OptionType::Call;
static const OptionType PUT  = OptionType::Put;

// ---------------------------------------------------------------- textbook values
static void test_textbook_values() {
    // Hull, Options Futures and Other Derivatives: S=42 K=40 r=10% sigma=20% T=0.5 -> c=4.76, p=0.81
    check_close("hull call 42/40", eu_option(42, 40, 0.10, 0.5, 0.20, CALL), 4.76, 0.005);
    check_close("hull put  42/40", eu_option(42, 40, 0.10, 0.5, 0.20, PUT), 0.81, 0.005);
    // S=K=100 r=5% sigma=20% T=1 (widely quoted: 10.4506 / 5.5735)
    check_close("atm 1y call", eu_option(100, 100, 0.05, 1.0, 0.20, CALL), 10.45058357218, 1e-8);
    check_close("atm 1y put",  eu_option(100, 100, 0.05, 1.0, 0.20, PUT),   5.57352602226, 1e-8);
}

// ------------------------------------------------- regression tests for the 3 original bugs
static void test_regressions() {
    // Bug 2: puts were priced as calls ('|| "Call"' is always true).
    const double c = eu_option(100, 100, 0.05, 1.0, 0.20, CALL);
    const double p = eu_option(100, 100, 0.05, 1.0, 0.20, PUT);
    check_true("put price differs from call price", std::fabs(c - p) > 1.0);

    // Bug 3: d1 used (r + 0.5*sigma^2*t) instead of (r + 0.5*sigma^2)*t - invisible at T=1.
    check_close("T=0.25 call", eu_option(100, 100, 0.05, 0.25, 0.20, CALL), 4.61499713, 1e-7);
    check_close("T=0.25 put",  eu_option(100, 100, 0.05, 0.25, 0.20, PUT),  3.372777179, 1e-7);
    check_close("2-day AAPL-like call", eu_option(230.76, 230, 0.05, 0.007937, 0.30, CALL), 2.904938818, 1e-7);
    check_close("2-day AAPL-like put",  eu_option(230.76, 230, 0.05, 0.007937, 0.30, PUT),  2.053681427, 1e-7);

    // Greeks at the same reference points (closed form, independent implementation)
    const Greeks g = bs_all(100, 100, 0.05, 0.25, 0.20, CALL);
    check_close("delta call T=.25", g.delta, 0.5694601832, 1e-9);
    check_close("gamma T=.25",      g.gamma, 0.03928800094, 1e-9);
    check_close("vega  T=.25",      g.vega,  19.64400047, 1e-7);
    check_close("theta call T=.25", g.theta, -10.47415125, 1e-7);
    check_close("rho   call T=.25", g.rho,   13.0827553, 1e-7);
    const Greeks gp = bs_all(100, 100, 0.05, 0.25, 0.20, PUT);
    check_close("delta put T=.25", gp.delta, -0.4305398168, 1e-9);
    check_close("theta put T=.25", gp.theta, -5.536262246, 1e-7);
    check_close("rho   put T=.25", gp.rho,   -11.60668971, 1e-7);
}

// ----------------------------------------------------------- structural properties
static void test_parity_and_dividends() {
    Rng rng(12345);
    for (int i = 0; i < 2000; ++i) {
        const double S = rng.in(20, 500), K = S * std::exp(rng.in(-0.6, 0.6));
        const double T = rng.in(0.003, 3.0), sigma = rng.in(0.05, 1.5);
        const double r = rng.in(-0.01, 0.08), q = rng.in(0.0, 0.05);
        const double c = eu_option(S, K, r, T, sigma, CALL, q);
        const double p = eu_option(S, K, r, T, sigma, PUT, q);
        // Put-call parity: C - P = S e^{-qT} - K e^{-rT}
        const double parity = S * std::exp(-q * T) - K * std::exp(-r * T);
        check_close("put-call parity", c - p, parity, 1e-9, 1e-9);
        // Dividend identity: BSM(S, q) == BS(S e^{-qT}, q = 0)
        check_close("dividend identity (call)", c, eu_option(S * std::exp(-q * T), K, r, T, sigma, CALL), 1e-9, 1e-9);
        // bounds
        check_true("call within no-arb bounds", c >= -1e-12 && c <= S * std::exp(-q * T) + 1e-9);
        check_true("put within no-arb bounds",  p >= -1e-12 && p <= K * std::exp(-r * T) + 1e-9);
    }
}

static void test_monotonic_in_sigma() {
    for (OptionType ty : {CALL, PUT}) {
        double prev = -1.0;
        for (double s = 0.05; s <= 2.0; s += 0.05) {
            const double v = eu_option(100, 105, 0.03, 0.5, s, ty, 0.01);
            check_true("price increasing in sigma", v > prev);
            prev = v;
        }
    }
}

// ----------------------------------- analytic Greeks vs central finite differences
static void test_greeks_vs_finite_differences() {
    const double Ss[] = {80, 100, 120};
    const double Ts[] = {0.05, 0.5, 2.0};
    const double sigmas[] = {0.10, 0.30, 0.80};
    const double rs[] = {0.01, 0.05};
    const double qs[] = {0.0, 0.02};
    for (OptionType ty : {CALL, PUT}) for (double S : Ss) for (double T : Ts)
    for (double sg : sigmas) for (double r : rs) for (double q : qs) {
        const double K = 100;
        const Greeks g = bs_all(S, K, r, T, sg, ty, q);
        auto V = [&](double s_, double r_, double t_, double sg_) { return eu_option(s_, K, r_, t_, sg_, ty, q); };

        const double hs = 1e-4 * S;   // small step: truncation error ~ hs^2 * V''' matters for sharp short-dated cases
        const double v0 = V(S, r, T, sg);
        const double fd_delta = (V(S + hs, r, T, sg) - V(S - hs, r, T, sg)) / (2 * hs);
        const double fd_gamma = (V(S + hs, r, T, sg) - 2 * v0 + V(S - hs, r, T, sg)) / (hs * hs);
        const double hv = 1e-5;
        const double fd_vega = (V(S, r, T, sg + hv) - V(S, r, T, sg - hv)) / (2 * hv);
        const double hr = 1e-6;
        const double fd_rho = (V(S, r + hr, T, sg) - V(S, r - hr, T, sg)) / (2 * hr);
        const double ht = 1e-5;
        const double fd_theta = -(V(S, r, T + ht, sg) - V(S, r, T - ht, sg)) / (2 * ht);   // theta = -dV/dT

        check_close("delta vs FD", g.delta, fd_delta, 1e-6, 1e-6);
        check_close("gamma vs FD", g.gamma, fd_gamma, 1e-6, 1e-5);
        check_close("vega  vs FD", g.vega,  fd_vega,  1e-5, 1e-6);
        check_close("rho   vs FD", g.rho,   fd_rho,   1e-5, 1e-6);
        check_close("theta vs FD", g.theta, fd_theta, 1e-5, 1e-6);
        check_close("bs_all price == eu_option", g.price, v0, 1e-12);
    }
}

// ------------------------------------------------------------ parsing & validation
static void test_parsing_and_validation() {
    check_true("parse 'call'", parse_option_type("call") == CALL);
    check_true("parse 'Call'", parse_option_type("Call") == CALL);
    check_true("parse 'PUT'",  parse_option_type("PUT") == PUT);
    check_true("parse '1'",    parse_option_type("1") == CALL);
    check_true("parse '0'",    parse_option_type("0") == PUT);
    bool threw = false;
    try { parse_option_type("straddle"); } catch (const std::invalid_argument&) { threw = true; }
    check_true("invalid option type throws", threw);

    auto throws = [](double S, double K, double t, double sg) {
        try { eu_option(S, K, 0.05, t, sg, CALL); } catch (const std::invalid_argument&) { return true; }
        return false;
    };
    check_true("S<=0 throws", throws(0, 100, 1, 0.2));
    check_true("K<=0 throws", throws(100, -1, 1, 0.2));
    check_true("t<=0 throws", throws(100, 100, 0, 0.2));
    check_true("sigma<=0 throws", throws(100, 100, 1, 0.0));
    check_true("NaN throws", throws(std::nan(""), 100, 1, 0.2));
}

// ------------------------------------------------------------------ implied vol
static void test_iv_roundtrip() {
    Rng rng(2024);
    int ok = 0, total = 0, other = 0;
    for (int i = 0; i < 5000; ++i) {
        const double S = rng.in(20, 500), K = S * std::exp(rng.in(-0.5, 0.5));
        const double T = rng.in(0.003, 3.0), sigma = rng.in(0.05, 1.5);
        const double r = rng.in(0.0, 0.08), q = rng.in(0.0, 0.04);
        const OptionType ty = rng.u() < 0.5 ? CALL : PUT;
        const double price = eu_option(S, K, r, T, sigma, ty, q);
        const IVResult res = implied_volatility_checked(S, K, r, T, ty, price, q);
        ++total;
        if (res.status == IVStatus::Ok) {
            ++ok;
            // the recovered vol must reproduce the price ...
            check_close("IV reprices", eu_option(S, K, r, T, res.iv, ty, q), price, 1e-9 * S);
            // ... and equal the true vol whenever the price is actually sensitive to it
            if (vega(S, K, r, T, sigma, ty, q) > 1e-2) check_close("IV equals true sigma", res.iv, sigma, 1e-6);
        } else if (res.status == IVStatus::NoTimeValue) {
            ++other;   // legitimately unidentifiable (price == intrinsic to numerical precision)
        } else {
            check_true("only NoTimeValue is an acceptable failure", false);
        }
    }
    check_true("at least 95% of round trips solved", ok >= 0.95 * total);
    std::printf("      iv round trip: %d/%d solved, %d unidentifiable (no time value)\n", ok, total, other);
}

static void test_iv_edge_cases() {
    const double nan = std::numeric_limits<double>::quiet_NaN();
    // The original main.cpp example: 2-day call, market price 2.20 -> sensible IV (~21%)
    const IVResult a = implied_volatility_checked(230.76, 230, 0.05, 0.007937, CALL, 2.20);
    check_true("main.cpp example solves", a.status == IVStatus::Ok);
    check_true("main.cpp example IV in (10%, 30%)", a.iv > 0.10 && a.iv < 0.30);
    check_close("main.cpp example reprices", eu_option(230.76, 230, 0.05, 0.007937, a.iv, CALL), 2.20, 1e-9);

    check_true("below intrinsic",    implied_volatility_checked(100, 50, 0.0, 1.0, CALL, 40.0).status == IVStatus::BelowIntrinsic);
    check_true("exactly intrinsic",  implied_volatility_checked(100, 50, 0.0, 1.0, CALL, 50.0).status == IVStatus::NoTimeValue);
    check_true("zero price",         implied_volatility_checked(100, 150, 0.0, 1.0, CALL, 0.0).status == IVStatus::NoTimeValue);
    check_true("above upper bound",  implied_volatility_checked(100, 50, 0.0, 1.0, CALL, 100.5).status == IVStatus::AboveUpperBound);
    check_true("put above K e^-rT",  implied_volatility_checked(100, 50, 0.0, 1.0, PUT, 51.0).status == IVStatus::AboveUpperBound);
    check_true("t = 0",              implied_volatility_checked(100, 100, 0.05, 0.0, CALL, 5.0).status == IVStatus::BadInput);
    check_true("NaN price",          implied_volatility_checked(100, 100, 0.05, 1.0, CALL, nan).status == IVStatus::BadInput);
    check_true("negative price",     implied_volatility_checked(100, 100, 0.05, 1.0, CALL, -1.0).status == IVStatus::BadInput);
    check_true("legacy wrapper NaN on failure", std::isnan(implied_volatility(100, 50, 0.0, 1.0, CALL, 40.0)));

    // Very high vol (500%) and very low vol (1%) both recovered
    for (double sg : {0.01, 5.0}) {
        const double px = eu_option(100, 100, 0.03, 1.0, sg, CALL);
        const IVResult r = implied_volatility_checked(100, 100, 0.03, 1.0, CALL, px);
        check_true("extreme vol solves", r.status == IVStatus::Ok);
        check_close("extreme vol value", r.iv, sg, 1e-6);
    }
}

static void test_vol_smile() {
    const double S = 100, r = 0.03, T = 0.25, q = 0.01;
    std::vector<double> strikes, prices, true_vols;
    for (double K = 80; K <= 120; K += 5) {
        const double m = std::log(K / S);
        const double sg = 0.25 - 0.30 * m + 0.60 * m * m;   // skew + curvature
        strikes.push_back(K); true_vols.push_back(sg);
        prices.push_back(eu_option(S, K, r, T, sg, CALL, q));
    }
    const std::vector<IVResult> smile = vol_smile(S, r, T, CALL, strikes, prices, q);
    check_true("smile size", smile.size() == strikes.size());
    for (std::size_t i = 0; i < smile.size(); ++i) {
        check_true("smile point solved", smile[i].status == IVStatus::Ok);
        check_close("smile point value", smile[i].iv, true_vols[i], 1e-7);
    }
    bool threw = false;
    try { vol_smile(S, r, T, CALL, strikes, std::vector<double>{1.0}); } catch (const std::invalid_argument&) { threw = true; }
    check_true("smile length mismatch throws", threw);
}

int main() {
    test_textbook_values();
    test_regressions();
    test_parity_and_dividends();
    test_monotonic_in_sigma();
    test_greeks_vs_finite_differences();
    test_parsing_and_validation();
    test_iv_roundtrip();
    test_iv_edge_cases();
    test_vol_smile();

    std::printf("%d checks, %d failures\n", g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}
