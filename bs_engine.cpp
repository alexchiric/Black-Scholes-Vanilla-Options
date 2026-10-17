// bs_engine - batch Black-Scholes-Merton engine.
//
// Reads a CSV table on stdin, writes a CSV table (one output row per input row, same
// order) on stdout. This replaces the old temp.bin hand-off: no shared files, no
// per-call recompilation, and the columns are looked up by *name*, so their order does
// not matter.
//
// Input columns (case-insensitive header):
//   required : type, S, K, T, r        type = call|put|c|p|1|0, T in years
//   optional : q      continuous dividend yield (default 0)
//              sigma  volatility -> price and Greeks are computed at this vol
//              price  market price -> implied volatility is solved from it
//
// If `sigma` is empty for a row but `price` is present, price and Greeks are computed
// at the implied volatility.
//
// Output columns:
//   row_status   ok | bad_input
//   iv           implied vol (NaN if not requested / not solvable)
//   iv_status    ok | no_price | below_intrinsic | above_upper_bound | no_time_value |
//                vol_too_high | no_convergence | bad_input
//   sigma_used   the volatility used for the model price / Greeks
//   price_model  Black-Scholes-Merton price at sigma_used
//   delta, gamma, vega, theta, rho   raw analytic Greeks (units documented in greeks.h)
//   iterations   solver iterations used for the implied vol
//
// Missing values are written as "nan".

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <map>
#include <string>
#include <vector>

#include "eu_option.h"
#include "greeks.h"
#include "vol_surface.h"

namespace {

const double NaN = std::numeric_limits<double>::quiet_NaN();

std::string trim(const std::string& s) {
    std::size_t a = 0, b = s.size();
    while (a < b && std::isspace(static_cast<unsigned char>(s[a]))) ++a;
    while (b > a && std::isspace(static_cast<unsigned char>(s[b - 1]))) --b;
    return s.substr(a, b - a);
}

std::string lower(std::string s) {
    for (char& c : s) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
}

std::vector<std::string> split_csv(const std::string& line) {
    std::vector<std::string> out;
    std::string cur;
    for (char c : line) {
        if (c == ',') { out.push_back(trim(cur)); cur.clear(); }
        else if (c != '\r') cur += c;
    }
    out.push_back(trim(cur));
    return out;
}

// Empty / "nan" / "none" / "null" / "na" / non-numeric -> NaN.
double to_double(const std::string& s) {
    if (s.empty()) return NaN;
    const std::string l = lower(s);
    if (l == "nan" || l == "none" || l == "null" || l == "na" || l == "n/a") return NaN;
    char* end = nullptr;
    const double v = std::strtod(s.c_str(), &end);
    if (end == s.c_str() || *end != '\0') return NaN;
    return v;
}

std::string fmt(double v) {
    if (std::isnan(v)) return "nan";
    char buf[64];
    std::snprintf(buf, sizeof buf, "%.15g", v);
    return buf;
}

struct Columns {
    int type = -1, S = -1, K = -1, T = -1, r = -1, q = -1, sigma = -1, price = -1;
};

std::string field(const std::vector<std::string>& row, int idx) {
    return (idx >= 0 && idx < static_cast<int>(row.size())) ? row[idx] : std::string();
}

}  // namespace

int main(int argc, char** argv) {
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        if (a == "--help" || a == "-h") {
            std::fputs("bs_engine: reads CSV (type,S,K,T,r[,q,sigma,price]) on stdin, writes CSV on stdout.\n"
                       "See the header comment of bs_engine.cpp for the full column reference.\n", stdout);
            return 0;
        }
        if (a == "--version") { std::puts("bs_engine 1.0"); return 0; }
    }

    std::ios::sync_with_stdio(false);
    std::string line;
    if (!std::getline(std::cin, line)) {
        std::fputs("bs_engine: empty input (expected a CSV header line)\n", stderr);
        return 2;
    }

    Columns col;
    const std::vector<std::string> header = split_csv(line);
    for (std::size_t i = 0; i < header.size(); ++i) {
        const std::string h = lower(header[i]);
        const int idx = static_cast<int>(i);
        if (h == "type") col.type = idx;
        else if (h == "s") col.S = idx;
        else if (h == "k") col.K = idx;
        else if (h == "t") col.T = idx;
        else if (h == "r") col.r = idx;
        else if (h == "q") col.q = idx;
        else if (h == "sigma") col.sigma = idx;
        else if (h == "price") col.price = idx;
    }
    if (col.type < 0 || col.S < 0 || col.K < 0 || col.T < 0 || col.r < 0) {
        std::fputs("bs_engine: header must contain the columns type,S,K,T,r\n", stderr);
        return 2;
    }

    std::puts("row_status,iv,iv_status,sigma_used,price_model,delta,gamma,vega,theta,rho,iterations");

    while (std::getline(std::cin, line)) {
        if (trim(line).empty()) continue;
        const std::vector<std::string> row = split_csv(line);

        std::string row_status = "ok";
        std::string iv_status = "no_price";
        double iv = NaN, sigma_used = NaN, iterations = NaN;
        Greeks g{NaN, NaN, NaN, NaN, NaN, NaN};

        try {
            const OptionType type = parse_option_type(field(row, col.type));
            const double S = to_double(field(row, col.S));
            const double K = to_double(field(row, col.K));
            const double T = to_double(field(row, col.T));
            const double r = to_double(field(row, col.r));
            double q = to_double(field(row, col.q));
            if (std::isnan(q)) q = 0.0;
            const double sigma = to_double(field(row, col.sigma));
            const double price = to_double(field(row, col.price));

            if (!std::isfinite(S) || !std::isfinite(K) || !std::isfinite(T) || !std::isfinite(r)) {
                throw std::invalid_argument("S, K, T and r must be finite numbers");
            }

            if (std::isfinite(price)) {
                const IVResult res = implied_volatility_checked(S, K, r, T, type, price, q);
                iv = res.iv;
                iv_status = iv_status_str(res.status);
                iterations = res.iterations;
            }

            if (std::isfinite(sigma)) sigma_used = sigma;
            else if (iv_status == "ok") sigma_used = iv;

            if (std::isfinite(sigma_used)) g = bs_all(S, K, r, T, sigma_used, type, q);   // throws on invalid inputs
        } catch (const std::invalid_argument&) {
            row_status = "bad_input";
            if (iv_status == "no_price") iv_status = "bad_input";
        }

        std::printf("%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n", row_status.c_str(), fmt(iv).c_str(), iv_status.c_str(),
                    fmt(sigma_used).c_str(), fmt(g.price).c_str(), fmt(g.delta).c_str(), fmt(g.gamma).c_str(),
                    fmt(g.vega).c_str(), fmt(g.theta).c_str(), fmt(g.rho).c_str(), fmt(iterations).c_str());
    }
    return 0;
}
