PREFIX ?= /usr
LIBDIR = $(PREFIX)/lib
BINDIR = $(PREFIX)/bin
LIBEXECDIR = $(PREFIX)/libexec
DATADIR = $(PREFIX)/share
SYSTEMDUSERDIR = $(LIBDIR)/systemd/user
SYSTEMDSYSTEMDIR = $(LIBDIR)/systemd/system

INSTALL_DIR = $(LIBDIR)/external-displays
DESKTOP_DIR = $(DATADIR)/applications
ICON_DIR = $(DATADIR)/icons/hicolor/64x64/apps
POLKIT_DIR = $(DATADIR)/polkit-1/rules.d

.PHONY: all install uninstall

all:
	@echo "Run 'make install' to install the files."

install:
	install -d $(DESTDIR)$(INSTALL_DIR)
	install -d $(DESTDIR)$(BINDIR)
	install -d $(DESTDIR)$(LIBEXECDIR)
	install -d $(DESTDIR)$(DESKTOP_DIR)
	install -d $(DESTDIR)$(ICON_DIR)
	install -d $(DESTDIR)$(SYSTEMDUSERDIR)
	install -d $(DESTDIR)$(SYSTEMDSYSTEMDIR)
	install -d $(DESTDIR)$(POLKIT_DIR)
	install -d $(DESTDIR)$(DATADIR)/external-displays

	cp -r external_displays $(DESTDIR)$(INSTALL_DIR)/

	install -m 755 main.py $(DESTDIR)$(INSTALL_DIR)/

	install -m 755 data/start-externaldisplay $(DESTDIR)$(LIBEXECDIR)
	install -m 644 data/xorg.card1.conf $(DESTDIR)$(DATADIR)/external-displays
	install -m 644 data/external-display-display-server.service $(DESTDIR)$(SYSTEMDSYSTEMDIR)
	install -m 644 data/externaldisplay.service $(DESTDIR)$(SYSTEMDUSERDIR)
	install -m 644 data/50-external-displays.rules $(DESTDIR)$(POLKIT_DIR)

	install -m 644 data/io.furios.ExternalDisplays.desktop $(DESTDIR)$(DESKTOP_DIR)/
	install -m 644 data/io.furios.ExternalDisplays.png $(DESTDIR)$(ICON_DIR)/

	ln -sf ../lib/external-displays/main.py $(DESTDIR)$(BINDIR)/io.furios.ExternalDisplays

uninstall:
	rm -rf $(DESTDIR)$(INSTALL_DIR)

	rm -f $(DESTDIR)$(LIBEXECDIR)/start-externaldisplay
	rm -rf $(DESTDIR)$(DATADIR)/external-displays
	rm -f $(DESTDIR)$(SYSTEMDSYSTEMDIR)/external-display-display-server.service
	rm -f $(DESTDIR)$(SYSTEMDUSERDIR)/externaldisplay.service
	rm -f $(DESTDIR)$(POLKIT_DIR)/50-external-displays.rules

	rm -f $(DESTDIR)$(DESKTOP_DIR)/io.furios.ExternalDisplays.desktop
	rm -f $(DESTDIR)$(ICON_DIR)/io.furios.ExternalDisplays.png

	rm -f $(DESTDIR)$(BINDIR)/io.furios.ExternalDisplays
