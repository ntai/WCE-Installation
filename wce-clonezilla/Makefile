#
# The clonezilla live original CD
#
#CLONEZILLA_LIVE := clonezilla-live-20110113-maverick.iso
#CLONEZILLA_LIVE := clonezilla-live-20120620-precise.iso
#CLONEZILLA_LIVE := clonezilla-live-20130429-raring-i386.iso
CLONEZILLA_LIVE := clonezilla-live-20140915-trusty-i386.iso

DIALOG := dialog_1.2-20130928-1_i386.deb
PYTHON_DIALOG := python-dialog_2.7-1_all.deb
PYTHON_SUPPORT := python-support_1.0.15_all.deb

WCEVERSION := $(shell cat version)
ISOTARGET := wce-clonezilla-v${WCEVERSION}-lite.iso
#UDF_FLAGS := -udf -allow-limited-size -iso-level 3
UDF_FLAGS :=

default: live-image $(ISOTARGET)

.phony: gpg-key

#DISKIMAGES := $(shell ls iso-extract/wce-disk-images/*.partclone.gz)
DISKIMAGES := 


LIVEPATCHES := \
 live-image/wce.py \
 live-image/image-disk.py \
 live-image/iserver-install.py \
 live-image/etc/default/console-setup \
 live-image/etc/ocs/ocs-live.conf \
 live-image/usr/sbin/ocs-live-wce \
 live-image/etc/inetd.conf \
 live-image/etc/init/failsafe.conf \
 live-image/usr/share/drbl/sbin/ocs-functions
# live-image/etc/sudoers.d/live \
# live-image/etc/passwd \
# live-image/etc/shadow \
# live-image/etc/group \
# live-image/etc/gshadow \
# live-image/home/user
# live-image/etc/sudoers \
# live-image/opt/drbl/conf/drbl.conf
# live-image/etc/network/interfaces \
# live-image/etc/resolv.conf


SOURCES := \
 iso-extract/live/filesystem.squashfs \
 iso-extract/syslinux/isolinux.cfg \
 iso-extract/syslinux/wcebg1.png \
 iso-extract/syslinux/wcebg2.png \
 iso-extract/syslinux/wceboot.png \
 iso-extract/wce \
 iso-extract/wce/live-triage \
 iso-extract/wce/install-ubuntu.py \
 iso-extract/wce/initrd.img.md5 \
 iso-extract/wce/vmlinuz.md5 \
 iso-extract/wce/${PYTHON_DIALOG} \
 iso-extract/wce/${PYTHON_SUPPORT} \
 iso-extract/wce/${DIALOG}
 ${DISKIMAGES}

SQUASHFS_TOOLS := $(shell dpkg -l squashfs-tools 2>/dev/null)

$(CLONEZILLA_LIVE) :
	wget http://files.smartfruit.com/wce/$(CLONEZILLA_LIVE) -O $@

$(PYTHON_DIALOG) :
	wget http://ubuntu.media.mit.edu/ubuntu/pool/main/p/pythondialog/$@ -O $@

$(PYTHON_SUPPORT):
	wget http://ubuntu.media.mit.edu/ubuntu/pool/main/p/python-support/$@ -O $@

$(DIALOG):
	wget http://ubuntu.media.mit.edu/ubuntu/pool/main/d/dialog/$@ -O $@


iso-extract: $(CLONEZILLA_LIVE)
	-sudo mkdir clonezilla_live
	sudo mount -o loop ./$(CLONEZILLA_LIVE) clonezilla_live
	-mkdir ./iso-extract
	sudo cp -pR ./clonezilla_live/* ./iso-extract
	sudo umount clonezilla_live
	sudo rmdir clonezilla_live

filesystem.squashfs: iso-extract
	cp iso-extract/live/filesystem.squashfs filesystem.squashfs
	chmod 444 filesystem.squashfs

live-image-original: filesystem.squashfs add-packages.sh 
	-mkdir live-image-original
	-mkdir live-image-temp
	sudo mount -o loop filesystem.squashfs live-image-temp
	sudo cp -pR live-image-temp/* ./live-image-original
	sudo umount live-image-temp
	rmdir live-image-temp
	#
	sudo make live-image-original/etc/resolv.conf
	sudo ./add-packages.sh
	sudo rm -f live-image-original/etc/resolv.conf


live-image: live-image-original ./slim-live-image.sh
	-mkdir live-image
	sudo cp -pR live-image-original/* ./live-image
	sudo python ./slim-live-image.py

live-image/usr/share/drbl/setup/files/gparted/usr/share/gparted/bin/gl-functions: wce/gl-functions
	sudo cp $< $@

live-image/home/user: 
	sudo mkdir live-image/home/user
	sudo chown 1000:1000 live-image/home/user

live-image/wce.py: wce/install-ubuntu.py
	sudo cp $< $@

live-image/image-disk.py: wce/image-disk.py
	sudo cp $< $@

live-image/iserver-install.py: wce/iserver-install.py
	sudo cp $< $@

live-image/etc/ocs/ocs-live.conf: wce/ocs-live.conf
	sudo cp $< $@

live-image/etc/sudoers: wce/sudoers
	sudo install -m 440 $< $@

live-image/etc/sudoers.d/live: wce/sudoers.d/live
	sudo install -m 440 $< $@

live-image/etc/passwd: wce/passwd
	sudo install -m 644 $< $@

live-image/etc/group: wce/group
	sudo install -m 644 $< $@

live-image/etc/shadow: wce/shadow
	sudo install -m 640 $< $@

live-image/etc/gshadow: wce/gshadow
	sudo install -m 640 $< $@

live-image/etc/default/console-setup: wce/console-setup
	sudo cp $< $@

live-image/etc/inetd.conf: wce/inetd.conf
	sudo cp $< $@

live-image/opt/drbl/sbin/ocs-live-wce: wce/ocs-live-wce
	sudo install -m 755 $< $@

live-image/usr/sbin/ocs-live-wce: wce/ocs-live-wce
	sudo install -m 755 $< $@

live-image/opt/drbl/conf/drbl.conf: wce/drbl.conf
	sudo cp $< $@

live-image/usr/share/drbl/sbin/ocs-functions: wce/ocs-functions
	sudo install -m 755 $< $@

#live-image/etc/apt/sources.list: wce/sources.list
#	sudo cp $< $@

live-image/etc/network/interfaces: wce/interfaces
	sudo cp $< $@

live-image-original/etc/resolv.conf: /etc/resolv.conf
	sudo cp -p $< $@


iso-extract/wce:
	sudo mkdir -p $@

iso-extract/wce/live-triage: wce/live-triage
	sudo install -m 755 $< $@

iso-extract/wce/initrd.img.md5: iso-extract/live/initrd.img
	md5sum $< | cut -d ' ' -f 1 > /var/tmp/initrd.img.md5
	sudo cp /var/tmp/initrd.img.md5 $@

iso-extract/wce/vmlinuz.md5: iso-extract/live/vmlinuz
	md5sum $< | cut -d ' ' -f 1 > /var/tmp/vmlinuz.md5
	sudo cp /var/tmp/vmlinuz.md5 $@

iso-extract/wce/install-ubuntu.py: wce/install-ubuntu.py
	sudo install -m 755 $< $@

iso-extract/wce/$(PYTHON_DIALOG): $(PYTHON_DIALOG)
	sudo install -m 555 $< $@

iso-extract/wce/$(PYTHON_SUPPORT): $(PYTHON_SUPPORT)
	sudo install -m 555 $< $@

iso-extract/wce/$(DIALOG): $(DIALOG)
	sudo install -m 555 $< $@

iso-extract/syslinux/%.png: wce/%.png
	sudo cp $< $@

iso-extract/syslinux/isolinux.cfg: wce/isolinux.cfg.template version
	sed s/###VERSION###/${WCEVERSION}/g $< > wce/isolinux.cfg
	sudo cp wce/isolinux.cfg $@
	rm -f wce/isolinux.cfg

iso-extract/live/filesystem.squashfs: $(LIVEPATCHES)
	if ! dpkg-query -s squashfs-tools > /dev/null 2>&1 ; then sudo apt-get -y install squashfs-tools ; fi
	sudo chmod +w iso-extract/live/filesystem.packages
	sudo chroot live-image dpkg-query -W --showformat='$${Package} $${Version}\n' > wce/filesystem.packages
	sudo cp wce/filesystem.packages iso-extract/live/filesystem.packages
	sudo rm -f iso-extract/live/filesystem.squashfs
	sudo mksquashfs live-image iso-extract/live/filesystem.squashfs -noappend -always-use-fragments -b 256K
	sudo chown $(USER) iso-extract/live/filesystem.squashfs
	sudo chmod 755 iso-extract/live/filesystem.squashfs
	printf $$(sudo du -sx --block-size=1 live-image | cut -f1) > wce/filesystem.size
	sudo cp wce/filesystem.size iso-extract/live/filesystem.size


$(ISOTARGET): $(SOURCES) version Makefile
	if ! dpkg-query -l genisoimage > /dev/null 2>&1 ; then sudo apt-get -y install genisoimage ; fi
	cd iso-extract;sudo genisoimage $(UDF_FLAGS) -f -r -J -l -V "$$IMAGE_NAME" -cache-inodes -b syslinux/isolinux.bin -c syslinux/boot.cat -no-emul-boot -boot-load-size 4 -boot-info-table -publisher worldcomputerexchange.org -p ntai@smartfruit.com -input-charset utf-8 -output-charset utf-8 -V "wce_triage_$(WCEVERSION)" -o ../$(ISOTARGET) .


gpg-key:
	wget -q http://drbl.org/GPG-KEY-DRBL -O- | sudo apt-key add -
	wget -q http://drbl.sourceforge.net/GPG-KEY-DRBL -O- | sudo apt-key add -

/usr/lib/syslinux:
	sudo apt-get -y install syslinux syslinux-common

/usr/lib/syslinux/pxelinux.0: /usr/lib/syslinux

/var/lib/tftpboot/wce/live/% : iso-extract/live/%
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
/var/lib/tftpboot/wce/live/ipxe.lkn \
/var/lib/tftpboot/wce/live/initrd.img \
/var/lib/tftpboot/wce/live/memtest \
/var/lib/tftpboot/wce/live/vmlinuz

.phony: clean

clean:
	-chmod 644 filesystem.squashfs
	sudo rm -fR filesystem.squashfs iso-extract live-image live-image-original live-image-temp clonezilla_live
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
	# echo "deb http://drbl.sourceforge.net/drbl-core drbl stable" > /tmp/drbl.list
	# sudo cp /tmp/drbl.list /etc/apt/sources.list.d/drbl.list
	sudo apt-get update
