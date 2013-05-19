#!/bin/sh

mount --bind /dev/ ./fsimage/dev

cat > ./fsimage/tmp/temp-chores <<EOF
#!/bin/sh
mount -t proc none /proc
mount -t sysfs none /sys
mount -t devpts none /dev/pts
# 
#update-rc.d -f rpcbind-boot remove
#
# Things to do
apt-get update
apt-get purge -y --ignore-missing defoma ttf-unifont unifont xfonts-encodings xfonts-unifont x11-common xfonts-utils w3m libxfont1 libfontenc1 libgc1c2
apt-get install -y --allow-unauthenticated --force-yes python-minimal python-support python python-dialog python-support lm-sensors fancontrol wireless-tools python-dialog xz-utils mg smartmontools wipe pigz lzop kbd partclone 
apt-get clean
#
rm -fR /var/cache/apt/* /var/lib/apt/lists/* /tmp/*
dpkg -l > /tmp/dpkg-list
#
umount /proc || umount -lf /proc
umount /sys
umount /dev/pts
EOF

chmod +x ./fsimage/tmp/temp-chores
/usr/sbin/chroot ./fsimage  /bin/sh /tmp/temp-chores
sleep 1
umount ./fsimage/dev
