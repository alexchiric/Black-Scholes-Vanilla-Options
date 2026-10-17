# Build / test entry points.
#   make            build the batch engine  -> build/bs_engine
#   make test       C++ core tests + Python tests
#   make test-core  C++ core tests only
#   make demo       build and run the small main.cpp demo
#   make clean      remove build/
#
# Override the build directory or compiler if needed:  make BUILD=/tmp/bs CXX=g++

ifeq ($(origin CXX),default)
CXX := c++
endif
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -pedantic
BUILD ?= build
PYTHON ?= python3

HEADERS := cdf.h eu_option.h greeks.h vol_surface.h

.PHONY: all test test-core test-py demo clean

all: $(BUILD)/bs_engine

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/bs_engine: bs_engine.cpp $(HEADERS) | $(BUILD)
	$(CXX) $(CXXFLAGS) -o $@ bs_engine.cpp

$(BUILD)/test_core: tests/test_core.cpp $(HEADERS) | $(BUILD)
	$(CXX) $(CXXFLAGS) -o $@ tests/test_core.cpp

$(BUILD)/demo: main.cpp $(HEADERS) | $(BUILD)
	$(CXX) $(CXXFLAGS) -o $@ main.cpp

test-core: $(BUILD)/test_core
	$(BUILD)/test_core

test-py: $(BUILD)/bs_engine
	BS_ENGINE=$(abspath $(BUILD))/bs_engine $(PYTHON) -m unittest discover -s tests -v

test: test-core test-py

demo: $(BUILD)/demo
	$(BUILD)/demo

clean:
	rm -rf $(BUILD)
