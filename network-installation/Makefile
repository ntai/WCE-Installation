
CLONEZILLA_LIVE := clonezilla-live-20140915-trusty-i386.iso

TARGETS = \
/etc/network/interfaces \
/etc/dnsmasq.conf \
/etc/vsftpd.conf \
/etc/inetd.conf \
/etc/lighttpd.conf \
../wce-clonezilla/$(CLONEZILLA_LIVE)


default: $(TARGETS)
	if ! dpkg-query -s squashfs-tools > /dev/null 2>&1 ; then sudo apt-get -y install squashfs-tools ; fi
	if ! dpkg-query -s syslinux > /dev/null 2>&1 ; then sudo apt-get -y install syslinux ; fi
	if ! dpkg-query -s openbsd-inetd > /dev/null 2>&1 ; then sudo apt-get -y install openbsd-netd ; fi
	if ! dpkg-query -s git > /dev/null 2>&1 ; then sudo apt-get -y install git ; fi
	if ! dpkg-query -s nfs-kernel-server > /dev/null 2>&1 ; then sudo apt-get -y install nfs-kernel-server ; fi
	if ! dpkg-query -s genisoimage > /dev/null 2>&1 ; then sudo apt-get -y install genisoimage ; fi
	if ! dpkg-query -s lighttpd > /dev/null 2>&1 ; then sudo apt-get -y install lighttpd ; fi
	if ! dpkg-query -s atftpd > /dev/null 2>&1 ; then sudo apt-get -y install atftpd ; fi
	if ! dpkg-query -s dnsmasq > /dev/null 2>&1 ; then sudo apt-get -y install dnsmasq ; fi


/etc/% : etc/%
	sudo cp -p $< $@


../wce-clonezilla/$(CLONEZILLA_LIVE):
	wget http://files.smartfruit.com/wce/$(CLONEZILLA_LIVE) -O $@
