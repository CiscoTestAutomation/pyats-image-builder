
# Variables
PKG_NAME      = pyats-image-builder
BUILD_DIR     = $(shell pwd)/__build__
DIST_DIR      = $(BUILD_DIR)/dist

# Development pkg requirements
DEPENDENCIES  = pytest wheel PyYAML pip-tools requests gitpython docker
DEPENDENCIES += jsonschema jinja2

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
	@echo "Installing dependencies"
	@pip install $(DEPENDENCIES)
	@echo "Installing package"
	@python3 setup.py install
	@echo ""
	@echo "Done."
	@echo ""

package:
	@echo "--------------------------------------------------------------------"
	@echo "Building package"
	@mkdir -p $(DIST_DIR)/
	@python3 setup.py bdist_wheel --dist-dir=$(DIST_DIR)
	@echo ""
	@echo "Done."
	@echo ""

clean:
	@echo ""
	@echo "--------------------------------------------------------------------"
	@python3 setup.py clean
	@echo "Removing *.pyc and __pycache__/ files"
	@find . -type f -name "*.pyc" | xargs rm -vrf
	@find . -type d -name "__pycache__" | xargs rm -vrf
	@echo ""
	@echo "Done."
	@echo ""

develop:
	@echo "--------------------------------------------------------------------"
	@echo "Uninstalling package"
	@pip uninstall -y pyats-image-builder
	@echo "Installing development dependencies"
	@pip install $(DEPENDENCIES)
	@echo ""
	@echo "--------------------------------------------------------------------"
	@echo "Setting up development environment"
	@python3 setup.py develop --no-deps -q
	@echo ""
	@echo "Done."
	@echo ""

undevelop:
	@echo ""
	@echo "--------------------------------------------------------------------"
	@echo "Removing development environment"
	@python3 setup.py develop -q --no-deps --uninstall
	@echo ""
	@echo "Done."
	@echo ""

image:
	@echo ""
	@echo "--------------------------------------------------------------------"
	@echo "Make image"
	@docker build --build-arg --no-cache -t image-builder:latest .
	@echo ""
	@echo "Done."
	@echo ""

distribute:
	@echo ""
	@echo "--------------------------------------------------------------------"
	@echo "Copying all distributable to $(PROD_PKGS)"
	@test -d $(DIST_DIR) || { echo "Nothing to distribute! Exiting..."; exit 1; }
	@ssh -q $(PROD_USER) 'test -e $(PROD_PKGS)/$(PKG_NAME) || mkdir $(PROD_PKGS)/$(PKG_NAME)'
	@scp $(DIST_DIR)/* $(PROD_USER):$(PROD_PKGS)/$(PKG_NAME)/
	@echo ""
	@echo "Done."
	@echo ""

distribute_staging:
	@echo ""
	@echo "--------------------------------------------------------------------"
	@echo "Copying all distributable to $(STAGING_PKGS)"
	@test -d $(DIST_DIR) || { echo "Nothing to distribute! Exiting..."; exit 1; }
	@ssh -q $(PROD_USER) 'test -e $(STAGING_PKGS)/$(PKG_NAME) || mkdir $(STAGING_PKGS)/$(PKG_NAME)'
	@scp $(DIST_DIR)/* $(PROD_USER):$(STAGING_PKGS)/$(PKG_NAME)/
	@echo ""
	@echo "Done."
	@echo ""

distribute_staging_external:
	@echo ""
	@echo "--------------------------------------------------------------------"
	@echo "Copying all distributable to $(STAGING_EXT_PKGS)"
	@test -d $(DIST_DIR) || { echo "Nothing to distribute! Exiting..."; exit 1; }
	@ssh -q $(PROD_USER) 'test -e $(STAGING_EXT_PKGS)/$(PKG_NAME) || mkdir $(STAGING_EXT_PKGS)/$(PKG_NAME)'
	@scp $(DIST_DIR)/* $(PROD_USER):$(STAGING_EXT_PKGS)/$(PKG_NAME)/
	@echo ""
	@echo "Done."
	@echo ""
