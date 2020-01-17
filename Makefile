
# Variables
BUILD_DIR     = $(shell pwd)/__build__
DIST_DIR      = $(BUILD_DIR)/dist

# Development pkg requirements
DEPENDENCIES  = pytest wheel PyYAML pip-tools requests gitpython docker

.PHONY: help install clean develop undevelop

help:
	@echo "Please use 'make <target>' where <target> is one of"
	@echo ""
	@echo " help                 display this help"
	@echo " install              install package"
	@echo " package              build package"
	@echo " clean                clean stuff"
	@echo " develop              install package in development mode"
	@echo " undevelop            unset the above development mode"
	@echo ""

install:
	@echo "--------------------------------------------------------------------"
	@echo "Installing package"
	@python setup.py install
	@echo ""
	@echo "Done."
	@echo ""

package:
	@echo "--------------------------------------------------------------------"
	@echo "Building package"
	@mkdir -p $(DIST_DIR)/
	@python setup.py bdist_wheel --dist-dir=$(DIST_DIR)
	@echo ""
	@echo "Done."
	@echo ""

clean:
	@echo ""
	@echo "--------------------------------------------------------------------"
	@python setup.py clean
	@echo "Removing *.pyc and __pycache__/ files"
	@find . -type f -name "*.pyc" | xargs rm -vrf
	@find . -type d -name "__pycache__" | xargs rm -vrf
	@echo ""
	@echo "Done."
	@echo ""

develop:
	@echo "--------------------------------------------------------------------"
	@echo "Installing development dependencies"
	@pip install $(DEPENDENCIES)
	@echo ""
	@echo "--------------------------------------------------------------------"
	@echo "Setting up development environment"
	@python setup.py develop --no-deps -q
	@echo ""
	@echo "Done."
	@echo ""

undevelop:
	@echo ""
	@echo "--------------------------------------------------------------------"
	@echo "Removing development environment"
	@python setup.py develop -q --no-deps --uninstall
	@echo ""
	@echo "Done."
	@echo ""
