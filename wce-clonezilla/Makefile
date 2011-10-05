#
# The clonezilla live original CD
#
CLONEZILLA_LIVE := clonezilla-live-20110113-maverick.iso

ISOTARGET := wce-clonezilla-v0.45-lite.iso

default: fsimage $(ISOTARGET)

.phony: gpg-key

#DISKIMAGES := $(shell ls extract-cd/wce-disk-images/*.partclone.gz)
DISKIMAGES := 


LIVEPATCHES := \
 fsimage/wce.py \
 fsimage/etc/ocs/ocs-live.conf \
 fsimage/etc/default/console-setup \
 fsimage/opt/drbl/sbin/ocs-live-wce \
 fsimage/opt/drbl/conf/drbl.conf \
 fsimage/etc/apt/sources.list


SOURCES := \
 extract-cd/live/filesystem.squashfs \
 extract-cd/isolinux/isolinux.cfg \
 extract-cd/isolinux/wcebg1.png \
 extract-cd/isolinux/wcebg2.png \
 ${DISKIMAGES}

$(CLONEZILLA_LIVE) :
	wget http://free.nchc.org.tw/clonezilla-live/alternative/oldstable/clonezilla-live-20110113-maverick.iso -O $@

extract-cd: $(CLONEZILLA_LIVE)
	-sudo mkdir clonezilla_live
	sudo mount -o loop ./$(CLONEZILLA_LIVE) clonezilla_live
	-mkdir ./extract-cd
	sudo cp -pR ./clonezilla_live/* ./extract-cd
	sudo umount clonezilla_live
	sudo rmdir clonezilla_live

fsimage: extract-cd
	-mkdir fsimage
	-mkdir fsimage-temp
	sudo mount -o loop extract-cd/live/filesystem.squashfs fsimage-temp
	sudo cp -pR fsimage-temp/* ./fsimage
	sudo umount fsimage-temp
	rmdir fsimage-temp
	sudo ./add-packages.sh


fsimage/wce.py: wce/install-ubuntu.py
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


extract-cd/isolinux/wcebg1.png: wce/wcebg1.png
	sudo cp $< $@

extract-cd/isolinux/wcebg2.png: wce/wcebg2.png
	sudo cp $< $@

extract-cd/isolinux/isolinux.cfg: wce/isolinux.cfg
	sudo cp $< $@


extract-cd/live/filesystem.squashfs: $(LIVEPATCHES)
	sudo chmod +w extract-cd/live/filesystem.packages
	sudo chroot fsimage dpkg-query -W --showformat='$${Package} $${Version}\n' > wce/filesystem.packages
	sudo cp wce/filesystem.packages extract-cd/live/filesystem.packages
	sudo rm -f extract-cd/live/filesystem.squashfs
	sudo mksquashfs fsimage extract-cd/live/filesystem.squashfs
	sudo chown $(USER):$(USER) extract-cd/live/filesystem.squashfs
	sudo chmod 755 extract-cd/live/filesystem.squashfs
	printf $$(sudo du -sx --block-size=1 fsimage | cut -f1) > wce/filesystem.size
	sudo cp wce/filesystem.size extract-cd/live/filesystem.size


$(ISOTARGET): $(SOURCES)
	cd extract-cd;sudo mkisofs -D -r -V "$$IMAGE_NAME" -cache-inodes -J -l -b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot -boot-load-size 4 -boot-info-table -o ../$(ISOTARGET) .


gpg-key:
	wget -q http://drbl.org/GPG-KEY-DRBL -O- | sudo apt-key add -
	wget -q http://drbl.sourceforge.net/GPG-KEY-DRBL -O- | sudo apt-key add -


/var/lib/tftpboot/wce/live/% : /home/ntai/wce/wce-clonezilla/extract-cd/live/%
	sudo cp -p $< $@

tftp: /var/lib/tftpboot/wce/live/filesystem.size \
/var/lib/tftpboot/wce/live/filesystem.squashfs \
/var/lib/tftpboot/wce/live/freedos.img \
/var/lib/tftpboot/wce/live/gpxe.lkn \
/var/lib/tftpboot/wce/live/initrd \
/var/lib/tftpboot/wce/live/initrd.img \
/var/lib/tftpboot/wce/live/memtest \
/var/lib/tftpboot/wce/live/vmlinuz

clean:
	sudo rm -fR extract-cd fsimage fsimage-temp clonezilla_live
	rm -f wce/filesystem.packages wce/filesystem.size


