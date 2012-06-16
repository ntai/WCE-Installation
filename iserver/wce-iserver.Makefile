#

TFTPBOOT_TARGETS := \
/var/lib/tftpboot/pxelinux.0 \
/var/lib/tftpboot/pxelinux.cfg/default \
/var/lib/tftpboot/menu.c32 \
/var/lib/tftpboot/vesamenu.c32 \
/var/lib/tftpboot/wce/boot/menu.cfg \
/var/lib/tftpboot/wce/boot/wceboot.png \
/var/lib/tftpboot/wce/live/filesystem.size \
/var/lib/tftpboot/wce/live/filesystem.squashfs \
/var/lib/tftpboot/wce/live/freedos.img \
/var/lib/tftpboot/wce/live/gpxe.lkn \
/var/lib/tftpboot/wce/live/initrd.img \
/var/lib/tftpboot/wce/live/memtest \
/var/lib/tftpboot/wce/live/vmlinuz

TARGETS := \
/usr/local/bin/update-wce-iserver \
/etc/cron.d/cron-update-wce-iserver

default: $(TARGETS) /var/lib/tftpboot.tgz

/var/lib/tftpboot.tgz: tftpboot.tgz
	(cd /var/lib/tftpboot/ ; tar xmzf /var/www/tftpboot.tgz)
	install -m 0444 -o root -g root $< $@

/usr/local/bin/update-wce-iserver: update-wce-iserver
	install -m 0555 -o root -g root $< $@

/etc/cron.d/cron-update-wce-iserver: cron-update-wce-iserver
	install -m 0555 -o root -g root $< $@
