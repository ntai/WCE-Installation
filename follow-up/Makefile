#
# WCE follow up 
#

TARGETS := \
 /var/www/wce-follow-up.tar \
 /var/www/post-installation.sh

default: install

install: ${TARGETS}

FILES := \
 fsimage/usr/local/bin/access-world-computer-exchange \
 fsimage/usr/local/bin/wce-follow-up \
 fsimage/etc/rc.local \
 fsimage/var/lib/world-computer-exchange/access-url


/var/www/wce-follow-up.tar: wce-follow-up.tar
	sudo install -D $< $@

wce-follow-up.tar: ${FILES}
	cd fsimage ; tar cf ../$@ *

fsimage/usr/local/bin/access-world-computer-exchange: bin/access-world-computer-exchange
	sudo install -D $< $@

fsimage/usr/local/bin/wce-follow-up: bin/wce-follow-up
	sudo install -D $< $@

fsimage/etc/rc.local: etc/rc.local
	sudo install -D $< $@

fsimage/var/lib/world-computer-exchange/access-url: lib/access-url
	sudo install -D $< $@

/var/www/post-installation.sh: bin/post-installation.sh
	sudo install $< $@
