#ifndef GREEKS_H
#define GREEKS_H

#include <cmath>
#include <string>
#include "eu_option.h"

//Used finite difference method in order to apply the same solution for both calls and puts

double delta(double S, double K, double r, double t, double sigma, string option_type){
    const double EPSILON_S = 1e-4;
    double price_up = eu_option(S + EPSILON_S, K, r, t, sigma, option_type);
    double price = eu_option(S , K, r, t, sigma, option_type);
    return (price_up - price)/EPSILON_S;

}

double gamma(double S, double K, double r, double t, double sigma, string option_type){
    const double EPSILON_S = 1e-4;
    double price_up = eu_option(S + EPSILON_S, K, r, t, sigma, option_type);
    double price_down = eu_option(S - EPSILON_S, K, r, t, sigma, option_type);
    double price = eu_option(S , K, r, t, sigma, option_type);
    return (price_up - 2 * price + price_down) / (EPSILON_S * EPSILON_S);
}

double rho(double S, double K, double r, double t, double sigma, string option_type){
    const double EPSILON_R = 1e-4;
    double price_up = eu_option(S, K, r + EPSILON_R, t, sigma, option_type);
    double price = eu_option(S , K, r, t, sigma, option_type);
    return (price_up - price)/EPSILON_R;
}

double vega(double S, double K, double r, double t, double sigma, string option_type){
    const double EPSILON_V = 1e-4;
    double price_up = eu_option(S, K, r, t, sigma + EPSILON_V, option_type);
    double price = eu_option(S , K, r, t, sigma, option_type);
    return (price_up - price)/EPSILON_V;
}

double theta(double S, double K, double r, double t, double sigma, string option_type){
    const double EPSILON_T = 1.0/365;
    double price_up = eu_option(S, K, r, t - EPSILON_T, sigma, option_type);
    double price = eu_option(S , K, r, t, sigma, option_type);
    return (price_up - price)/EPSILON_T;
}

#endif