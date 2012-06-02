#!/bin/sh

for pkg in make openbsd-inetd openssh-server lighttpd dnsmasq atftpd git genisoimage nfs-kernel-server vsftpd
do
  status=$(dpkg-query -s $pkg 2>/dev/null | grep Status: | cut -d ' ' -f 4)
  if [ x$status != xinstalled ] ; then
    sudo aptitude install -y $pkg
  fi
done

cat > /tmp/interfaces <<EOF
# The loopback network interface
auto lo
iface lo inet loopback

# The primary network interface
auto eth0
iface eth0 inet static
 address 10.1.1.1
 netmask 255.255.255.0

allow-hotplug eth1
iface eth1 inet dhcp

EOF

sudo install /tmp/interfaces /etc/network/interfaces

cat > /tmp/lighttpd.conf <<EOF

server.modules = (
	"mod_access",
	"mod_alias",
	"mod_compress",
 	"mod_redirect",
#       "mod_rewrite",
)

server.document-root        = "/var/www"
server.upload-dirs          = ( "/var/cache/lighttpd/uploads" )
server.errorlog             = "/var/log/lighttpd/error.log"
server.pid-file             = "/var/run/lighttpd.pid"
server.username             = "www-data"
server.groupname            = "www-data"

index-file.names            = ( "index.html",
                                "index.htm", "default.htm",
                                "index.lighttpd.html" )

url.access-deny             = ( "~", ".inc" )

static-file.exclude-extensions = ( ".php", ".pl", ".fcgi" )

dir-listing.encoding        = "utf-8"
server.dir-listing          = "enable"

compress.cache-dir          = "/var/cache/lighttpd/compress/"
compress.filetype           = ( "application/x-javascript", "text/css", "text/html", "text/plain" )
EOF

sudo install /tmp/lighttpd.conf /etc/lighttpd.conf

cat > /tmp/inetd.conf <<EOF
tftp		dgram	udp4	wait	nobody /usr/sbin/tcpd /usr/sbin/in.tftpd --tftpd-timeout 300 --retry-timeout 5 --mcast-port 1758 --mcast-addr 239.239.239.0-255 --mcast-ttl 1 --maxthread 100 --verbose=5 /var/lib/tftpboot
EOF

sudo install /tmp/inetd.conf /etc/inetd.conf

cat > /tmp/dnsmasq.conf <<EOF
no-dhcp-interface=eth1
no-hosts
address=/wceinstall/10.1.1.1
address=/wcesrv/10.1.1.1
dhcp-range=10.1.1.100,10.1.1.199,2h
pxe-service=x86PC, "Boot from local disk"
pxe-service=x86PC, "Install WCE Ubuntu", pxelinux
conf-dir=/etc/dnsmasq.d
EOF

sudo install /tmp/dnsmasq.conf /etc/dnsmasq.conf


cat > /tmp/vsftpd.conf <<EOF
listen=YES
anonymous_enable=YES
dirmessage_enable=NO
use_localtime=YES
xferlog_enable=NO
connect_from_port_20=YES
chroot_list_enable=YES
pam_service_name=vsftpd
ls_recurse_enable=YES
anon_root=/var/www
EOF

sudo install /tmp/vsftpd.conf /etc/vsftpd.conf


if [ ! -d WCE-Installation ] ; then
git clone git://github.com/ntai/WCE-Installation.git
fi
cd WCE-Installation/wce-clonezilla
make
