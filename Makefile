VERSION = $(shell ./maildirproc --version)

all: maildirproc-$(VERSION).tar.bz2

DIST_FILES = \
    LICENSE \
    MANIFEST.in \
    NEWS \
    README \
    doc

define build_dist_archive
	rm -rf build/
	./setup.py sdist
endef

maildirproc-$(VERSION).tar.bz2: $(DIST_FILES) maildirproc setup.py
	$(call build_dist_archive,maildirproc,setup.py)

setup.py: setup.py.template
	sed -e 's/%PY_BIN%/python3/g' \
	    -e 's/%PY_VER%/3.x/g' \
	    -e 's/%CLASSIFIERS%/\
    "Programming Language :: Python :: 3",\
    "Programming Language :: Python :: 3.0",\
    "Programming Language :: Python :: 3.1",\
    "Programming Language :: Python :: 3.2",\
    "Programming Language :: Python :: 3.3",\
    "Programming Language :: Python :: 3.4",/' \
	    -e 's/%MDP_NAME%/maildirproc/g' \
	    -e 's/%MDP_VER%/$(VERSION)/g' \
	    $< >$@
	chmod +x $@

upload: all
	twine upload build/maildirproc-$(VERSION)-sdist/dist/maildirproc-$(VERSION).tar.bz2

clean:
	rm -rf maildirproc*-$(VERSION) build dist MANIFEST
	rm -rf *.gz setup.py
	find -name '*~' | xargs rm -f

.PHONY: all clean
