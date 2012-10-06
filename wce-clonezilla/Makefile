#
# The clonezilla live original CD
#
CLONEZILLA_LIVE := clonezilla-live-20110113-maverick.iso

WCEVERSION := $(shell cat version)
ISOTARGET := wce-clonezilla-v${WCEVERSION}-lite.iso
#UDF_FLAGS := -udf -allow-limited-size -iso-level 3
UDF_FLAGS :=

default: fsimage $(ISOTARGET)

.phony: gpg-key

#DISKIMAGES := $(shell ls extract-cd/wce-disk-images/*.partclone.gz)
DISKIMAGES := 


LIVEPATCHES := \
 fsimage/wce.py \
 fsimage/image-disk.py \
 fsimage/iserver-install.py \
 fsimage/etc/ocs/ocs-live.conf \
 fsimage/etc/default/console-setup \
 fsimage/opt/drbl/sbin/ocs-live-wce \
 fsimage/opt/drbl/conf/drbl.conf \
 fsimage/etc/apt/sources.list \
 fsimage/etc/network/interfaces \
 fsimage/etc/resolv.conf 


SOURCES := \
 extract-cd/live/filesystem.squashfs \
 extract-cd/isolinux/isolinux.cfg \
 extract-cd/isolinux/wcebg1.png \
 extract-cd/isolinux/wcebg2.png \
 extract-cd/isolinux/wceboot.png \
 ${DISKIMAGES}

SQUASHFS_TOOLS := $(shell dpkg -l squashfs-tools 2>/dev/null)

$(CLONEZILLA_LIVE) :
	wget http://free.nchc.org.tw/clonezilla-live/alternative/oldstable/20110113-maverick/clonezilla-live-20110113-maverick.iso -O $@


extract-cd: $(CLONEZILLA_LIVE)
	-sudo mkdir clonezilla_live
	sudo mount -o loop ./$(CLONEZILLA_LIVE) clonezilla_live
	-mkdir ./extract-cd
	sudo cp -pR ./clonezilla_live/* ./extract-cd
	sudo umount clonezilla_live
	sudo rmdir clonezilla_live

fsimage: extract-cd add-packages.sh wce/sources.list
	-mkdir fsimage
	-mkdir fsimage-temp
	sudo mount -o loop extract-cd/live/filesystem.squashfs fsimage-temp
	sudo cp -pR fsimage-temp/* ./fsimage
	sudo umount fsimage-temp
	rmdir fsimage-temp
	sudo make fsimage/etc/apt/sources.list
	sudo make fsimage/etc/resolv.conf
	sudo ./add-packages.sh


fsimage/wce.py: wce/install-ubuntu.py
	sudo cp $< $@

fsimage/image-disk.py: wce/image-disk.py
	sudo cp $< $@

fsimage/iserver-install.py: wce/iserver-install.py
	sudo cp $< $@

fsimage/etc/ocs/ocs-live.conf: wce/ocs-live.conf
	sudo cp $< $@

fsimage/etc/default/console-setup: wce/console-setup
	sudo cp $< $@

fsimage/opt/drbl/sbin/ocs-live-wce: wce/ocs-live-wce
	sudo install -m 755 $< $@

fsimage/opt/drbl/conf/drbl.conf: wce/drbl.conf
	sudo cp $< $@

fsimage/etc/apt/sources.list: wce/sources.list
	sudo cp $< $@

fsimage/etc/network/interfaces: wce/interfaces
	sudo cp $< $@

fsimage/etc/resolv.conf: /etc/resolv.conf
	sudo cp -p $< $@

extract-cd/isolinux/%.png: wce/%.png
	sudo cp $< $@

extract-cd/isolinux/isolinux.cfg: wce/isolinux.cfg.template version
	sed s/###VERSION###/${WCEVERSION}/g $< > wce/isolinux.cfg
	sudo cp wce/isolinux.cfg $@
	rm -f wce/isolinux.cfg

extract-cd/live/filesystem.squashfs: $(LIVEPATCHES)
	if ! dpkg-query -s squashfs-tools > /dev/null 2>&1 ; then sudo apt-get -y install squashfs-tools ; fi
	sudo chmod +w extract-cd/live/filesystem.packages
	sudo chroot fsimage dpkg-query -W --showformat='$${Package} $${Version}\n' > wce/filesystem.packages
	sudo cp wce/filesystem.packages extract-cd/live/filesystem.packages
	sudo rm -f extract-cd/live/filesystem.squashfs
	sudo mksquashfs fsimage extract-cd/live/filesystem.squashfs -noappend -always-use-fragments -b 256K
	sudo chown $(USER):$(USER) extract-cd/live/filesystem.squashfs
	sudo chmod 755 extract-cd/live/filesystem.squashfs
	printf $$(sudo du -sx --block-size=1 fsimage | cut -f1) > wce/filesystem.size
	sudo cp wce/filesystem.size extract-cd/live/filesystem.size


$(ISOTARGET): $(SOURCES) version Makefile
	if ! dpkg-query -l genisoimage > /dev/null 2>&1 ; then sudo apt-get -y install genisoimage ; fi
	cd extract-cd;sudo genisoimage $(UDF_FLAGS) -f -r -J -l -V "$$IMAGE_NAME" -cache-inodes -b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot -boot-load-size 4 -boot-info-table -publisher worldcomputerexchange.org -p ntai@smartfruit.com -input-charset utf-8 -output-charset utf-8 -V "wce_triage_$(WCEVERSION)" -o ../$(ISOTARGET) .


gpg-key:
	wget -q http://drbl.org/GPG-KEY-DRBL -O- | sudo apt-key add -
	wget -q http://drbl.sourceforge.net/GPG-KEY-DRBL -O- | sudo apt-key add -

/usr/lib/syslinux:
	sudo apt-get -y install syslinux syslinux-common

/usr/lib/syslinux/pxelinux.0: /usr/lib/syslinux

/var/lib/tftpboot/wce/live/% : extract-cd/live/%
	[ -d /var/lib/tftpboot/wce/live/ ] || sudo mkdir -p /var/lib/tftpboot/wce/live
	sudo cp -p $< $@

/var/lib/tftpboot/wce/boot/% : tftpboot/wce/boot/%
	[ -d /var/lib/tftpboot/wce/boot/ ] || sudo mkdir -p /var/lib/tftpboot/wce/boot
	sudo cp -p $< $@

/var/lib/tftpboot:
	sudo mkdir -p /var/lib/tftpboot

/var/lib/tftpboot/pxelinux.cfg:
	sudo mkdir -p /var/lib/tftpboot/pxelinux.cfg

tftpboot/pxelinux.0: /usr/lib/syslinux/pxelinux.0
	[ -d tftpboot ] || mkdir tftpboot
	cp -p /usr/lib/syslinux/pxelinux.0 $@

/var/lib/tftpboot/pxelinux.0: tftpboot/pxelinux.0
	sudo install -D $< $@

/var/lib/tftpboot/pxelinux.cfg/default: tftpboot/pxelinux.cfg/default
	sudo install -D $< $@

/usr/lib/syslinux/%.c32: /usr/lib/syslinux

/var/lib/tftpboot/%.c32: /usr/lib/syslinux/%.c32
	sudo install -D $< $@

tftp: \
/var/lib/tftpboot/pxelinux.0 \
/var/lib/tftpboot/pxelinux.cfg/default \
/var/lib/tftpboot/menu.c32 \
/var/lib/tftpboot/chain.c32 \
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

.phony: clean

clean:
	sudo rm -fR extract-cd fsimage fsimage-temp clonezilla_live
	rm -f wce/filesystem.packages wce/filesystem.size
	rm -f squashfs-installed genisoimage-installed


.phony: prerequisits debian

prerequisits:
	if ! dpkg-query -s squashfs-tools > /dev/null 2>&1 ; then sudo apt-get -y install squashfs-tools ; fi
	if ! dpkg-query -s wireless-tools > /dev/null 2>&1 ; then sudo apt-get -y install wireless-tools ; fi
	if ! dpkg-query -s python-dialog > /dev/null 2>&1 ; then sudo apt-get -y install python-dialog ; fi
	if ! dpkg-query -s xz-utils > /dev/null 2>&1 ; then sudo apt-get -y install xz-utils ; fi
	if ! dpkg-query -s smartmontools > /dev/null 2>&1 ; then sudo apt-get -y install smartmontools ; fi
	if ! dpkg-query -s wipe > /dev/null 2>&1 ; then sudo apt-get -y install wipe ; fi
	if ! dpkg-query -s pigz > /dev/null 2>&1 ; then sudo apt-get -y install pigz ; fi
	if ! dpkg-query -s lzop > /dev/null 2>&1 ; then sudo apt-get -y install lzop ; fi
	if ! dpkg-query -s kbd > /dev/null 2>&1 ; then sudo apt-get -y install kbd ; fi
	if ! dpkg-query -s parted > /dev/null 2>&1 ; then sudo apt-get -y install parted ; fi
	if ! dpkg-query -l genisoimage > /dev/null 2>&1 ; then sudo apt-get -y install genisoimage ; fi
	if ! dpkg-query -s squashfs-tools > /dev/null 2>&1 ; then sudo apt-get -y install squashfs-tools ; fi
	if ! dpkg-query -s partclone > /dev/null 2>&1 ; then sudo apt-get -y install partclone ; fi

debian:
	wget -q http://drbl.org/GPG-KEY-DRBL -O- | sudo apt-key add -
	echo "deb http://drbl.sourceforge.net/drbl-core drbl stable" > /tmp/drbl.list
	sudo cp /tmp/drbl.list /etc/apt/sources.list.d/drbl.list
	sudo apt-get update
