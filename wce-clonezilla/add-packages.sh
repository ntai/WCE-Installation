#!/bin/sh

mount --bind /dev/ ./fsimage/dev

cat > ./fsimage/tmp/temp-chores <<EOF
#!/bin/sh
mount -t proc none /proc
mount -t sysfs none /sys
mount -t devpts none /dev/pts
# Things to do
apt-get update
apt-get install -y lm-sensors fancontrol wireless-tools python-dialog xz-utils emacs22-nox smartmontools wipe pigz lzop
apt-get clean
#
umount /proc || umount -lf /proc
umount /sys
umount /dev/pts
EOF

chmod +x ./fsimage/tmp/temp-chores
/usr/sbin/chroot ./fsimage  /bin/sh /tmp/temp-chores
umount ./fsimage/dev
