#ifndef EU_OPTION_H
#define EU_OPTION_H

#include <cmath>
#include <string>
#include <stdexcept>

#include "cdf.h"

using std::string;

double eu_option(double S, double K, double r, double t, double sigma, string option_type){
    //Calculate d1 and d2
    double d1 = (log(S/K) + (r + 0.5 * pow(sigma, 2) * t)) / (sigma * sqrt(t));
    double d2 = d1 - sigma * sqrt(t);

    //Initialise Option Price
    double option_price = 0.0;

    //Calculate price based on option type
    if (option_type == "call" || "Call") {
            option_price = S * cdf(d1) - K * exp(-r * t) * cdf(d2);
        }
        else if (option_type == "put" || "Put") {
            option_price = K * exp(-r * t) * cdf(-d2) - S * cdf(-d1);
        }
        else {
            throw std::invalid_argument("Invalid option type. Please enter 'call' or 'put'.");
        }

    return option_price;

}

#endif