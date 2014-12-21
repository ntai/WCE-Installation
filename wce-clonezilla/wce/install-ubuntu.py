#!/usr/bin/env python
#
# install-ubuntu.py
# is the installer/imager/triage Python script for WCE.
#
# The idea behind this is because, we want to have a single triage/installer
# CD. 
# For the triage, it picks up the machine vitals such as RAM, optical dirve
# spec, hard disk capacity, CPU class designation. 
# It also does the network detection by running dhclient so that it can
# talk to the router.
# 
# If you stop there, then it's triage. If you proceed, it continues to
# install the ubuntu image using partclone.
# 
#
import os, sys, subprocess, re, string, getpass, time, shutil, uuid, urllib, select, urlparse, datetime, getopt, traceback
try:
    import shlex
except:
    pass

installer_version = "0.66"

wce_release_file_name = 'wce-release'

fstab_template = '''# /etc/fstab: static file system information.
#
# Use 'blkid -o value -s UUID' to print the universally unique identifier
# for a device; this may be used with UUID= as a more robust way to name
# devices that works even if disks are added and removed. See fstab(5).
#
# <file system> <mount point>   <type>  <options>       <dump>  <pass>
proc            /proc           proc    nodev,noexec,nosuid 0       0
# / was on /dev/sda1 during installation
UUID=%s /               ext4    errors=remount-ro 0       1
# swap was on /dev/sda5 during installation
UUID=%s none            swap    sw              0       0
'''

dialog_rc_filename = "/tmp/triage-dialog-rc"
triage_txt = "/tmp/triage.txt"

dialog_rc_failure_template = '''
aspect = 0
separate_widget = ""
tab_len = 0
visit_items = OFF
use_shadow = OFF
use_colors = ON
screen_color = (YELLOW,RED,ON)
shadow_color = (BLACK,BLACK,ON)
dialog_color = (BLACK,WHITE,OFF)
title_color = (BLUE,WHITE,ON)
border_color = (WHITE,WHITE,ON)
button_active_color = (WHITE,BLUE,ON)
button_inactive_color = (BLACK,WHITE,OFF)
button_key_active_color = (WHITE,BLUE,ON)
button_key_inactive_color = (RED,WHITE,OFF)
button_label_active_color = (YELLOW,BLUE,ON)
button_label_inactive_color = (BLACK,WHITE,ON)
inputbox_color = (BLACK,WHITE,OFF)
inputbox_border_color = (BLACK,WHITE,OFF)
searchbox_color = (BLACK,WHITE,OFF)
searchbox_title_color = (BLUE,WHITE,ON)
searchbox_border_color = (WHITE,WHITE,ON)
position_indicator_color = (BLUE,WHITE,ON)
menubox_color = (BLACK,WHITE,OFF)
menubox_border_color = (WHITE,WHITE,ON)
item_color = (BLACK,WHITE,OFF)
item_selected_color = (WHITE,BLUE,ON)
tag_color = (BLUE,WHITE,ON)
tag_selected_color = (YELLOW,BLUE,ON)
tag_key_color = (RED,WHITE,OFF)
tag_key_selected_color = (RED,BLUE,ON)
check_color = (BLACK,WHITE,OFF)
check_selected_color = (WHITE,BLUE,ON)
uarrow_color = (GREEN,WHITE,ON)
darrow_color = (GREEN,WHITE,ON)
itemhelp_color = (WHITE,BLACK,OFF)
form_active_text_color = (WHITE,BLUE,ON)
form_text_color = (WHITE,CYAN,ON)
form_item_readonly_color = (CYAN,WHITE,ON)
'''


patch_grub_cfg = '''#
cp /boot/grub/grub.cfg /tmp/grub.cfg
sed "s/root='(hd.,1)'/root='(hd0,1)'/g" /tmp/grub.cfg > /boot/grub/grub.cfg
'''

# PCI vendors. use lower case
PCI_VENDOR_SIS = "1039"
PCI_VENDOR_VIA = "1106"
PCI_VENDOR_NVIDIA = "10de"
PCI_VENDOR_ATI = "1002"

# Ethernet device blacklist
#
# SIS 191 gigabit controller 1039:0191 does not work.
# 

ethernet_device_blacklist = { PCI_VENDOR_SIS : { "0191" : True } }

#
# Video device blacklist
# 
# Some VIA UniChrome is not supported by OpenChrome driver
#
video_device_blacklist = { PCI_VENDOR_VIA : { "7205" : True } }


nvidia_xorg_conf = '''
Section "ServerLayout"
    Identifier     "Layout0"
    Screen      0  "Screen0" 0 0
    InputDevice    "Keyboard0" "CoreKeyboard"
    InputDevice    "Mouse0" "CorePointer"
EndSection

Section "InputDevice"
    # generated from default
    Identifier     "Mouse0"
    Driver         "mouse"
    Option         "Protocol" "auto"
    Option         "Device" "/dev/psaux"
    Option         "Emulate3Buttons" "no"
    Option         "ZAxisMapping" "4 5"
EndSection

Section "InputDevice"
    # generated from default
    Identifier     "Keyboard0"
    Driver         "kbd"
EndSection

Section "Monitor"
    # HorizSync source: edid, VertRefresh source: edid
    Identifier     "Monitor0"
    Option         "DPMS"
EndSection

Section "Device"
    Identifier     "Device0"
    Driver         "nvidia"
    VendorName     "NVIDIA Corporation"
EndSection

Section "Screen"
    Identifier     "Screen0"
    Device         "Device0"
    Monitor        "Monitor0"
EndSection
'''

dhclient_conf = '''
timeout 5;
retry 0;
initial-interval 1;
'''

etc_network_interfaces = '''
auto lo
iface lo inet loopback
iface eth0 inet dhcp
iface eth1 inet dhcp
iface eth2 inet dhcp
'''



lspci_nm_re = re.compile(r'\s*([0-9a-f]{2}:[0-9a-f]{2}.[0-9a-f])\s+"([0-9a-f]{4})"\s+"([0-9a-f]{4})"\s+"([0-9a-f]{4})"')

disk_images = []

class mkfs_failed(Exception):
    pass

class unmount_failed(Exception):
    pass


def get_transport_scheme(u):
    transport_scheme = None
    try:
        transport_scheme = urlparse.urlsplit(u).scheme
    except:
        pass
    return transport_scheme


lspci_output = None

def get_lspci_nm_output():
    global lspci_output
    if not lspci_output:
        lspci = subprocess.Popen("lspci -nm", shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        (lspci_output, err) = lspci.communicate()
        pass
    return lspci_output


def get_lspci_device_desc(pci_id):
    lspci = subprocess.Popen("lspci -mm -s %s" % pci_id, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    (out, err) = lspci.communicate()
    lspci_mm_s_re = re.compile(r'\s*([0-9a-f]{2}:[0-9a-f]{2}.[0-9a-f])\s+"([^"]*)"\s+"([^"]*)"\s+"([^"]*)"\s+([^\s]+)\s+"([^"]*)"\s+"([^"]*)"\s*')
    m = lspci_mm_s_re.match(out.strip())
    if m:
        return m.group(3) + " " + m.group(4)
    return ""


def detect_video_cards():
    n_nvidia = 0
    n_ati = 0
    n_vga = 0
    n_black_vga = 0
    out = get_lspci_nm_output()
    blacklisted_videos = []
    for line in out.split('\n'):
        m = lspci_nm_re.match(line)
        if m:
            # Display controller
            if m.group(2) == '0300':
                vendor_id = m.group(3).lower()
                device_id = m.group(4).lower()

                if video_device_blacklist.has_key(vendor_id) and video_device_blacklist[vendor_id].has_key(device_id):
                    blacklisted_videos.append(get_lspci_device_desc(m.group(1)))
                    n_black_vga = n_black_vga + 1
                elif vendor_id == PCI_VENDOR_NVIDIA:
                    # nVidia
                    n_nvidia = n_nvidia + 1
                    pass
                elif vendor_id == PCI_VENDOR_ATI:
                    # ATI
                    n_ati = n_ati + 1
                    pass
                else:
                    n_vga = n_vga + 1
                    pass
                pass
            pass
        pass
    return (n_nvidia, n_ati, n_vga, n_black_vga, blacklisted_videos)


def uuidgen():
    return str(uuid.uuid1())

def get_filename_stem(p):
    basename = os.path.basename(p)
    while 1:
        ext = ""
        try:
            basename, ext = os.path.splitext(basename)
        except:
            pass
        if ext == "":
            break
        pass
    return basename


def get_router_ip_address():
    netstat = subprocess.Popen("netstat -rn", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    (out, err) = netstat.communicate()
    routes_re = re.compile(r'([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+\w+\s+\d+\s+\d+\s+\d+\s+(\w+)')
    for line in out.split('\n'):
        m = routes_re.match(line)
        if m and m.group(1) == '0.0.0.0':
            return m.group(2)
        pass
    return None
            

def is_network_connected():
    connected = False
    try:
        carrier = open("/sys/class/net/eth0/carrier")
        carrier_state = carrier.read()
        carrier.close()
        connected = string.atoi(carrier_state) == 1
    except:
        pass
    if not connected:
        try:
            carrier = open("/sys/class/net/eth1/carrier")
            carrier_state = carrier.read()
            carrier.close()
            connected = string.atoi(carrier_state) == 1
        except:
            pass
        pass
    return connected
            

class partition:
    def __init__(self):
        self.device_name = None
        self.partition_name = None
        self.partition_type = None
        self.partition_number = None
        pass

    def start_mkfs(self, name):
        mkfs = None
        if self.partition_type == 'c':
            mkfs = subprocess.Popen(["mkfs.vfat", "-F", "32", "-n", name, self.device_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        elif self.partition_type == '83':
            mkfs = subprocess.Popen(["mkfs.ext2", "-b", "4096", "-L", name, self.device_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            pass
        self.partition_name = name
        return mkfs


    def unmount(self):
        unmount = subprocess.Popen(["/bin/umount", "-f", self.device_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = unmount.communicate()
        pass

    def get_mount_point(self):
        return "/media/%s" % self.partition_name
    
    def mount(self):
        mount_point = self.get_mount_point()
        if not os.path.exists(mount_point):
            os.mkdir(mount_point)
            pass
        subprocess.call(["/bin/mount", self.device_name, mount_point], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        pass


    def install_bootloader(self):
        syslinux = subprocess.Popen(["/usr/bin/syslinux", "-maf", self.device_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = syslinux.communicate()
        pass

    pass


#
# disk class represents a disk
#
class disk:
    def __init__(self):
        self.device_name = None
        self.partitions = []
        self.disk_type = None
        self.size = None
        self.byte_size = None
        self.sectors = None
        self.uuid1 = None
        self.uuid2 = None
        self.mounted = False
        self.partclone_image = "/ubuntu.partclone.gz"
        self.is_disk = None
        self.is_ata_or_scsi = None
        self.is_usb = None
        self.model_name = ""
        self.serial_no = ""
        self.mount_dir = "/mnt/wce_install_target.%d" % os.getpid()
        self.wce_release_file = os.path.join(self.mount_dir, "etc", wce_release_file_name)
        pass

    def find_partition(self, part_name):
        for part in self.partitions:
            if part.device_name == part_name:
                return part
            pass
        return None

    def install_ubuntu(self, memsize, newhostname, grub_cfg_patch):
        ask_continue = True
        try:
            self.partition_disk(memsize, True)
            ask_continue = False
        except mkfs_failed, e:
            pass
        
        if ask_continue:
            yes_no = getpass._raw_input("  mkfs failed continue? ([Y]/n) ")
            if (len(yes_no) > 0) and (yes_no[0].lower() == 'n'):
                sys.exit(0)
                pass
            pass

        # self.restore_disk("/cdrom/ubuntu.dump")

        self.partclone_restore_disk(self.partclone_image)
        self.assign_uuid_to_partitions()
        self.mount_disk()
        self.finalize_disk(newhostname, grub_cfg_patch)
        self.create_wce_tag(self.partclone_image)
        pass


    def post_install(self, remote_hook_name, hook_file, addition_dir, addition_tar):
        if remote_hook_name:
            try_hook(remote_hook_name, do_exec=False)
            pass
        if hook_file:
            run_hook_file(hook_file, do_exec=False)
            pass
        if addition_dir:
            print "Copying additional contents from directory %s" % addition_dir
            subprocess.call("cp -prvP %s -t %s" % (addition_dir, self.mount_dir), shell=True)
            print "Additional contents copied."
            pass
        if addition_tar:
            print "Expanding additional tar file %s" % addition_tar
            subprocess.call("tar -xv --directory %s -f %s " % (self.mount_dir, addition_tar), shell=True)
            print "Additional contents copied."
            pass
        pass


    def partition_disk(self, memsize, verbose):
        if not self.sectors:
            parted = subprocess.Popen("parted -s -m %s unit s print" % (self.device_name), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (out, err) = parted.communicate()
            if parted.returncode != 0:
                if verbose:
                    print "# %s disk partitioning (parted) failed." % (self.device_name)
                    sys.stderr.write(err)
                    pass
                return parted.returncode
            lines = out.split("\n")
            disk_line = lines[1]
            columns = disk_line.split(":")
            if columns[0] != self.device_name:
                if verbose:
                    print "# %s parted format changed!? Talk to Tai" % (self.device_name)
                    pass
                sys.exit(1)
                pass
            sectors = string.atoi(columns[1][:-1])
            self.sectors = sectors
            pass
        else:
            sectors = self.sectors
            pass
        if verbose:
            print "# %s Disk has %d sectors" % (self.device_name, sectors)
            pass

        # Everything is multiple of 8, so that 4k sector problem never happens

        sectors = (sectors / 8) * 8

        # first, memsize and sectors.
        max_swap_sectors = 3 * (((memsize * 1024) / 512) * 1024)
        min_swap_sectors = (((memsize * 1024) / 512) * 1024) / 2
        swap_sectors = sectors / 20
        if swap_sectors > max_swap_sectors:
            swap_sectors = max_swap_sectors
            pass

        if swap_sectors < min_swap_sectors:
            swap_sectors = min_swap_sectors
            pass
        
        part1_start = 2048
        part2_start = ((sectors - part1_start - swap_sectors - 8) / 8) * 8
        part5_start = part2_start + 8
        part1_end = part2_start - 1
        part2_end = sectors - 1 
        part5_end = part2_end

        args = ["parted", "-s", self.device_name, "unit", "s", "mklabel", "msdos", "mkpart", "primary", "ext2", "2048", "%d" % part1_end, "mkpart", "extended", "%d" % part2_start, "%d" % part2_end, "mkpart", "logical", "linux-swap", "%d" % part5_start, "%d" % part5_end, "set", "1", "boot", "on" ]
        if verbose:
            print "# %s Executing " % (self.device_name) + " ".join(args)
            pass
        parted = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = parted.communicate()
        return parted.returncode


    def mkfs_partition_1(self):
        print "mkfs - takes a while, a few minutes"

        mkfs_out = open("/tmp/mkfs.out", "w")
        mkfs_err = open("/tmp/mkfs.err", "w")
        mkfs = subprocess.Popen(["mkfs", "-t", "ext4", "-b", "4096", "%s1" % self.device_name], stdout=mkfs_out, stderr=mkfs_err)
        i = 0
        wheel = "|/-\\"
        while mkfs.returncode is None:
            time.sleep(0.3)
            sys.stdout.write("\r%s" % wheel[ i ])
            sys.stdout.flush()
            i = (i + 1) % len(wheel)
            mkfs.poll()
            pass
        print ""
        print "Done mkfs"
        print ""
        mkfs_out.close()
        mkfs_err.close()
        if mkfs.returncode != 0:
            print "mkfs failed!"
            mkfs_err = open("/tmp/mkfs.err")
            sys.stderr.write(mkfs_err.read())
            mkfs_err.close()
            raise mkfs_failed
        pass


    def assign_uuid_to_partitions(self):
        self.uuid1 = uuidgen()
        self.uuid2 = uuidgen()

        s2 = subprocess.Popen(["tune2fs", "%s1" % self.device_name, "-U", self.uuid1, "-L", "/"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        s2.communicate()
        s3 = subprocess.Popen(["mkswap", "-U", self.uuid2, "%s5" % self.device_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        s3.communicate()
        pass

    def get_uuid_from_partitions(self):
        self.uuid1 = None
        self.uuid2 = None
        blkid_re = re.compile(r'/dev/(\w+)1: LABEL="([/\w\.\d]+)" UUID="([\w\d]+-[\w\d]+-[\w\d]+-[\w\d]+-[\w\d]+)" TYPE="([\w\d]+)"')
        blkid1 = subprocess.Popen(["/sbin/blkid", "%s1" % self.device_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = blkid1.communicate()
        for line in out.split('\n'):
            m = blkid_re.match(line)
            if m:
                self.uuid1 = m.group(2)
                break
            pass
        blkid5 = subprocess.Popen(["/sbin/blkid", "%s5" % self.device_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = blkid5.communicate()
        for line in out.split('\n'):
            m = blkid_re.match(line)
            if m:
                self.uuid2 = m.group(2)
                break
            pass
        pass
        

    def unmount_partitions(self):
        for part in self.partitions:
            part.unmount()
            pass
        pass


    def mount_partitions(self):
        for part in self.partitions:
            part.mount()
            pass
        pass


    def mount_disk(self):
        if self.mounted:
            return

        # Mount it to self.mount_dir
        if not os.path.exists(self.mount_dir):
            os.mkdir(self.mount_dir)
            pass

        s4 = subprocess.Popen(["mount", "%s1" % self.device_name, self.mount_dir])
        s4.communicate()

        self.mounted = True
        pass


    def restore_disk(self, dump_image_file):
        # Needs to mkfs first for restore
        self.mkfs_partition_1()

        print "restoring disk image"

        self.mount_disk()

        os.chdir(self.mount_dir)

        # Restore ubuntu 
        print "restore -- this takes about 10-20 minutes"
        restore_out = open("/tmp/restore.out", "w")
        restore_err = open("/tmp/restore.err", "w")
        restore = subprocess.Popen(["restore", "-r", "-f", dump_image_file], stdout=restore_out, stderr=restore_err)
        i = 0
        wheel = "|/-\\"
        while restore.returncode is None:
            time.sleep(0.3)
            restore.poll()
            sys.stdout.write("\r%s" % wheel[ i ])
            sys.stdout.flush()
            i = (i + 1) % len(wheel)
            pass
        pass
        print ""
        print "Done restore"
        print ""
        restore_out.close()
        restore_err.close()
        pass


    def partclone_restore_disk(self, partclone_image_file):
        print "restoring disk image"

        ext = ""
        try:
            ext = os.path.splitext(partclone_image_file)[1]
        except:
            pass
        if ext == ".7z":
            decomp = "7z e -so"
        elif ext == ".gz":
            decomp = "gunzip -c"
        elif ext == ".xz":
            decomp = "unxz -c"
        elif ext == ".partclone":
            # aka no compression
            decomp = "cat"
        elif ext == ".lzo":
            decomp = "lzop -dc"
        else:
            decomp = "gunzip -c"
            pass

        transport_scheme = get_transport_scheme(partclone_image_file)
        if transport_scheme:
            retcode = subprocess.call("wget -q -O - '%s' | %s | partclone.ext4 -r -s - -o %s1" % (partclone_image_file, decomp, self.device_name), shell=True)
        else:
            if decomp == "cat":
                retcode = subprocess.call("partclone.ext4 -r -s %s -o %s1" % (partclone_image_file, self.device_name), shell=True)
            else:
                retcode = subprocess.call("%s '%s' | partclone.ext4 -r -s - -o %s1" % (decomp, partclone_image_file, self.device_name), shell=True)
                pass
            pass

        if retcode != 0:
            print "\nrestore failed\n"
            sys.exit(1)
            pass

        # Enalrge the ext4 partition. First get partition size
        parted = subprocess.Popen("parted -s -m %s unit s print" % (self.device_name), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = parted.communicate()
        partition_size = None
        for line in out.split('\n'):
            columns = line.split(':')
            if columns[0] == "1":
                partition_size = string.atoi(columns[3][:-1])
                break
            pass

        retcode = subprocess.call("/sbin/e2fsck -f -y %s1" % (self.device_name), shell=True)
        if retcode != 0:
            return retcode
        retcode = subprocess.call("resize2fs -p %s1" % (self.device_name), shell=True)
        return retcode


    def finalize_disk(self, newhostname, grub_cfg_patch):
        print "# %s Finalizing disk" % (self.device_name)

        blkid = subprocess.Popen(["blkid"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = blkid.communicate()

        this_disk = re.compile(r'(' + self.device_name + r'\d): ((LABEL=\"[^"]+\") ){0,1}(UUID=\"([0-9a-f-]+)\")\s+TYPE=\"([a-z0-9]+)\"')

        for line in out.split("\n"):
            m = this_disk.match(line)
            if m:
                if m.group(6) == "swap":
                    self.uuid2 = m.group(5)
                elif  m.group(6)[0:3] == "ext":
                    self.uuid1 = m.group(5)
                    pass
                pass
            pass

        print "# Primary %s1 - UUID: %s" % (self.device_name, self.uuid1)
        print "# Swap    %s5 - UUID: %s" % (self.device_name, self.uuid2)
        
        # patch up the restore
        fstab = open("%s/etc/fstab" % self.mount_dir, "w")
        fstab.write(fstab_template % (self.uuid1, self.uuid2))
        fstab.close()

        print "# fstab done"

        #
        # New hostname
        #
        if newhostname:
            # Set up the /etc/hostname
            etc_hostname_filename = "%s/etc/hostname" % self.mount_dir
            hostname_file = open(etc_hostname_filename, "w")
            hostname_file.write("%s\n" % newhostname)
            hostname_file.close()
            print "# /etc/hostname done"

            # Set up the /etc/hosts file
            etc_hosts_filename = "%s/etc/hosts" % self.mount_dir
            hosts = open(etc_hosts_filename, "r")
            lines = hosts.readlines()
            hosts.close()
            hosts = open(etc_hosts_filename, "w")

            this_host = re.compile(r"127\.0\.1\.1\s+[a-z_A-Z0-9]+\n")
            for line in lines:
                m = this_host.match(line)
                if m:
                    hosts.write("127.0.1.1\t%s\n" % newhostname)
                else:
                    hosts.write(line)
                    pass
                pass
            hosts.close()
            print "# /etc/hosts done"
            sys.stdout.flush()
            pass

        #
        # Remove the persistent rules
        # 
        print "# rm -f %s/etc/udev/rules.d/70-persistent*" % self.mount_dir
        sys.stdout.flush()
        retcode = subprocess.call("rm -f %s/etc/udev/rules.d/70-persistent*" % self.mount_dir, shell=True)

        #
        # Remove the WCE follow up files
        # 
        print "# rm -f %s/var/lib/world-computer-exchange/computer-uuid" % self.mount_dir
        sys.stdout.flush()
        retcode = subprocess.call("rm -f %s/var/lib/world-computer-exchange/computer-uuid" % self.mount_dir, shell=True)
        print "# rm -f %s/var/lib/world-computer-exchange/access-timestamp" % self.mount_dir
        sys.stdout.flush()
        retcode = subprocess.call("rm -f %s/var/lib/world-computer-exchange/access-timestamp" % self.mount_dir, shell=True)

        print "# removing some files done."
        sys.stdout.flush()

        # It needs to do a few things before chroot
        # Try copy the /etc/resolve.conf
        # try:
        #     shutil.copy2("/etc/resolv.conf", "%s/etc/resolv.conf" % self.mount_dir)
        # except:
        #     # Not a big deal if it does not exist
        #     pass

        # Now, chroot to the installing disk and do something more

        # Things to do is installing grub
        to_do = "grub-install %s\n" % self.device_name

        # Survey the video card situation
        # Remove the proprietary drivers if not needed.
        # It's particulary important now since Ubuntu developers
        # screwed up the nVidia driver.

        (n_nvidia, n_ati, n_vga, n_black_vga, blacklisted_videos) = detect_video_cards()
        
        if (n_ati > 0) or (n_vga > 0):
            to_do = to_do + "apt-get -q -y --force-yes purge `dpkg --get-selections | cut -f 1 | grep -v xorg | grep nvidia-`\n"
            pass

        #
        print "# calling chroot_and_exec for %s" % self.mount_dir
        chroot_and_exec(self.mount_dir, to_do, self.uuid1, grub_cfg_patch)

        #
        # Patch up the grub.cfg just in case the "/dev/disk/by-uuid/%s" % 
        # self.uuid1 does not exist. If that happens, grub-mkconfig 
        # genertes the device name based grub.cfg which is bad.
        #
        # This should fix up the most of unbootable disk imaging.
        #
        root_fs = "UUID=%s" % self.uuid1
        linux_re = re.compile(r'(\s+linux\s+[^ ]+\s+root=)([^ ]+)(\s+ro .*)')
        grub_cfg_file = open("%s/boot/grub/grub.cfg" % self.mount_dir)
        grub_cfg = grub_cfg_file.readlines()
        grub_cfg_file.close()
        grub_cfg_file = open("%s/boot/grub/grub.cfg" % self.mount_dir, "w")
        for line in grub_cfg:
            m = linux_re.match(line)
            if m:
                grub_cfg_file.write("%s%s%s\n" % (m.group(1), root_fs, m.group(3)))
            else:
                grub_cfg_file.write(line)
                pass
            pass
        grub_cfg_file.close()
        pass


    def create_wce_tag(self, image_file_name):
        # Set up the /etc/wce-release file
        release = open(self.wce_release_file, "w+")
        print >> release, "wce-contents: %s" % get_filename_stem(image_file_name)
        print >> release, "installer-version: %s" % installer_version
        print >> release, "installation-date: %s" % datetime.datetime.isoformat( datetime.datetime.utcnow() )
        release.close()
        pass


    def image_disk(self, stem_name):
        if  not os.path.exists("/mnt/www/wce-disk-images"):
            return
        self.imagename = "/mnt/www/wce-disk-images/%s-%s.partclone.gz" % (stem_name, datetime.date.today().isoformat())
        self.create_image()
        pass


    def create_image(self):
        if self.imagename == None:
            print "999 Image file name is not specified for create image. Bailing out."
            sys.exit(2)
            pass

        ext = ""
        try:
            ext = os.path.splitext(self.imagename)[1]
        except:
            pass
        if ext == ".7z":
            comp = "p7zip"
        elif ext == ".gz":
            comp = "pigz -9"
        elif ext == ".xz":
            comp = "xz --stdout"
        elif ext == ".partclone":
            # aka no compression
            comp = "cat"
        elif ext == ".lzo":
            comp = "lzop -c"
        else:
            comp = "cat"
            pass

        self.mount_disk()
        rm_args = ["rm", "-f"] + [ "%s%s" % (self.mount_dir, filename) for filename in ["/etc/wce-release", "/var/lib/world-computer-exchange/access-timestamp", "/var/lib/world-computer-exchange/computer-uuid", "/etc/udev/rules.d/70-persistent-cd.rules", "/etc/udev/rules.d/70-persistent-net.rules"] ]
        subprocess.call(rm_args)

        self.unmount_disk()

        print "001 Check file system integrity. (e2fsck)"
        sys.stdout.flush()
        e2fsck = subprocess.Popen("/sbin/e2fsck -f -y %s1" % self.device_name, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        e2fsck.communicate()
        print "010 Resize file system to smallest"
        sys.stdout.flush()
        resize2fs = subprocess.Popen("/sbin/resize2fs -M %s1" % self.device_name, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        resize2fs.communicate()
        print "019 Ready for imaging"
        sys.stdout.flush()

        if comp == "cat":
            partclone = subprocess.Popen("/usr/sbin/partclone.extfs -B -c -s %s1 -o %s" % (self.device_name, self.imagename), shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        else:
            partclone = subprocess.Popen("/usr/sbin/partclone.extfs -B -c -s %s1 -o - | %s > %s" % (self.device_name, comp, self.imagename), shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            pass

        read_set = [partclone.stdout, partclone.stderr]
        write_set = []

        partclone_output = ""
        partclone_error = ""

        start_re = []
        start_re.append(re.compile(r'Partclone [^ ]+ http://partclone.org\n'))
        start_re.append(re.compile(r'Starting to clone device \(/dev/\w+\) to image \([^\)]+\)\n'))
        start_re.append(re.compile(r'Reading Super Block\n'))
        start_re.append(re.compile(r'Calculating bitmap... Please wait... [^\n]+\n[^\n]+\n[^\n]+\n'))
        start_re.append(re.compile(r'File system:\s+EXTFS\n'))
        start_re.append(re.compile(r'Device size:\s+[\d.]+\s+GB\n'))
        start_re.append(re.compile(r'Space in use:\s+[\d.]+\s+GB\n'))
        start_re.append(re.compile(r'Free Space:\s+[\d.]+\s+MB\n'))
        start_re.append(re.compile(r'Block size:\s+\d+\s+Byte\n'))
        start_re.append(re.compile(r'Used block :\s+\d+\n'))

        progress_re = re.compile(r'\r\s+\rElapsed: (\d\d:\d\d:\d\d), Remaining: (\d\d:\d\d:\d\d), Completed:\s+(\d+.\d*)%,\s+([^\/]+)/min,')

        while read_set:
            try:
                rlist, wlist, xlist = select.select(read_set, write_set, [])
            except select.error, e:
                if e.args[0] == errno.EINTR:
                    continue
                raise
            
            if partclone.stdout in rlist:
                data = os.read(partclone.stdout.fileno(), 1024)
                if data == "":
                    read_set.remove(partclone.stdout)
                    pass
                else:
                    # Ignore the stdout
                    pass
                pass
            
            if partclone.stderr in rlist:
                data = os.read(partclone.stderr.fileno(), 1024)
                if data == "":
                    partclone.stderr.close()
                    read_set.remove(partclone.stderr)
                    pass
                else:
                    partclone_error = partclone_error + data
                    if len(start_re) > 0:
                        while len(start_re) > 0:
                            m = start_re[0].match(partclone_error)
                            if not m:
                                break
                            start_re = start_re[1:]
                            partclone_error = partclone_error[len(m.group(0)):]
                            pass
                        if len(start_re) == 0:
                            print "021 Start imaging"
                            sys.stdout.flush()
                            pass
                        pass
                    else:
                        while True:
                            m = progress_re.search(partclone_error)
                            if not m:
                                break
                            partclone_error = partclone_error[len(m.group(0)):]
                            elapsed = m.group(1)
                            remaining = m.group(2)
                            completed = string.atof(m.group(3))
                            print "0%2d elapsed: %s remaining: %s" % (round(22 + 67 * completed / 100), elapsed, remaining)
                            sys.stdout.flush()
                            pass
                        pass
                    pass
                pass
            pass

        print "089 Imaging complete"
        print "090 Resize file system to normal"
        sys.stdout.flush()
        resize2fs = subprocess.Popen("/sbin/resize2fs %s1" % self.device_name, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        resize2fs.communicate()
        print "100 Complete"
        sys.stdout.flush()
        pass


    def unmount_disk(self):
        if not self.mounted:
            return
        for i in range(0, 30):
            retcode = subprocess.call("sync", shell=True)
            time.sleep(0.5)
            retcode = subprocess.call("umount %s" % self.mount_dir, shell=True)
            if retcode == 0:
                self.mounted = False
                return
            pass
        raise unmount_failed

    def force_unmount_disk(self):
        retcode = subprocess.call("sync", shell=True)
        time.sleep(0.5)
        retcode = subprocess.call("umount %s1" % self.device_name, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        time.sleep(0.5)
        retcode = subprocess.call("umount %s2" % self.device_name, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        time.sleep(0.5)
        retcode = subprocess.call("umount %s3" % self.device_name, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        time.sleep(0.5)
        retcode = subprocess.call("umount %s4" % self.device_name, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        time.sleep(0.5)
        self.mounted = False
        return


    def has_wce_release(self):
        part1 = self.device_name + "1"
        installed = False
        for partition in self.partitions:
            if partition.partition_name == part1 and partition.partition_type == '83':
                print "# %s Partition %s has the linux partition type" % (self.device_name, partition.partition_name)
                # The parition 
                try:
                    self.mount_disk()
                    if os.path.exists(self.wce_release_file):
                        installed = True
                        pass
                    pass
                except:
                    traceback.print_exc(sys.stdout)
                    pass

                try:
                    self.unmount_disk()
                    time.sleep(2)
                except:
                    traceback.print_exc(sys.stdout)
                    pass
                break
            pass
        return installed


    def restore_disk_image_backend(self, partclone_image_file):
        ext = ""
        try:
            ext = os.path.splitext(partclone_image_file)[1]
        except:
            pass
        if ext == ".7z":
            decomp = "7z e -so"
        elif ext == ".gz":
            decomp = "gunzip -c"
        elif ext == ".xz":
            decomp = "unxz -c"
        elif ext == ".partclone":
            # aka no compression
            decomp = "cat"
        elif ext == ".lzo":
            decomp = "lzop -dc"
        else:
            decomp = "gunzip -c"
            pass

        if decomp == "cat":
            partclone = subprocess.Popen("partclone.ext4 -B -r -s %s -o %s1" % (partclone_image_file, self.device_name), shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        else:
            partclone = subprocess.Popen("%s '%s' | partclone.ext4 -B -r -s - -o %s1" % (decomp, partclone_image_file, self.device_name), shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            pass

        read_set = [partclone.stdout, partclone.stderr]
        write_set = []

        partclone_output = ""
        partclone_error = ""

        start_re = []
        start_re.append(re.compile(r'Partclone [^ ]+ '))
        start_re.append(re.compile(r'Starting to restore image \([^\)]+\) to device \(/dev/\w+\)'))
        start_re.append(re.compile(r'Calculating bitmap... Please wait... done!'))
        start_re.append(re.compile(r'File system:\s+EXTFS'))
        start_re.append(re.compile(r'Device size:\s+'))
        start_re.append(re.compile(r'Space in use:\s+'))
        start_re.append(re.compile(r'Free Space:\s+'))
        start_re.append(re.compile(r'Block size:\s+'))

        start_blanks_re = re.compile(r'\s{80}')
        progress_re = re.compile(r'\r\s+\rElapsed: (\d\d:\d\d:\d\d), Remaining: (\d\d:\d\d:\d\d), Completed:\s+(\d+.\d*)%,\s+([^\/]+)/min,')

        while read_set:
            try:
                rlist, wlist, xlist = select.select(read_set, write_set, [])
            except select.error, e:
                if e.args[0] == errno.EINTR:
                    continue
                raise
            
            if partclone.stdout in rlist:
                data = os.read(partclone.stdout.fileno(), 1024)
                if data == "":
                    read_set.remove(partclone.stdout)
                    pass
                else:
                    # Ignore the stdout
                    pass
                pass
            
            if partclone.stderr in rlist:
                data = os.read(partclone.stderr.fileno(), 1024)
                if data == "":
                    partclone.stderr.close()
                    read_set.remove(partclone.stderr)
                    pass
                else:
                    partclone_error = partclone_error + data
                    if len(start_re) > 0:
                        while len(start_re) > 0:
                            if start_blanks_re.search(partclone_error) is not None:
                                start_re = []
                                break
                            m = start_re[0].search(partclone_error)
                            if not m:
                                break
                            start_re = start_re[1:]
                            partclone_error = partclone_error[len(m.group(0)):]

                            if progress_re.search(partclone_error) is not None:
                                start_re = []
                                break
                            pass

                        if len(start_re) == 0:
                            print "021 Start imaging"
                            sys.stdout.flush()
                            pass
                        pass
                    else:
                        while True:
                            m = progress_re.search(partclone_error)
                            if not m:
                                break
                            partclone_error = partclone_error[len(m.group(0)):]
                            elapsed = m.group(1)
                            remaining = m.group(2)
                            completed = string.atof(m.group(3))
                            print "0%2d elapsed: %s remaining: %s" % (round(22 + 48 * completed / 100), elapsed, remaining)
                            sys.stdout.flush()
                            pass
                        pass
                    pass
                pass
            pass

        while partclone.poll() == None:
            time.sleep(0.5)
            pass

        if partclone.returncode != 0:
            print "999 restore image failed %s" % partclone_error
            return partclone.returncode

        print "071 File system check (e2fsck)"
        sys.stdout.flush()
        e2fsck = subprocess.Popen("/sbin/e2fsck -f -y %s1 -C 2" % (self.device_name), shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        e2fsck.communicate()
        if e2fsck.returncode != 0:
            print "999 file system check failed."
            return e2fsck.returncode
        print "080 Expanding file system (resize2fs)"
        sys.stdout.flush()
        resize2fs = subprocess.Popen("resize2fs -p %s1" % (self.device_name), shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        resize2fs.communicate()
        if resize2fs.returncode != 0:
            print "999 file system resize failed (resize2fs)"
            return resize2fs.returncode
        print "089 Expanding file system complete"
        sys.stdout.flush()
        return 0


    def get_byte_size(self):
        if self.byte_size:
            return self.byte_size

        fdisk = subprocess.Popen(["fdisk", "-l", "-u", self.device_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = fdisk.communicate()

        for line in out.split("\n"):
            if line == "":
                break
            m = disk1_re.match(line)
            if m:
                self.byte_size = string.atoi(m.group(1))
                print "# %s disk byte size %s = %d" % (self.device_name, m.group(1), self.byte_size)
                break
                pass
            pass
        return self.byte_size


    def usb_installer_start_parted(self):
        byte_size = self.get_byte_size()
        sectors = byte_size / 512
        part1_sectors = (750 * 1024 * 1024) / 512
        part1_start = 2048
        if part1_sectors + part1_start > (sectors / 2):
            part1_sectors = (sectors / 2) - part1_start
            pass
        part1_end = part1_start + part1_sectors - 1
        part2_start = part1_start + part1_sectors
        part2_end = sectors - 1 
        print "# %s byte size %d sectors %d part1_sectors %d" % (self.device_name, byte_size, sectors, part1_sectors)

        args = ["parted", "-s", self.device_name, "unit", "s", "mklabel", "msdos", "mkpart", "primary", "fat32", "%d" % part1_start, "%d" % part1_end, "mkpart", "primary", "ext2", "%d" % part2_start, "%d" % part2_end, "set", "1", "boot", "on" ]
        print "# %s %s" % (self.device_name, ' '.join(args))
        return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def usb_installer_refresh_partition(self):
        # Disk to look at
        fdisk = subprocess.Popen(["fdisk", "-l", "-u", self.device_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = fdisk.communicate()
        if len(err) > 0:
            print "999 " + err
            return

        looking_for_partition = False
        self.partitions = []

        for line in out.split("\n"):
            if looking_for_partition:
                m = part_re.match(line)
                if m:
                    part = partition()
                    part.device_name = m.group(1)
                    part.partition_type = m.group(2)
                    self.partitions.append(part)
                    pass
                pass
            else:
                if line == "":
                    looking_for_partition = True
                    continue
                pass
            pass
        pass


    def install_mbr(self):
        print "Install MBR to disk %s" % self.device_name
        mbr = subprocess.Popen(["/sbin/install-mbr", "-f", "-r", self.device_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = mbr.communicate()
        print "install-mbr out %s" % out
        print "install-mbr err %s" % err
        pass


    def remove_mount_dir(self):
        if os.path.exists(self.mount_dir) and os.path.isdir(self.mount_dir):
            os.rmdir(self.mount_dir)
            pass
        pass

    pass


class optical_drive:
    def __init__(self):
        self.device_name = None
        self.features = []
        self.model_name = ""
        self.vendor = ""
        pass

    def get_feature_string(self, sep):
        self.features.sort()
        cd = []
        dvd = []
        rest = []
        for feature in self.features:
            if feature[0:2] == "CD":
                if len(feature[2:]) > 0:
                    cd.append(feature[2:])
                    pass
                else:
                    cd.append("CD")
                    pass
                pass
            elif feature[0:3] == "DVD":
                if len(feature[3:]) > 0:
                    dvd.append(feature[3:])
                    pass
                else:
                    dvd.append("DVD")
                    pass
                pass
            else:
                rest.append(feature)
                pass
            pass
        features = []
        if len(cd) > 0:
            features.append(" ".join(cd))
            pass
        if len(dvd) > 0:
            features.append(" ".join(dvd))
            pass
        return ", ".join(features + rest)

    pass


def chroot_and_exec(mount_dir, things_to_do, root_partition_uuid, grub_cfg_patch):
    print "# %s chroot and execute" % mount_dir
    try:
        subprocess.call("mount --bind /dev/ %s/dev" % mount_dir, shell=True)
    except:
        pass

    install_script = open("%s/tmp/install-grub" % mount_dir, "w")
    install_script.write("""#!/bin/sh
echo "Here we go!"
mount -t proc none /proc
mount -t sysfs none /sys
mount -t devpts none /dev/pts
#
""")

    install_script.write(things_to_do)

    install_script.write('''#
chmod +rw /boot/grub/grub.cfg
export GRUB_DEVICE_UUID="%s"
export GRUB_DISABLE_OS_PROBER=true
export GRUB_DISABLE_LINUX_UUID=false
grub-mkconfig -o /boot/grub/grub.cfg
''' % root_partition_uuid)

    if grub_cfg_patch:
        install_script.write(grub_cfg_patch)
        pass

    install_script.write('''#
chmod 444 /boot/grub/grub.cfg
umount /proc || umount -lf /proc
umount /sys
umount /dev/pts
''')

    install_script.close()
    
    subprocess.call("chmod +x %s/tmp/install-grub" % mount_dir, shell=True)
    chroot = subprocess.Popen(["/usr/sbin/chroot", "%s" % mount_dir, "/bin/sh", "/tmp/install-grub"], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    (out, err) = chroot.communicate()
    if chroot.returncode == 0:
        print "# grub installation complete."
    else:
        print out
        print err
        pass
    subprocess.call("umount %s/dev" % mount_dir, shell=True)
    pass


# disk_re = re.compile(r"([^:]+):([^:]*):([^:]*):([^:]*):([^:]*):([^:]*):([^ ]*) ([^;]*);")
# part_re = re.compile(r"([^:]+):([^:]*):([^:]*):([^:]*):([^:]*):([^:]*):([^;]*);")


disk1_re = re.compile(r"Disk /dev/[^:]+:\s+\d+\.\d*\s+[KMG]B, (\d+) bytes")
disk2_re = re.compile(r"\d+ heads, \d+ sectors/track, \d+ cylinders, total (\d+) sectors")
disk3_re = re.compile(r"Units = sectors of \d+ * \d+ = (\d+) bytes")

part_re = re.compile(r"([^\s]+)\s+\*{0,1}\s+\d+\s+\d+\s+\d+\s+([\dA-Fa-f]+)\s+")


class bad_size(Exception):
    pass


# Memory size in MB
def get_memory_size():
    meminfo = open("/proc/meminfo")
    s = string.atoi(re.findall("MemTotal:\s+ (\d+) kB\n", meminfo.readline())[0]) / 1024
    meminfo.close()
    return s

re_smbios_present = re.compile(r'\s*SMBIOS \d+\.\d+ present.')
re_memory_module_information = re.compile(r'Memory Module Information')
re_socket_designation = re.compile(r'\s*Socket Designation: ([\w\d]+)')
re_enabled_size = re.compile(r'\s*Enabled Size: (\d+) MB')
re_error_status = re.compile(r'\sError Status: (\w+)')

def get_ram_info():
    dmidecode = subprocess.Popen('dmidecode -t 6', shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    (out, err) = dmidecode.communicate()
    # To gurantee the last line flushes out
    out = out + '\n'
    rams = []
    parse_state = 0
    for line in out.split('\n'):
        if parse_state == 0:
            m = re_smbios_present.match(line)
            if m:
                parse_state = 1
                pass
            pass
        elif parse_state == 1:
            m = re_memory_module_information.match(line)
            if m:
                parse_state = 2
                socket_designation = ""
                enabled_size = 0
                memory_status = True
                pass
            pass
        elif parse_state == 2:
            if len(line.strip()) == 0:
                rams.append( (socket_designation, enabled_size, memory_status) )
                parse_state = 1
                continue

            m = re_socket_designation.match(line)
            if m:
                socket_designation = m.group(1)
                pass

            m = re_enabled_size.match(line)
            if m:
                enabled_size = string.atoi(m.group(1))
                pass

            m = re_error_status.match(line)
            if m:
                memory_status = m.group(1).upper() == "OK"
                pass
            pass
        pass
    return rams

# Get ram type
re_memory_type = re.compile(r'\sType: (\w+)')
re_memory_device = re.compile(r'Memory Device')
re_physical_memory = re.compile(r'Physical Memory Array')

def get_ram_type():
    memory_type = None
    dmidecode = subprocess.Popen('dmidecode -t 17', shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    (out, err) = dmidecode.communicate()
    out = out + '\n'
    parse_state = 0
    for line in out.split('\n'):
        if parse_state == 0:
            m = re_smbios_present.match(line)
            if m:
                parse_state = 1
                pass
            pass
        elif parse_state == 1:
            m = re_memory_device.match(line)
            if m:
                parse_state = 2
                pass
            pass
        elif parse_state == 2:
            if len(line.strip()) == 0:
                parse_state = 1
                continue

            m = re_memory_type.match(line)
            if m:
                memory_type = m.group(1)
                pass
            pass
        pass

    if memory_type:
        return memory_type

    dmidecode = subprocess.Popen('dmidecode -t 16', shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    (out, err) = dmidecode.communicate()
    out = out + '\n'
    parse_state = 0
    for line in out.split('\n'):
        if parse_state == 0:
            m = re_smbios_present.match(line)
            if m:
                parse_state = 1
                pass
            pass
        elif parse_state == 1:
            m = re_physical_memory.match(line)
            if m:
                parse_state = 2
                pass
            pass
        elif parse_state == 2:
            if len(line.strip()) == 0:
                parse_state = 1
                continue

            m = re_memory_type.match(line)
            if m:
                memory_type = m.group(1)
                pass
            pass
        pass

    return memory_type


# returns size in MB
def parse_parted_size(size_string):
    if size_string[-1] == "B":
        if size_string[-2] == "M":
            return (int)(string.atof(size_string[:-2]) + 0.5)
        elif size_string[-2] == "G":
            return (int)(string.atof(size_string[:-2]) * 1024 + 0.5)
        else:
            raise bad_size
        pass
    raise bad_size
    pass


#
def find_disk_device_files(devpath):
    result = []
    for letter in "abcdefghijklmnopqrstuvwxyz":
        device_file = devpath + letter
        if os.path.exists(device_file):
            result.append(device_file)
            pass
        pass
    return result


def find_optical_device_files(devpath):
    result = []
    for letter in "0123456789":
        device_file = devpath + letter
        if os.path.exists(device_file):
            result.append(device_file)
        else:
            break
        pass
    return result


def disk_is_a_real_disk(disk_name):
    # I'm going to be optimistic here since the user can pick a disk
    result = True
    try:
        udevadm = subprocess.Popen("udevadm info --query=property --name=%s" % disk_name, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (out, err) = udevadm.communicate()
        is_ata_or_scsi = False
        is_disk = False
        for line in out.split("\n"):
            if line == "ID_BUS=ata":
                is_ata_or_scsi = True
            elif line == "ID_BUS=scsi":
                is_ata_or_scsi = True
                pass
            elif line == "ID_TYPE=disk":
                is_disk = True
                pass
            if is_ata_or_scsi and is_disk:
                return True
            pass
    except:
        pass
    return result


# This one gets the disks on IDE / SATA only
def get_disks(list_mounted_disks, verbose):
    global mounted_devices, mounted_partitions

    disks = []

    # Known mounted disks. 
    # These cannot be the target
    mount = subprocess.Popen(["mount"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (mount_out, muont_err) = mount.communicate()
    mount_re = re.compile(r"(/dev/[a-z]+)([0-9]*) on ([a-z0-9/]+) type ([a-z0-9]+) (.*)")
    mounted_devices = {}
    mounted_partitions = {}
    usb_disks = []
    for line in mount_out.split('\n'):
        m = mount_re.match(line)
        if m:
            device_name = m.group(1)
            if mounted_devices.has_key(device_name):
                mounted_devices[device_name] = mounted_devices[device_name] + ", " + m.group(3)
            else:
                mounted_devices[device_name] = m.group(3)
                pass

            partition_name = m.group(1) + m.group(2)
            mounted_partitions[partition_name] = m.group(3)
            pass
        pass

    # Gather up the possible disks
    possible_disks = find_disk_device_files("/dev/hd") + find_disk_device_files("/dev/sd")
    if verbose:
        print "# Possible disks = %s" % str(possible_disks)
        pass
    
    for disk_name in possible_disks:
        # Let's out right skip the mounted disk
        if mounted_devices.has_key(disk_name) and (not list_mounted_disks):
            if verbose:
                print "Mounted disk %s is not included in the candidate." % disk_name
                pass
            continue

        # Now, I do double check that this is really a disk
        is_ata_or_scsi = False
        is_disk = False
        is_usb = False
        disk_model = None
        disk_serial = None

        try:
            udevadm = subprocess.Popen("udevadm info --query=property --name=%s" % disk_name, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            (out, err) = udevadm.communicate()
            is_ata_or_scsi = False
            is_disk = False
            for line in out.split("\n"):
                try:
                    elems = line.split('=')
                    tag = string.strip(elems[0])
                    value = string.strip(elems[1])
                    if tag == "ID_BUS":
                        if value.lower() == "ata" or value.lower() == "scsi":
                            is_ata_or_scsi = True
                            pass
                        elif value.lower() == "usb":
                            is_usb = True
                            pass
                        pass
                    elif tag == "ID_TYPE":
                        if value.lower() == "disk":
                            is_disk = True
                            pass
                        pass
                    elif tag == "ID_MODEL":
                        disk_model = value
                        pass
                    elif tag == "ID_SERIAL":
                        disk_serial = value
                        pass
                    pass
                except:
                    pass
                pass
            pass
        except:
            traceback.print_exc(sys.stdout)
            pass

        if not is_disk:
            continue

        # Disk to look at
        current_disk = None
        fdisk = subprocess.Popen(["fdisk", "-l", "-u", disk_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = fdisk.communicate()

        looking_for_partition = False

        for line in out.split("\n"):
            if looking_for_partition and current_disk:
                m = part_re.match(line)
                if m:
                    if current_disk:
                        part = partition()
                        part.partition_name = m.group(1)
                        part.partition_type = m.group(2)
                        current_disk.partitions.append(part)
                        pass
                    pass
                pass
            else:
                if line == "":
                    looking_for_partition = True
                    continue
                m = disk1_re.match(line)
                if m:
                    if verbose:
                        print "# Found a disk"
                        pass
                    current_disk = disk()
                    current_disk.device_name = disk_name
                    current_disk.mounted = mounted_devices.has_key(current_disk.device_name)
                    current_disk.byte_size = string.atoi(m.group(1))
                    current_disk.size = current_disk.byte_size / 1000000
                    current_disk.sectors = string.atoi(m.group(1)) / 512
                    pass
                pass
            pass

        if current_disk:
            current_disk.is_ata_or_scsi = is_ata_or_scsi
            current_disk.is_usb = is_usb
            current_disk.is_disk = is_disk
            current_disk.model_name = disk_model
            current_disk.serial_no = disk_serial

            if is_ata_or_scsi:
                disks.append(current_disk)
            elif is_usb:
                usb_disks.append(current_disk)
                pass
            pass
        else:
            if verbose:
                print "# Did not find the disk %s" % disk_name
                pass
            pass
        pass

    return disks, usb_disks


def detect_optical_drives():
    opticals = []

    # Gather up the possible devices
    possible_opticals = find_optical_device_files("/dev/sr")
    
    for optical in possible_opticals:
        current_optical = None
        features = []
        is_cd = False
        vendor = ""
        model_name = ""
        try:
            udevadm = subprocess.Popen("udevadm info --query=property --name=%s" % optical, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            (out, err) = udevadm.communicate()
            for line in out.split("\n"):
                elems = line.split('=')
                tag = string.strip(elems[0])
                value = string.strip(elems[1])
                if tag == "ID_TYPE":
                    if value.lower() == "cd":
                        current_optical = optical_drive()
                        pass
                    pass
                elif tag == "ID_CDROM":
                    if value == "1":
                        is_cd = True
                        pass
                    pass
                elif tag[0:9] == "ID_CDROM_":
                    if value == "1":
                        feature = tag[9:].replace('_', '-')
                        if feature == "DVD-PLUS-R":
                            features.append("DVD+R")
                        elif feature == "DVD-PLUS-RW":
                            features.append("DVD+RW")
                        elif feature == "DVD-PLUS-R-DL":
                            features.append("DVD+R(DL)")
                        else:
                            features.append(feature)
                            pass
                        pass
                    pass
                elif tag == "ID_VENDOR":
                    vendor = value
                elif tag == "ID_MODEL":
                    model_name = value
                    pass
                pass
            pass
        except:
            pass

        if is_cd and (current_optical != None):
            current_optical.features = features
            current_optical.vendor = vendor
            current_optical.model_name = model_name
            opticals.append(current_optical)
            pass
        pass
        
    return opticals




def mount_usb_disks(usb_disks):
    global mounted_devices, mounted_partitions, wce_disk_image_path
    index = 1
    for disk in usb_disks:
        for part in disk.partitions:
            mounted = False
            if mounted_partitions.has_key(part.partition_name):
                mounted = True
            else:
                if part.partition_type == '83':
                    mount_point = "/mnt/usb%02d" % index
                    index = index + 1
                    if not os.path.exists(mount_point):
                        retcode = subprocess.call("mkdir %s" % mount_point, shell=True)
                    else:
                        retcode = 0
                        pass
                    if retcode == 0:
                        retcode = subprocess.call("mount %s %s" % (part.partition_name, mount_point), shell=True)
                        pass
                    if retcode == 0:
                        mounted = True
                        mounted_partitions[part.partition_name] = mount_point
                        pass
                    pass
                pass
            if mounted:
                wce_disk_image_path.append(os.path.join(mounted_partitions[part.partition_name], "wce-disk-images"))
                pass
            pass
        pass
    pass


def get_live_disk_images():
    global wce_disk_image_path
    images = []
    for image_path in wce_disk_image_path:
        try:
            for image in os.listdir(image_path):
                path = os.path.join(image_path, image)
                try:
                    if os.path.isfile(path):
                        images.append(path)
                        pass
                    pass
                except:
                    pass
                pass
            pass
        except:
            pass
        pass
    return images


def get_net_disk_images():
    images = []
    urls = []
    urls = urls + ["http://wceinstall/wce-disk-images.txt",
                   "http://wcesrv/wce-disk-images.txt"]

    for url in urls:
        try:
            wget = subprocess.Popen("wget -q -O - -T 2 --dns-timeout=2 %s" % url, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            (out, err) = wget.communicate()
            if wget.returncode == 0:
                for line in out.split('\n'):
                    transport_scheme = get_transport_scheme(line)
                    # Only accept ftp/http
                    if transport_scheme and (transport_scheme == "ftp" or transport_scheme == "http"):
                        images.append(line)
                        pass
                    pass
                pass
            pass
        except Exception, e:
            print url
            print str(e)
            pass
        if len(images) > 0:
            break
        pass
    return images


def choose_disk_image(prompt, images):
    choosing = True

    if len(images) == 1:
        return images[0]

    while choosing:
        print ""
        print prompt
        index = 1
        for image in images:
            if index == 1:
                print "  %2d (default) : %s" % (index, image)
            else:
                print "  %2d           : %s" % (index, image)
                pass
            index = index + 1
            pass
        print "Please choose a disk image file by number (default=1): "
        selection = None
        for t in range(10, 0, -1):
            i, o, e = select.select( [sys.stdin], [], [], 1)
            if i:
                selection = sys.stdin.readline().strip()
                break
            sys.stdout.write("\r %2d " % t)
            sys.stdout.flush()
            pass

        if (selection == None) or len(selection) == 0:
            break

        try:
            return images[string.atoi(selection)-1]
        except Exception, e:
            print e
            choosing = False
            break
        pass
    return images[0]
    pass


def detect_ethernet():
    out = get_lspci_nm_output()

    blacklisted_cards = []
    for line in out.split('\n'):
        m = lspci_nm_re.match(line)
        if m:
            if m.group(2) == '0200':
                vendor_id = m.group(3).lower()
                device_id = m.group(4).lower()
                
                try:
                    if ethernet_device_blacklist[vendor_id][device_id]:
                        blacklisted_cards.append(get_lspci_device_desc(m.group(1)))
                        pass
                    pass
                except KeyError:
                    pass
                pass
            pass
        pass

    ethernet_detected = False
    ip = subprocess.Popen(["ip", "addr", "show", "scope", "link"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = ip.communicate()
    try:
        mac_addr = re.findall("link/ether\s+(..):(..):(..):(..):(..):(..)", out)[0]
        if len(mac_addr[3]) > 0:
            ethernet_detected = True
            pass
    except:
        pass

    eth_entry_re = re.compile(r"\d+: (eth\d+):")
    eth_devices = []
    for line in out.split('\n'):
        m = eth_entry_re.match(line.strip())
        if m:
            eth_devices.append(m.group(1))
            pass
        pass

    return (ethernet_detected, blacklisted_cards, eth_devices)


def detect_sound_device():
    detected = False
    try:
        for snd_dev in os.listdir("/dev/snd"):
            if snd_dev[0:3] == 'pcm':
                detected = True
                break
            pass
        pass
    except:
        pass
    return detected


def try_hook(remote_hook_name, do_exec=True):
    # If hook does not exist, just bail out without complaint
    if remote_hook_name == None:
        return

    urls = []
    router_ip_address = get_router_ip_address()
    if router_ip_address:
        urls.append("http://%s/%s.py" % (router_ip_address, remote_hook_name))
        urls.append("http://%s/%s.sh" % (router_ip_address, remote_hook_name))
        pass

    for url in urls:
        print "Trying %s..." % url
        try:
            wget = subprocess.Popen("wget -q -O - -T 2 --dns-timeout=2 %s" % url, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            (out, err) = wget.communicate()
            if wget.returncode == 0:
                print "Running %s..." % url
                basename = os.path.basename(url)
                tmpfilepath = "/var/tmp/%s" % basename
                tmpfile = open(tmpfilepath, "w")
                tmpfile.write(out)
                tmpfile.close()
                os.chmod(tmpfilepath, 0755)
                run_hook_file(tmpfilepath, do_exec=do_exec)
                pass
            pass
        except Exception, e:
            print "Exception while trying to run a hook."
            traceback.print_exc(sys.stdout)
            pass
        pass
    return


def run_hook_file(hook_file, do_exec=True):
    file_ext = os.path.splitext(hook_file)[1]
    if do_exec:
        if file_ext == ".py":
            os.execvp("python", ["python", hook_file])
        elif file_ext == ".sh":
            os.execvp("sh", ["sh", hook_file])
            pass
        pass
    else:
        sub = None
        if file_ext == ".py":
            sub = subprocess.Popen("python %s" % hook_file, shell=True)
        elif file_ext == ".sh":
            sub = subprocess.Popen(hook_file, shell=True)
            pass
        if sub:
            sub.communicate()
            pass
        pass
    pass



# force_installation: True - install new contents even if it already has WCE release
def main(force_installation=False, generate_hostname=False, disk_image_file=None,
         memory_size=None, include_usb_disks=False, grub_cfg_patch=None,
         remote_hook_name=None, hook_file=None, addition_dir=None, addition_tar=None):
    global mounted_devices, disk_images, dlg

    (active_ethernet, bad_cards, eth_devices) = detect_ethernet()
    if not active_ethernet:
        print """
************************************************************
*        Ethernet Interface is not detected.               *
*  Before shipping, please make sure to add a network NIC. *
************************************************************
"""
        pass

    print "At any point, if you want to interrupt the installation, hit Control-C"

    if disk_image_file == None:
        disk_images = get_net_disk_images() + get_live_disk_images()
        if len(disk_images) <= 0:
            dlg.msgbox("""There is no disk image on this media or network.
It means either the network is not connected, the installation 
server is not working, or the installation server does not have
the WCE Ubuntu files in the HTTP server document directory.
Talk to the admin of installation server if you are installing.""",
                       width=70, height=10)
            raise Exception("No disk images")
        pass

    disks, usb_disks = get_disks(False, True)
    if include_usb_disks:
        disks = disks + usb_disks
        pass
    targets = []
    index = 1
    n_free_disk = 0
    first_target = None
    skipped = 0
    print "Disks so far - ata/sata %d, usb %d" % (len(disks), len(usb_disks))
    print "Detected disks"
    for d in disks:
        if mounted_devices.has_key(d.device_name):
            print "%3d : %s  - mounted %s" % (index, d.device_name, mounted_devices[d.device_name])
        else:
            print "%3d : %s" % (index, d.device_name)
            n_free_disk = n_free_disk + 1
            if n_free_disk == 1:
                first_target = index - 1
                pass
            pass
        index += 1
        pass

    if n_free_disk > 1:
        print " NOTE: Mounted disks cannot be the installation target."

        selection = getpass._raw_input("  space separated: ")
        for which in selection.split(" "):
            try:
                index = string.atoi(which) - 1
                if not disks[index].mounted:
                    targets.append(disks[index])
                else:
                    print "%s is mounted and cannot be the target." % disks[index].device_name
                    pass
            except Exception, e:
                print "Bad input for picking disk"
                raise e
                pass
            pass
        pass
    else:
        if first_target != None:
            targets.append(disks[first_target])
            pass
        pass

    if memory_size:
        memsize = memory_size
    else:
        memsize = get_memory_size()
        pass

    if len(targets) > 0:
        for target in targets:
            if disk_image_file:
                target.partclone_image = disk_image_file
            else:
                target.partclone_image = choose_disk_image("Please choose a disk image for %s." % target.device_name, disk_images)
                pass
            pass

        if len(targets) == 1:
            print ""
            print "Installing to %s with %s" % (targets[0].device_name, targets[0].partclone_image)
            print "Hit Control-C to stop the installation"
            count = 5
            while count > 0:
                sys.stdout.write("\r     \r %2d " % count)
                sys.stdout.flush()
                time.sleep(1)
                count = count - 1
                pass
            print ""
            pass

        for target in targets:
            if generate_hostname:
                new_id = uuidgen()
                newhostname = "wce%s" % new_id[1:8]
            else:
                newhostname = None
                pass

            if force_installation or (not target.has_wce_release()):
                target.install_ubuntu(memsize, newhostname, grub_cfg_patch)
                target.post_install(remote_hook_name, hook_file, addition_dir, addition_tar)
                target.unmount_disk()
            else:
                print ""
                print "Installation to %s is skipped since it appears the disk already has a WCE Ubuntu." % target.device_name
                print ""
                skipped = skipped+1
                pass
            pass
        pass
    else:
        print "**************************************************"
        print " Please make sure a disk exists, and not mounted."
        print "**************************************************"
        pass

    if skipped > 0:
        print "If you want to install to the skipped disk, use '--force-installation' option."
        pass
    pass


def parse_cpu_info_tag_value(line):
    try:
        elems = line.split(":")
        return string.strip(elems[0]), string.strip(elems[1])
    except:
        return None, None
    pass


def detect_cpu_type():
    max_processor = 0
    cpu_vendor = "other"
    model_name = ""
    cpu_cores = 1
    cpu_class = 1
    bogomips = 0
    cpu_speed = 0
    cpu_64 = False
    cpu_sse2 = False
    cpu_sse = False
    cpu_3dnow = False
    cpu_mmx = False

    for line in open("/proc/cpuinfo").readlines():
        tag, value = parse_cpu_info_tag_value(line)
        if tag == None:
            continue
        elif tag == "processor":
            processor = string.atoi(value)
            if max_processor < processor:
                max_processor = processor
                pass
            pass
        elif tag == 'vendor_id':
            if value == 'GenuineIntel':
                cpu_vendor = "Intel"
            elif value == 'AuthenticAMD':
                cpu_vendor = "AMD"
                pass
            pass
        elif tag == 'cpu MHz':
            cpu_speed = (int)(string.atof(value)+0.5)
            pass
        elif tag == 'model name':
            model_name = value
            pass
        elif tag == 'cpu cores':
            cpu_cores = string.atoi(value)
            pass
        elif tag == 'flags':
            
            for a_flag in value.split(' '):
                flag = a_flag.lower()
                if flag == "lm" or flag == "lahf_lm":
                    cpu_64 = True
                elif flag == "sse2":
                    cpu_sse2 = True
                elif flag == "sse":
                    cpu_sse = True
                elif flag == "3dnow":
                    cpu_3dnow = True
                elif flag == "mmx":
                    cpu_mmx = True
                    pass
                pass
            pass
        elif tag == 'bogomips':
            bogomips = value
            pass
        pass

    cpu_class = 1
    if cpu_cores >= 2:
        cpu_class = 5
    elif cpu_sse2 or (cpu_3dnow and cpu_sse):
        cpu_class = 4
    elif cpu_sse or (cpu_3dnow and cpu_mmx):
        cpu_class = 3
    elif cpu_mmx:
        cpu_class = 2
        pass

    # Patch up the CPU speed. cpuinfo seems to show the current CPU speed,
    # not the max speed
    scaling_max_freq = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq"
    if os.path.exists(scaling_max_freq):
        f = open(scaling_max_freq)
        speed = f.read()
        f.close()
        cpu_speed = string.atol(speed) / 1000
        pass

    return cpu_class, cpu_cores, max_processor + 1, cpu_vendor, model_name, bogomips, cpu_speed


def triage(output, live_system = False):
    global mounted_devices
    cpu_class, cpu_cores, n_processors, cpu_vendor, model_name, bogomips, cpu_speed = detect_cpu_type()
    # Try getting memory from dmidecode
    ram_type = get_ram_type()
    rams = get_ram_info()
    total_memory = 0
    for ram in rams:
        total_memory = total_memory + ram[1]
        pass
    # backup method
    if total_memory == 0:
        total_memory = get_memory_size()
        pass
    disks, usb_disks = get_disks(True, True)
    (n_nvidia, n_ati, n_vga, n_black_vga, blacklisted_videos) = detect_video_cards()
    (ethernet_detected, bad_ethernet_cards, eth_devices) = detect_ethernet()
    sound_dev = detect_sound_device()
    triage_result = True
    
    subprocess.call("clear", shell=True)
    print >> output, "CPU Level: P%d - %dMhz" % (cpu_class, cpu_speed)
    print >> output, "  %s" % (model_name)
    print >> output, "  Cores: %d cores, Bogomips: %s" % (cpu_cores, bogomips)

    if ram_type == None:
        ram_type = "Unknown"
        pass

    if total_memory < 200:
        print >> output, "RAM Type: %s  Size: %dMbytes -- INSTALL MORE MEMORY" % (ram_type, total_memory)
        triage_result = False
    else:
        print >> output, "RAM Type: %s  Size: %dMbytes" % (ram_type, total_memory)
        pass

    if len(rams) > 0:
        slots = "    "
        for ram in rams:
            slots = slots + "  %s: %d MB" % (ram[0], ram[1])
            pass
        print >> output, slots
        pass
        
    if len(disks) == 0:
        print >> output, "Hard Drive: NOT DETECTED -- INSTALL A DISK"
        triage_result = False
    else:
        print >> output, "Hard Drive:"
        good_disk = False
        for disk in disks:
            disk_msg = "     Device %s: size = %dGbytes  %s" % (disk.device_name, disk.size / 1000, disk.model_name)
            if (disk.size / 1000) >= 20:
                good_disk = True
                disk_msg += " - PASS"
                pass
            else:
                disk_msg += " - TOO SMALL"
                pass
            print >> output, disk_msg
            pass
        if not good_disk:
            triage_result = False
            pass
        pass

    optical_drives = detect_optical_drives()
    if len(optical_drives) == 0:
        print >> output, "Optical drive: ***** NO OPTICALS: INSTALL OPTICAL DRIVE *****"
        triage_result = False
    else:
        print >> output, "Optical drive:"
        index = 1
        for optical in optical_drives:
            print >> output, "    %d: %s %s" % (index, optical.vendor, optical.model_name)
            print >> output, "       %s" % (optical.get_feature_string(", "))
            index = index + 1
            pass
        pass

    if n_nvidia > 0:
        print >> output, "Video:     nVidia video card = %d" % n_nvidia
        pass
    if n_ati > 0:
        print >> output, "Video:     ATI video card = %d" % n_ati
        pass
    if n_vga > 0:
        print >> output, "Video:     Video card = %d" % n_vga
        pass

    if (n_nvidia + n_ati + n_vga) <= 0:
        triage_result = False
        if len(blacklisted_videos) > 0:
            print >> output, "Remove or disable following video(s) because known to not work"
            for video in blacklisted_videos:
                print >> output, "    " + video
                pass
            pass
        pass

    if not len(eth_devices) > 0:
        print >> output, "Ethernet card: NOT DETECTED -- INSTALL ETHERNET CARD"
        triage_result = False
        pass
    if len(bad_ethernet_cards) > 0:
        print >> output, "Remove or disable following cards because known to not work"
        for card in bad_ethernet_cards:
            print >> output, "    " + card
            pass
        pass

    if not sound_dev:
        print >> output, "Sound card: NOT DETECTED -- INSTALL SOUND CARD"
        triage_result = False
        pass
    
    return triage_result, disks, usb_disks


# Live triage for post installation triage
def live_triage(cmd):
    if os.getuid() != 0:
        subprocess.call("gksudo -- xterm -geometry 132x40 -e python %s --live-triage" % cmd["argv0"], shell=True)
        pass
    else:
        live_triage_step1(cmd)
        pass
    pass


def read_file(filepath):
    content = None
    try:
        f = open(filepath)
        content = f.read()
        f.close()
    except:
        pass
    return content
    

def compare_files(file1, file2):
    return read_file(file1) == read_file(file2)

# Called when I'm root
def live_triage_step1(cmd):
    try:
        import dialog
        live_triage_step2(cmd)
    except:
        # I need to install some packages from "wce"
        wce_path = os.path.dirname(cmd["argv0"])
        packages = []
        for maybe_package in os.listdir(wce_path):
            if os.path.splitext(maybe_package)[1] == ".deb":
                packages.append(os.path.join(wce_path, maybe_package))
                pass
            pass
        subprocess.call("dpkg -i %s" % " ".join(packages), shell=True)
        subprocess.call("python %s --live-triage-step-2" % cmd["argv0"], shell=True)
        pass
    pass


def live_triage_step2(cmd):
    global mounted_devices, mounted_partitions, wce_disk_image_path, dlg
    import dialog

    dialog_width = 100
    dialog_height = 32

    triage_output = open(triage_txt, "w")

    dlg = dialog.Dialog()
    dialog_rc = open(dialog_rc_filename, "w")
    dialog_rc.write(dialog_rc_failure_template)
    dialog_rc.close()
    failure_dlg = dialog.Dialog(DIALOGRC=dialog_rc_filename)

    has_network = None
    if is_network_connected():
        dlg.gauge_start("Thank you for triaging. Please fill the form.", title="Checking network")
        for i in range(0, 9):
            time.sleep(1)
            has_network = get_router_ip_address() != None
            if has_network:
                break
            pass
        dlg.gauge_update(100, "Thank you for triaging. Please fill the form.", update_text=1)
        time.sleep(1)
        dlg.gauge_stop()
        pass
            
    triage_result = True

    while True:
        # I do this extra work so that I can have a temp file.
        try:
            triage_result, disks, usb_disks = triage(triage_output, live_system=True)
        except:
            traceback.print_exc(triage_output)
            pass
        triage_output.flush()

        result_displayed = False

        btitle = "Triage Output"
        triage_dlg = dlg

        if not triage_result:
            btitle = "Triage Output - Failed"
            triage_dlg = failure_dlg
            pass
        dlg = triage_dlg
        triage_output.close()

        try:
            if (not has_network) or (not triage_result):
                triage_dlg.textbox(triage_txt, width=dialog_width, height=dialog_height, cr_wrap=1, backtitle=btitle)
                pass
            else:
                triage_output = open(triage_txt)
                report = triage_output.read()
                triage_output.close()
                triage_dlg.infobox(report, width=dialog_width, height=dialog_height, cr_wrap=1, backtitle=btitle)
                pass
            result_displayed = True
        except:
            triage_output = open(triage_txt, "a+")
            traceback.print_exc(triage_output)
            triage_output.close()
            pass        

        # See the disks contain WCE Ubuntu
        triage_output = open(triage_txt, "a+")
        if os.path.exists("/etc/wce-release"):
            print >> triage_output, "The machine has the WCE Ubuntu installed."
        else:
            print >> triage_output, "The machine does not have the WCE Ubuntu installed. -- FAIL"
            triage_result = False
            pass

        # Network working?
        has_network = get_router_ip_address() != None
        (active_ethernet, bad_cards, eth_devices) = detect_ethernet()

        while not has_network:
            triage_dlg.infobox("\nPlease connect to a router.\n", width=dialog_width, height=dialog_height/2, cr_wrap=1, backtitle=btitle)
            has_network = get_router_ip_address() != None
            if has_network:
                break
            time.sleep(5)
            pass

        print >> triage_output, "Live network is working."
        triage_output.close()
        triage_dlg.textbox(triage_txt, width=dialog_width, height=dialog_height, cr_wrap=1, backtitle=btitle)

        #
        # Checking optical
        #

        optical_result = True
        triage_output = open(triage_txt, "a+")
        wce_path = os.path.dirname(cmd["argv0"])
        live_path = os.path.join(wce_path, "..", "live")
        initrd_path = os.path.join(live_path, "initrd.img")
        vmlinuz_path = os.path.join(live_path, "vmlinuz")

        msg = '''*********************************************
    Checking CD. Step 1
    This may take some time.
*********************************************
'''
        triage_dlg.infobox(msg, width=dialog_width, height=dialog_height, cr_wrap=1, backtitle=btitle)

        try:
            subprocess.check_call("md5sum %s | cut -d ' ' -f 1 > /tmp/initrd.img.md5" % initrd_path, shell=True)
        except:
            print >> triage_output, "Reading %s on CD did not succeed. -- FAIL\n" % initrd_path
            optical_result = False
            traceback.print_exc(triage_output)
            pass

        if not compare_files("/tmp/initrd.img.md5", os.path.join(wce_path, "initrd.img.md5")):
            print >> triage_output, "Checksum %s on CD did not succeed. -- FAIL\n" % initrd_path
            optical_result = False
            pass

        msg = '''*********************************************
    Checking CD. Step 2
    This may take some time.
*********************************************
'''
        triage_dlg.infobox(msg, width=dialog_width, height=dialog_height, cr_wrap=1, backtitle=btitle)
        triage_output.flush()

        try:
            subprocess.check_call("md5sum %s | cut -d ' ' -f 1 > /tmp/vmlinuz.md5" % vmlinuz_path, shell=True)
        except:
            print >> triage_output, "Reading %s on CD did not succeed. -- FAIL" % vmlinuz_path
            optical_result = False
            traceback.print_exc(triage_output)
            pass
            if status != 0:
                pass
            pass

        if not compare_files("/tmp/vmlinuz.md5", os.path.join(wce_path, "vmlinuz.md5")):
            print >> triage_output, "Checksum %s on CD did not succeed. -- FAIL" % vmlinuz_path
            optical_result = False
            pass

        if optical_result:
            print >> triage_output, "Checking CD passed."
            pass
        else:
            triage_result = False
            pass

        if not triage_result:
            btitle = "Triage Output - Failed"
            triage_dlg = failure_dlg
            pass

        has_network = get_router_ip_address() != None
        if has_network:
            # If it's connected to a network.
            # it's probably hooked up to a random router.
            print >> triage_output, "Triage is complete. If it passes the triage, it's ready to ship.\n"
            triage_output.close()
            triage_dlg.textbox(triage_txt, width=dialog_width, height=dialog_height, cr_wrap=1, backtitle="Triage conclusion")
            pass
        else:
            # It's an island triage
            if triage_result:
                print >> triage_output, "Triage complete. Ready to install."
            else:
                print >> triage_output, "The machine did not pass the triage. Please fix it." 
                pass
            triage_output.close()
            triage_dlg.textbox(triage_txt, width=dialog_width, height=dialog_height, cr_wrap=1, backtitle=btitle)
            pass

        triage_dlg.msgbox("Please turn off the computer.")

        # Just fall through
        break
    pass


def detect_sensor_modules(modules_path):
    if modules_path:
        modules = open(modules_path)
        lines = modules.readlines()
        modules.close()
        its_there = False
        for line in lines:
            if line == '# LM-SENSORS\n':
                its_there = True
                break
            pass
        if its_there:
            return
        pass

    drivers = []
    sd = subprocess.Popen("cat /dev/null | sensors-detect", shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    (out, err) = sd.communicate()
    look_for_chip_driver = 0
    for line in out.split('\n'):
        if look_for_chip_driver == 0:
            if line == '#----cut here----':
                look_for_chip_driver = 1
                pass
            pass
        elif look_for_chip_driver == 1:
            if line == '# Chip drivers':
                look_for_chip_driver = 2
                pass
            pass
        elif look_for_chip_driver == 2:
            if line == '#----cut here----':
                look_for_chip_driver = 0
            else:
                drivers.append(line)
                pass
            pass
        pass

    if len(drivers) > 0:
        if modules_path:
            modules = open(modules_path, 'a+')
            modules.write("# LM-SENSORS\n%s\n#\n" % "\n".join(drivers))
            modules.close()
            pass

        for module in drivers:
            try:
                retcode = subprocess.call("modprobe %s" % module, shell=True)
            except:
                pass
            pass
        pass
    pass


def set_pwm(speed):
    p = "/sys/devices/platform"
    re_pwm = re.compile(r'^pwm[0-9]$')
    re_pwm_enable = re.compile(r'^pwm[0-9]_enable$')

    for node in os.listdir(p):
        pnode = os.path.join(p, node)
        nodes = []
        try:
            nodes = os.listdir(pnode)
        except:
            nodes = []
            pass
        for pdev in nodes:
            try:
                if re_pwm.match(pdev):
                    ppath = os.path.join(pnode, pdev)
                    pwm = open(ppath, "w")
                    pwm.write("%d" % speed)
                    pwm.close()
                    pass
                pass
            except:
                pass
            try:
                if re_pwm_enable.match(pdev):
                    ppath = os.path.join(pnode, pdev)
                    pwm = open(ppath, "w")
                    pwm.write("1")
                    pwm.close()
                    pass
                pass
            except:
                pass
            pass
        pass
    pass
        

def reboot():
    subprocess.call("reboot", shell=True)
    pass


def triage_install():
    global mounted_devices, mounted_partitions, wce_disk_image_path, dlg
    import dialog
    dlg = dialog.Dialog()
    dialog_rc = open(dialog_rc_filename, "w")
    dialog_rc.write(dialog_rc_failure_template)
    dialog_rc.close()
    failure_dlg = dialog.Dialog(DIALOGRC=dialog_rc_filename)

    wce_disk_image_path = ["/live/image/wce-disk-images"]

    # To save my sanity
    #detect_sensor_modules(None)
    #set_pwm(144)

    # dialog must work, or else dead.

    has_network = None
    if is_network_connected():
        dlg.gauge_start("Thank you for triaging. Please fill the form.", title="Checking network")
        for i in range(0, 9):
            dlg.gauge_update(1+i*10, "Thank you for triaging. Please fill the form.", update_text=1)
            time.sleep(1)
            has_network = get_router_ip_address() != None
            if has_network:
                break
            pass
        dlg.gauge_update(100, "Thank you for triaging. Please fill the form.", update_text=1)
        time.sleep(1)
        dlg.gauge_stop()
        pass
            
    triage_result = True

    while True:
        # I do this extra work so that I can have a temp file.
        triage_output = open(triage_txt, "w")
        triage_result, disks, usb_disks = triage(triage_output, live_system=False)
        triage_output.close()
        result_displayed = False

        btitle = "Triage Output"
        triage_dlg = dlg

        if not triage_result:
            btitle = "Triage Output - Failed"
            triage_dlg = failure_dlg
            pass
        dlg = triage_dlg

        try:
            if (not has_network) or (not triage_result):
                triage_dlg.textbox(triage_txt, width=76, height=20, cr_wrap=1, backtitle=btitle)
                pass
            else:
                triage_output = open(triage_txt)
                report = triage_output.read()
                triage_output.close()
                triage_dlg.infobox(report, width=76, height=20, cr_wrap=1, backtitle=btitle)
                time.sleep(5)
                pass
            result_displayed = True
        except Exception, e:
            traceback.print_exc(sys.stdout)
            pass

        # See the disks contain WCE Ubuntu
        installed_disks = []
        for d in disks:
            if not mounted_devices.has_key(d.device_name):
                if d.has_wce_release():
                    installed_disks.append(d)
                    pass
                pass
            pass

        if len(installed_disks) > 0:
            triage_output = open(triage_txt, "a+")
            print >> triage_output, "The machine has the WCE Ubuntu installed in %s." % installed_disks[0].device_name
            triage_output.close()

            # Ask whether or not to do the update-grub
            yesno = triage_dlg.yesno("The disk contains the WCE Ubuntu installed.\nDo you want to rerun the disk finalize? (recommended)", 7, 70)
            if yesno == 0:
                for target in installed_disks:
                    target.get_uuid_from_partitions()
                    if target.uuid1:
                        target.mount_disk()
                        target.finalize_disk(False, None)
                        target.unmount_disk()
                        pass
                    pass
                print "Disk finalized."
                pass

            # Looks like a disk is already installed.
            has_network = get_router_ip_address() != None
            (active_ethernet, bad_cards, eth_devices) = detect_ethernet()

            restore_interfaces = False
            try:
                os.rename("/etc/network/interfaces", "/etc/network/interfaces.original")
                restore_interfaces = True
            except:
                pass

            try:
                iface_file = open("/etc/network/interfaces", "w")
                iface_file.write(etc_network_interfaces)
                iface_file.close()

                if has_network:
                    # The startup tried to start the eth0
                    for eth_dev in eth_devices:
                        subprocess.call("ifdown %s" % eth_dev, shell=True)
                        pass
                    has_network = False
                    time.sleep(3)
                    pass

                while not has_network:
                    has_network = get_router_ip_address() != None
                    if has_network:
                        break
                    triage_dlg.msgbox("Please connect the NIC to a router/hub and press RETURN")
                    for eth_dev in eth_devices:
                        subprocess.call("ifup %s" % eth_dev, shell=True)
                        has_network = get_router_ip_address() != None
                        if has_network:
                            break
                        pass
                    pass
                pass
            finally:
                if restore_interfaces:
                    try:
                        os.unlink("/etc/network/interfaces")
                    except:
                        pass
                    os.rename("/etc/network/interfaces.original", "/etc/network/interfaces")
                    pass
                pass

            triage_output = open(triage_txt, "a+")
            print >> triage_output, "Network is working."
            triage_output.close()
            triage_dlg.textbox(triage_txt, width=76, height=20, cr_wrap=1, backtitle=btitle)
            pass

        has_network = get_router_ip_address() != None
        if has_network:
            triage_dlg.infobox("Contacting the installation server.")
            disk_images = get_net_disk_images()
            triage_output = open(triage_txt, "a+")
            print >> triage_output, "%d disk images found." % (len(disk_images))
            triage_output.close()
        else:
            disk_images = []
            pass



        if has_network and len(disk_images) == 0:
            # If it's connected to a network but no disk images, then
            # it's probably hooked up to a random router.
            triage_output = open(triage_txt, "a+")
            if len(installed_disks) == 0:
                print >> triage_output, "Triage is complete."
                pass
            else:
                print >> triage_output, "Triage is complete. If it passes the triage, it's ready to ship.\n"
                pass
            triage_output.close()
            triage_dlg.textbox(triage_txt, width=76, height=20, cr_wrap=1, backtitle="Triage conclusion")
            triage_dlg.msgbox("Please turn off the computer.")
            pass
        elif (not has_network) and len(disk_images) == 0:
            # It's an island triage
            triage_output = open(triage_txt, "a+")
            if triage_result:
                print >> triage_output, "Triage complete. Ready to install."
            else:
                print >> triage_output, "The machine did not pass the triage. Please fix it." 
                pass
            triage_output.close()
            triage_dlg.textbox(triage_txt, width=76, height=20, cr_wrap=1, backtitle=btitle)
            triage_dlg.msgbox("Please turn off the computer.")
            pass

        # If there is disk images, it's connected to a server
        # Proceed to installation.
	# Also, if there is a USB disk (USB stick), maybe, 
	# there is a installation image.
        if len(disk_images) > 0 or (len(usb_disks) > 0):
            break

        # If it's hooked up to a network, then I'm very done.
        if has_network:
            return

        # Just fall through to the installation
        break

    mount_usb_disks(usb_disks)

    print ""

    try_hook("pre-installation")
    try:
        main(force_installation=True, generate_hostname=True, remote_hook_name="post-installation")
        print ""
        print "**********************"
        print "Installation complete."
        print "**********************"
        print ""
        reboot()
        pass
    except (KeyboardInterrupt, SystemExit), e:
        print "Installation interrupted."
        raise e
        pass
    except Exception, e:
        print "Installation interrupted."
        print str(e)
        raise e
        pass
    print "If you want to restart the installation, type\nsudo python %s" % sys.argv[0]
    pass


# Remote disk imaging
def image_disk(args):
    global mounted_devices, mounted_partitions, dlg
    import dialog
    dlg = dialog.Dialog()

    stem_name = "wce"

    has_network = None
    if is_network_connected():
        router_ip_address = get_router_ip_address()
        if not router_ip_address:
            sys.exit(1)
            pass

        # Mount the NFS to /mnt/www
        if not os.path.exists("/mnt/www"):
            os.mkdir("/mnt/www")
            pass

        subprocess.call("mount -t nfs %s:/var/www /mnt/www" % router_ip_address, shell=True)

        if not os.path.exists("/mnt/www/wce-disk-images"):
            print "NFS mount did not mount /mnt/www/wce-disk-images"
            sys.exit(1)
        pass

    try:
        (active_ethernet, bad_cards, eth_devices) = detect_ethernet()
        if not active_ethernet:
            print """
************************************************************
*        Ethernet Interface is not detected.               *
************************************************************
"""
            pass


        disks, usb_disks = get_disks(False, True)
        disks = disks + usb_disks
        sources = []
        index = 1
        n_free_disk = 0
        first_source = None
        print "Detected disks"
        for d in disks:
            if mounted_devices.has_key(d.device_name):
                print "%3d : %s  - mounted %s" % (index, d.device_name, mounted_devices[d.device_name])
            else:
                print "%3d : %s" % (index, d.device_name)
                n_free_disk = n_free_disk + 1
                if n_free_disk == 1:
                    first_source = index - 1
                    pass
                pass
            index += 1
            pass

        if n_free_disk > 1:
            print " NOTE: Mounted disks cannot be the imaging source."

            selection = getpass._raw_input("  space separated: ")
            for which in selection.split(" "):
                try:
                    index = string.atoi(which) - 1
                    if not disks[index].mounted:
                        sources.append(disks[index])
                    else:
                        print "%s is mounted and cannot be the source." % disks[index].device_name
                        pass
                except Exception, e:
                    print "Bad input for picking disk"
                    raise e
                pass
            pass
        else:
            if first_source != None:
                sources.append(disks[first_source])
                pass
            pass


        if len(sources) > 0:
            for source in sources:
                source.image_disk(stem_name)
                pass
            pass
        else:
            print "**************************************************"
            print " Please make sure a disk exists, and not mounted."
            print "**************************************************"
            pass

        print ""
        print "**********************"
        print "  Imaging complete."
        print "**********************"
        print ""
        pass
    except (KeyboardInterrupt, SystemExit), e:
        print "Disk imaging interrupted."
        raise e
        pass
    except Exception, e:
        print "Disk imaging interrupted."
        print str(e)
        raise e
        pass
    pass



def install_iserver(args):
    global mounted_devices, mounted_partitions, wce_disk_image_path, dlg
    try:
        import dialog
        dlg = dialog.Dialog()
    except:
        dlg = None
        pass
    wce_disk_image_path = ["/live/image/wce-disk-images"]

    # Make sure dialog works
    # This also is a way to wait for the network to come up

    has_network = None
    while True:
        has_network = get_router_ip_address() != None
        # If no network, just wait for the machine to reboot.
        if (not has_network):
            print ""
            yes_no = getpass._raw_input("Reboot (i=Install)? ([Y]/n/i) ")
            if ((len(yes_no) == 0) or (yes_no[0].lower() == 'y')):
                reboot()
                sys.exit(0)
                pass
            if (len(yes_no) > 0):
                what = yes_no[0].lower()
                if what == 'i':
                    break
                pass
            pass
        else:
            break
        pass

    disks, usb_disks = get_disks(False, True)
    disks = disks
    if len(disks) == 0:
        print "Hard Drive: NOT DETECTED -- INSTALL A DISK"
        pass

    mount_usb_disks(usb_disks)
    print ""

    try_hook("iserver-pre-installation")
    try:
        main(force_installation=True, remote_hook_name="iserver-post-installation")
        print ""
        print "*********************************************"
        print "Installation of Installation server complete."
        print "*********************************************"
        print ""
        reboot()
        pass
    except (KeyboardInterrupt, SystemExit), e:
        print "Installation interrupted."
        raise e
        pass
    except Exception, e:
        print "Installation interrupted."
        print str(e)
        raise e
        pass
    print "If you want to restart the installation, type\nsudo python %s" % sys.argv[0]
    pass


def safe_get_arg(args, name, default_value):
    if args.has_key(name):
        return args[name]
    return default_value



def wait_for_disk_insertion():
    current_disks = find_disk_device_files("/dev/hd") + find_disk_device_files("/dev/sd")
    while True:
        time.sleep(2)
        new_disks = find_disk_device_files("/dev/hd") + find_disk_device_files("/dev/sd")
        if len(current_disks) < len(new_disks):
            break
        if len(current_disks) > len(new_disks):
            print "Disk disappeared"
            pass
        current_disks = new_disks
        pass
    pass


def batch_install(args):
    wait_for_disk = safe_get_arg(args, "wait-for-disk", False)

    while True:
        if wait_for_disk:
            print "Waiting for disk to appear."
            wait_for_disk_insertion()
            pass

        try:
            main(force_installation=safe_get_arg(args, "force-installation", False),
                 generate_hostname=safe_get_arg(args, "generate-host-name", True),
                 disk_image_file=args["image-file"],
                 memory_size=1024,
                 include_usb_disks=True,
                 grub_cfg_patch=patch_grub_cfg,
                 addition_dir=safe_get_arg(args, "addition-dir", None),
                 addition_tar=safe_get_arg(args, "addition-tar", None))
            print "Installation complete."
            print ""
            pass
        except (KeyboardInterrupt, SystemExit), e:
            print "Installation interrupted."
            raise e
        except Exception, e:
            print "Installation interrupted."
            print str(e)
            raise e

        if not wait_for_disk:
            break

        pass
    
    pass


def check_installation(args):
    disks, usb_disks = get_disks(False, True)
    disks = disks + usb_disks
    print "Disk count %d" % len(disks)
    for disk in disks:
        print "Disk %s" % (disk.device_name)
        if disk.has_wce_release():
            print "  WCE Ubuntu installed."
        else:
            print "  WCE Ubuntu NOT installed."
            pass
        for part in disk.partitions:
            print "  Partition %s : %s" % (part.partition_name, part.partition_type)
            pass
        pass
    pass


def finalize_wce_disk(args):
    wait_for_disk = safe_get_arg(args, "wait-for-disk", False)

    while True:
        if wait_for_disk:
            print "# Waiting for disk to appear"
            wait_for_disk_insertion()
            pass

        disks, usb_disks = get_disks(False, True)
        disks = disks + usb_disks
        print "# Disk count %d" % len(disks)

        targets = []
        index = 1
        n_wce_ubuntu_disk = 0
        first_target = None
        skipped = 0
        print "# Disks so far - ata/sata %d, usb %d" % (len(disks), len(usb_disks))
        print "# Detected disks"
        wce_ubuntu_disks = []
        for d in disks:
            if mounted_devices.has_key(d.device_name):
                print "%3d : %s  - mounted %s" % (index, d.device_name, mounted_devices[d.device_name])
            else:
                if d.has_wce_release():
                    print "%3d : %s" % (index, d.device_name)
                    n_wce_ubuntu_disk = n_wce_ubuntu_disk + 1
                    wce_ubuntu_disks.append(d)
                    if n_wce_ubuntu_disk == 1:
                        first_target = index - 1
                        pass
                    pass
                else:
                    print "%3d : %s - Not WCE Ubuntu disk" % (index, d.device_name)
                    pass
                pass
            index += 1
            pass
        
        if len(wce_ubuntu_disks) > 1:
            print " NOTE: Mounted disks cannot be the installation target."

            selection = getpass._raw_input("  space separated: ")
            for which in selection.split(" "):
                try:
                    index = string.atoi(which) - 1
                    if not wce_ubuntu_disks[index].mounted:
                        targets.append(wce_ubuntu_disks[index])
                    else:
                        print "%s is mounted and cannot be the target." % disks[index].device_name
                        pass
                except Exception, e:
                    print "Bad input for picking disk"
                    raise e
                pass
            pass
        elif len(wce_ubuntu_disks) == 1:
            targets.append(wce_ubuntu_disks[0])
            pass

        if len(targets) > 0:
            for target in targets:
                target.get_uuid_from_partitions()
                if target.uuid1:
                    target.mount_disk()
                    target.finalize_disk(False, patch_grub_cfg)
                    target.post_install(None, None,
                                        addition_dir=safe_get_arg(args, "addition-dir", None),
                                        addition_tar=safe_get_arg(args, "addition-tar", None))
                    target.unmount_disk()
                    pass
                else:
                    print "%s1 does not have UUID. Disk finalization skipped." % target.device_name
                    pass
                pass
            print "Disk finalization complete."
            pass

        if not wait_for_disk:
            break
        pass
    pass


def create_install_image(args):
    wait_for_disk = safe_get_arg(args, "wait-for-disk", False)
    image_file = args["image-file"]

    disks, usb_disks = get_disks(False, True)
    disks = disks + usb_disks
    sources = []
    print "Disk count %d" % len(disks)
    for disk in disks:
        print "Disk %s" % (disk.device_name)
        if disk.has_wce_release():
            sources.append(disk)
            print "  WCE Ubuntu installed."
        else:
            print "  WCE Ubuntu NOT installed."
            pass
        pass

    if len(sources) == 0:
        print "Did not find any WCE Ubuntu disks."
        pass
    elif len(sources) > 1:
        index = 1
        skipped = 0
        for disk in sources:
            print "%3d : %s" % (index, disk.device_name)
            index += 1
            pass
        selection = getpass._raw_input("  Choose one: ")
        index = string.atoi(selection) - 1
        sources = [sources[index]]
        pass
 
    source = sources[0]
    source.imagename = image_file
    source.create_image()
    pass



def save_install_image(args):
    image_file = args["image-file"]
    source_disk = args["source-disk"]

    disks, usb_disks = get_disks(False, False)
    disks = disks + usb_disks

    sources = {}
    if args.has_key("check-contents") and args["check-contents"]:
        for disk in disks:
            if disk.has_wce_release():
                sources[disk.device_name] = disk
                pass
            pass

        if len(sources.keys()) == 0:
            print "999 Did not find any WCE Ubuntu disks."
            sys.stdout.flush()
            sys.exit(1)
            pass
        elif not sources.has_key(source_disk):
            print "999 The disk %s has no WCE cotents." % source_disk
            sys.stdout.flush()
            sys.exit(1)
            pass
        pass
    else:
        for disk in disks:
            sources[disk.device_name] = disk
            pass
        pass
 
    if not sources.has_key(source_disk):
        print "999 Disk %s is not detected" % source_disk
        sys.exit(1)
        pass

    source = sources[source_disk]
    source.imagename = image_file
    source.create_image()
    pass


try:
    import pygtk
    import gtk
except:
    pass

class GUIInstaller():
    ui = '''<ui>
    <menubar name="MenuBar">
      <menu action="File">
        <menuitem action="Choose"/>
        <menuitem action="Refresh"/>
        <menuitem action="Install"/>
        <menuitem action="Save"/>
        <menuitem action="USB stick install"/>
        <menuitem action="Quit"/>
      </menu>
    </menubar>

    <toolbar name="Toolbar">
      <toolitem action="Choose"/>
      <toolitem action="Refresh"/>
      <toolitem action="Install"/>
      <toolitem action="Save"/>
      <toolitem action="Quit"/>
      <separator/>
    </toolbar>

    </ui>'''
      
    def __init__(self, args):
        #
        self.args = args
        #
        self.image_file = args['image-file'] if args.has_key('image-file') else None

        # Create the toplevel window
        self.window = gtk.Window()
        self.window.connect('destroy', lambda w: gtk.main_quit())
        self.window.set_size_request(500, -1)
        vbox = gtk.VBox()
        self.window.add(vbox)

        # Create a UIManager instance
        uimanager = gtk.UIManager()
        self.uimanager = uimanager

        # Add the accelerator group to the toplevel window
        accelgroup = uimanager.get_accel_group()
        self.window.add_accel_group(accelgroup)

        # Create an ActionGroup
        actiongroup = gtk.ActionGroup('DiskImageInstaller')
        self.actiongroup = actiongroup

        # Create actions
        actiongroup.add_actions([('Quit', gtk.STOCK_QUIT, '_Quit', None, 'Quit the Program', self.quit_cb),
                                 ('File', None, '_File')])
        actiongroup.add_actions([('Choose', gtk.STOCK_OPEN, '_Choose image...', None, 'Choose disk image source', self.choose_image_file_cb),
                                 ('Install', gtk.STOCK_APPLY, '_Install image', None, 'Install disk image', self.install_cb),
                                 ('Save', gtk.STOCK_SAVE, '_Save disk image', None, 'Save disk image', self.save_cb),
                                 ('USB stick install', gtk.STOCK_APPLY, '_USB stick install', None, 'USB stick install', self.usb_stick_install_cb),
                                 ('Refresh', gtk.STOCK_REFRESH, '_Refresh disks', None, 'Refresh disk status', self.refresh_disks_cb)])
        actiongroup.get_action('Quit').set_property('short-label', '_Quit')

        # Add the actiongroup to the uimanager
        uimanager.insert_action_group(actiongroup, 0)

        # Add a UI description
        uimanager.add_ui_from_string(self.ui)

        # Create a MenuBar
        menubar = uimanager.get_widget('/MenuBar')
        vbox.pack_start(menubar, False)

        # Create a Toolbar
        toolbar = uimanager.get_widget('/Toolbar')
        vbox.pack_start(toolbar, False)

        # Create the image file
        self.image_file_label = gtk.Label('Image file:')
        self.image_file_label.set_alignment(0, 0.5)
        vbox.pack_start(self.image_file_label)

        disks_label = gtk.Label('Disks')
        disks_label.set_alignment(0.5, 1.0)
        vbox.pack_start(disks_label)

        buttonbox = gtk.HButtonBox()
        self.disk_buttons = []

        #
        disk_button_names = ["sda", "sdb", "sdc", "sdd", "sde", "sdf", "sdg", "sdh", "sdi", "sdj" ]
        for name in disk_button_names:
            disk_button = gtk.CheckButton(name)
            self.disk_buttons.append(disk_button)
            disk_button.set_active(True)
            disk_button.connect('toggled', self.toggle_disk)
            buttonbox.pack_start(disk_button, False)
            pass

        vbox.pack_start(buttonbox)

        target_disk = self.args['target-disk'] if self.args.has_key('target-disk') else None
        if target_disk:
            for disk_button in self.disk_buttons:
                disk_button.set_sensitive(disk_button.get_name() == target_disk)
                disk_button.set_active(disk_button.get_name() == target_disk)
                pass
            pass
        
        liststore = gtk.ListStore(str, str, int)
        liststore.append(["Partitioning", "", 0])
        liststore.append(["Imaging",      "", 0])
        liststore.append(["Finalizing",   "", 0])
        self.progress_table = liststore

        treeview = gtk.TreeView(liststore)
        
        column_phase = gtk.TreeViewColumn("Activity")
        treeview.append_column(column_phase)

        column_status = gtk.TreeViewColumn("Status")
        treeview.append_column(column_status)

        column_progress = gtk.TreeViewColumn("Progress")
        treeview.append_column(column_progress)

        cell_phase_renderer = gtk.CellRendererText()
        column_phase.pack_start(cell_phase_renderer, False)
        column_phase.add_attribute(cell_phase_renderer, "text", 0)
        
        cell_status_renderer = gtk.CellRendererText()
        column_status.pack_start(cell_status_renderer, False)
        column_status.add_attribute(cell_status_renderer, "text", 1)

        cell_progress_renderer = gtk.CellRendererProgress()
        column_progress.pack_start(cell_progress_renderer, True)
        column_progress.add_attribute(cell_progress_renderer, "value", 2)

        vbox.pack_start(treeview)

        self.window.show_all()

        self.refresh_disks()
        return

    def toggle_disk(self, action):
        # action has not toggled yet
        return

    def quit_cb(self, b):
        gtk.main_quit()
        pass

    def choose_image_file_cb(self, b):
        self.choose_image_file()
        pass

    def choose_image_file(self):
        chooser = gtk.FileChooserDialog(parent=self.window,
                                        title="Choose WCE Disk Image File",
                                        action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                        buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        chooser.set_current_folder("/var/www/wce-disk-images")

        response = chooser.run()
        if response == gtk.RESPONSE_OK:
            self.image_file = chooser.get_filename()
            self.image_file_label.set_text("Image file: %s" % self.image_file)
            pass
        chooser.destroy()
        pass

    def clear_status(self):
        for row in range(0, 3):
            which = self.progress_table.get_iter(row)
            self.progress_table.set(which, 1, "")
            self.progress_table.set(which, 2, 0)
            pass
        while gtk.events_pending():
            gtk.main_iteration()
            pass
        pass


    def refresh_disks_cb(self, b):
        self.clear_status()
        self.refresh_disks()
        pass

    def refresh_disks(self):
        global mounted_devices, mounted_partitions
        disks, usb_disks = get_disks(True, False)

        all_disks = disks + usb_disks
        table = {}
        for disk in all_disks:
            table[disk.device_name] = 1
            pass

        for disk_button in self.disk_buttons:
            disk_name = "/dev/%s" % disk_button.get_label()
            if table.has_key(disk_name):
                disk_button.set_sensitive(True)
                if mounted_devices.has_key(disk_name):
                    disk_button.set_active(False)
                else:
                    disk_button.set_active(True)
                    pass
            else:
                disk_button.set_active(False)
                disk_button.set_sensitive(False)
                pass
            pass

        pass

    def install_cb(self, b):
        self.start_installation("install")
        pass

    def start_installation(self, install_command):
        if not self.image_file:
            self.choose_image_file()
            if not self.image_file:
                return
            pass

        install_button = self.uimanager.get_widget('/Toolbar/Install')
        install_button.set_sensitive(False)

        for disk_button in self.disk_buttons:
            disk_name = "/dev/%s" % disk_button.get_label()
            if disk_button.get_active() and disk_button.get_sensitive():
                self.install_image(install_command, disk_name)
                disk_button.set_active(False)
                pass
            pass

        install_button.set_sensitive(True)
        pass


    def install_image(self, install_command, disk_name):
        cmdline = "%s --%s %s --target-disk %s" % (sys.argv[0], install_command, self.image_file, disk_name )
        cmd_args = shlex.split(cmdline)
        backend = subprocess.Popen(cmd_args, bufsize=1, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        read_set = [backend.stdout, backend.stderr]
        write_set = []
        progress_re = re.compile(r'(\d\d\d) (.*)')
        stderr_data = ""
        stdout_data = ""
        rlist = []

        while backend.poll() == None:
            try:
                rlist, wlist, xlist = select.select(read_set, write_set, [], 0.5)
            except select.error, e:
                if e.args[0] == errno.EINTR:
                    continue
                raise

            if backend.stderr in rlist:
                data = os.read(backend.stderr.fileno(), 1024)
                if data == "":
                    read_set.remove(backend.stderr)
                    pass
                else:
                    pass
                pass

            if backend.stdout in rlist:
                data = os.read(backend.stdout.fileno(), 1024)
                if data == "":
                    read_set.remove(backend.stdout)
                    pass
                else:
                    sys.stdout.write(data)
                    stdout_data = stdout_data + data
                    lines = stdout_data.split('\n')
                    stdout_data = lines[-1]
                    lines = lines[:-1]
                    for line in lines:
                        m = progress_re.match(line)
                        if m:
                            progress = string.atof(m.group(1))
                            if progress < 20:
                                progress_min = 0
                                progress_max = 19
                                row = 0
                                pass
                            elif progress < 90:
                                progress_min = 20
                                progress_max = 89
                                row = 1
                                pass
                            elif progress <= 100:
                                progress_min = 90
                                progress_max = 100
                                row = 2
                                pass
                            elif progress > 900:
                                row = 2
                                pass

                            which = self.progress_table.get_iter(row)
                            self.progress_table.set(which, 1, m.group(2))
                            if progress >= 900:
                                self.progress_table.set(which, 2, 0)
                            else:
                                self.progress_table.set(which, 2, (100*(progress - progress_min)) / (progress_max - progress_min))
                                pass
                            if progress >= 100:
                                break
                            pass
                        pass
                    pass
                pass

            while gtk.events_pending():
                gtk.main_iteration()
                pass

            pass
        pass

    def save_cb(self, b):
        self.save_image()
        pass


    def save_image(self):
        disk_name = None
        for disk_button in self.disk_buttons:
            if disk_button.get_active() and disk_button.get_sensitive():
                disk_name = "/dev/%s" % disk_button.get_label()
                break
            pass

        if not disk_name:
            return

        chooser = gtk.FileChooserDialog(title="Save WCE Disk Image File",
                                        action=gtk.FILE_CHOOSER_ACTION_SAVE,
                                        buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        response = chooser.run()
        if response == gtk.RESPONSE_OK:
            image_file = chooser.get_filename()
            self.image_file_label.set_text("Image file: %s" % image_file)
            pass
        chooser.destroy()

        if response != gtk.RESPONSE_OK:
            return

        save_button = self.uimanager.get_widget('/Toolbar/Save')
        save_button.set_sensitive(False)
        self.clear_status()

        cmdline = "%s --save-install-image %s --source-disk %s" % (sys.argv[0], image_file, disk_name )
        cmd_args = shlex.split(cmdline)
        backend = subprocess.Popen(cmd_args, bufsize=1, stderr=subprocess.PIPE, stdout=subprocess.PIPE, close_fds=True)
        read_set = [backend.stdout, backend.stderr]
        write_set = []
        progress_re = re.compile(r'(\d\d\d) (.*)')
        stderr_data = ""
        stdout_data = ""
        rlist = []

        while backend.poll() == None:
            try:
                rlist, wlist, xlist = select.select(read_set, write_set, [], 0.5)
            except select.error, e:
                if e.args[0] == errno.EINTR:
                    continue
                raise

            if backend.stderr in rlist:
                data = os.read(backend.stderr.fileno(), 1024)
                if data == "":
                    read_set.remove(backend.stderr)
                    pass
                else:
                    pass
                pass

            if backend.stdout in rlist:
                data = os.read(backend.stdout.fileno(), 1024)
                if data == "":
                    read_set.remove(backend.stdout)
                    pass
                else:
                    sys.stdout.write(data)
                    stdout_data = stdout_data + data
                    lines = stdout_data.split('\n')
                    stdout_data = lines[-1]
                    lines = lines[:-1]
                    for line in lines:
                        m = progress_re.match(line)
                        if m:
                            progress = string.atof(m.group(1))
                            if progress < 20:
                                progress_min = 0
                                progress_max = 19
                                row = 0
                                pass
                            elif progress < 90:
                                progress_min = 20
                                progress_max = 89
                                row = 1
                                pass
                            elif progress <= 100:
                                progress_min = 90
                                progress_max = 100
                                row = 2
                                pass

                            which = self.progress_table.get_iter(row)
                            self.progress_table.set(which, 1, m.group(2))
                            self.progress_table.set(which, 2, (100*(progress - progress_min)) / (progress_max - progress_min))
                            if progress >= 100:
                                break
                            pass
                        pass
                    pass
                pass

            while gtk.events_pending():
                gtk.main_iteration()
                pass

            pass

        if backend.returncode != 0:
            d = gtk.MessageDialog(parent=self.window, type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK, message_format="Installation failed")
            d.run()
            d.destroy()
            pass
        pass

    def usb_stick_install_cb(self, b):
        self.start_installation("usb-stick-install")
        pass

    pass


def gui_install_image(args):
    if os.getuid() == 0:
        rooted_gui_install_image(args)
        pass
    else:
        # Rerun the script with sudo
        subprocess.call("gksudo -- python %s --gui" % args["argv0"], shell=True)
        pass
    pass

def rooted_gui_install_image(args):
    gui = GUIInstaller(args)
    gtk.main()

    if args.has_key('secondary-gui'):
        gui.start_installation("install")
        pass

    return


def installer_backend(args):
    try:
        installer_backend_body(args)
    except Exception, exc:
        exception_out = traceback.format_exc()
        for line in exception_out.split('\n'):
            print "# " + line
            pass
        stack_out = traceback.format_stack()
        for line in exception_out.split('\n'):
            print "# " + line
            pass
        pass
    pass

def installer_backend_body(args):
    global mounted_devices, disk_images

    disk_image_file = args['image-file']
    if disk_image_file == None:
        print "999 ERROR: no disk image."
        sys.exit(1)
        return

    target_disk = args['target-disk']

    disks, usb_disks = get_disks(True, True)
    disks = disks + usb_disks
    if len(disks) == 0:
        print "999 ERROR: no disks detected"
        sys.exit(1)
        pass
        
    target = None
    for d in disks:
        if d.device_name == target_disk:
            if mounted_devices.has_key(d.device_name):
                print "999 ERROR: %s mounted" % d.device_name
                sys.exit(1)
                return
            target = d
            break
        pass

    if not target:
        print "999 ERROR: no target disk found"
        sys.exit(1)
        pass

    #
    target.force_unmount_disk()

    memsize = 1024
    target.partclone_image = disk_image_file
    new_id = uuidgen()
    newhostname = "wce%s" % new_id[1:8]

    skip_to_finalize = False # for debugging

    print "010 Partitioning %s starting" % target.device_name
    sys.stdout.flush()
    if not skip_to_finalize:
        returncode = None
        try:
            returncode = target.partition_disk(memsize, False)
        except mkfs_failed, e:
            print "999 ERROR: File system creation failed on %s" % target.device_name
            sys.exit(1)
            pass
        if returncode != 0:
            print "999 ERROR: Partioning failed on %s" % target.device_name
            sys.exit(1)
            pass
        pass
    print "019 Partitioning completed"
    print "020 Restore disk image"
    sys.stdout.flush()
    if not skip_to_finalize:
        returncode = target.restore_disk_image_backend(disk_image_file)
        if returncode != 0:
            sys.exit(1)
            pass
        pass
    print "090 Finalizing disk"
    sys.stdout.flush()
    target.assign_uuid_to_partitions()
    target.mount_disk()
    print "092 Finalizing disk - disk mounted"
    sys.stdout.flush()
    target.finalize_disk(newhostname, patch_grub_cfg)
    print "095 Create WCE Tag"
    sys.stdout.flush()
    target.create_wce_tag(target.partclone_image)
    target.unmount_disk()
    print "099 Complete"
    target.remove_mount_dir()
    print "100 Image installation successful"
    sys.stdout.flush()
    sys.exit(0)
    pass

# --------------------------------------------------------------------------------

def usb_stick_installer_backend(args):
    global mounted_devices, disk_images

    fresh = True
    mbr = True

    print "001 Starting"
    sys.stdout.flush()
    iso_file = args['iso-file']
    if iso_file == None:
        print "999 ERROR: No ISO image file specified"
        sys.exit(1)
        return

    target_disk = args['target-disk']

    disks, usb_disks = get_disks(True, True)
    disks = disks + usb_disks
    if len(disks) == 0:
        print "999 ERROR: no disks detected"
        sys.exit(1)
        pass

    target = None
    for d in disks:
        if d.device_name == target_disk:
            if mounted_devices.has_key(d.device_name):
                print "999 ERROR: %s mounted" % d.device_name
                sys.exit(1)
                return
            target = d
            break
        pass

    if not target:
        print "999 ERROR: no target disk found"
        sys.exit(1)
        pass

    #
    print "002 Unmounting target"
    sys.stdout.flush()
    target.force_unmount_disk()

    print "003 Mounting ISO file"
    sys.stdout.flush()
    iso_mount_point = "/mnt/my_iso.%d" % os.getpid()
    mount_iso_file(iso_file, iso_mount_point)
    print "005 Mounting ISO file"
    sys.stdout.flush()

    if fresh:
        print "006 Partitioning started"
        sys.stdout.flush()
        parted = target.usb_installer_start_parted()
        (out, err) = parted.communicate()
        if len(err) > 0:
            print "999 ERROR: "+ err
            sys.exit(1)
            pass
        if out[0:6] == "Error:":
            print "999 %s" % out
            sys.exit(1)
            pass
        print "# %s" % out
        print "009 Refresh partitions"
        sys.stdout.flush()
        target.usb_installer_refresh_partition()
        pass
    else:
        print "009 "
        pass

    sys.stdout.flush()

    boot_part = None
    ext2_part = None
    print "010 Formatting partitions"
    sys.stdout.flush()
    for part in target.partitions:
        mkfs = None
        if part.partition_type == 'c':
            print "012 Partitioning boot partition"
            sys.stdout.flush()
            boot_part = part
            if fresh:
                mkfs = part.start_mkfs("ubuntu")
            else:
                part.partition_name = "ubuntu"
                pass
        elif part.partition_type == '83':
            print "013 Partitioning linux partition"
            sys.stdout.flush()
            ext2_part = part
            if fresh:
                mkfs = part.start_mkfs("casper-rw")
            else:
                part.partition_name = "casper-rw"
                pass
            pass

        if mkfs:
            progress = 14
            progress_max = 18
            n = 0
            while mkfs.returncode is None:
                time.sleep(0.3)
                n = n + 1
                if (n % 99) == 0:
                    if progress < progress_max:
                        progress = progress + 1
                        sys.stdout.write("%03d" % progress) 
                        sys.stdout.flush()
                        pass
                    pass
                mkfs.poll()
                pass
            pass

        pass

    if not boot_part:
        print "999 Boot parition is not found"
        sys.exit(1)
        pass

    if not ext2_part:
        print "999 Linux parition is not found"
        sys.exit(1)
        pass

    if fresh:
        print "019 Formatting complete"
        pass

    sys.stdout.flush()

    target.mount_partitions()
    print "020 Figuring out copying"

    # make_copy_plan(srcdir, destdir):
    srcdir = iso_mount_point
    destdir = boot_part.get_mount_point()

    root = root_node(srcdir)
    root.walk()
    destroot = root_node(destdir)
    root.set_destination(destroot, False)
    # need to filter out syslinux
    dirs = []
    for dir in root.dirs:
        if dir.name == "isolinux":
            dir.set_destination(syslinux_node(destroot, "syslinux"), True)
            dirs.append(dir)
        elif dir.name == "syslinux":
            continue
        else:
            dir.set_destination(node(destroot, dir.name), True)
            dirs.append(dir)
            pass
        pass
    # dirs holds the dirs without syslinux
    root.dirs = dirs
    plan = root.generate_plan()

    # execute_copy_plan

    total_cost = 0
    for step in plan:
        if step[0] == 'dir':
            cost = 2
        else:
            cost = (step[3] + 4095) / 4096 + 1 
            pass
        total_cost = total_cost + cost
        pass
    
    print "020 Copying: 0%"
    sys.stdout.flush()
    sofar = 0
    for step in plan:
        percentage = (100 * sofar) / total_cost
        print "%03d Copying %s" % ((20 + 68 * percentage / 100), step[2])
        sys.stdout.flush()
        if step[0] == 'dir':
            cost = 2
            if not os.path.exists(step[2]):
                os.mkdir(step[2])
                pass
            shutil.copymode(step[1], step[2])
        else:
            cost = (step[3] + 4095) / 4096 + 1 
            shutil.copy2(step[1], step[2])
            pass
        sofar = sofar + cost
        percentage = (100 * sofar) / total_cost
        print "%03d Copying %s" % ((20 + 68 * percentage / 100), step[2])
        pass

    sys.stdout.flush()
    # End of plan execution

    target.unmount_partitions()
    print "089 Target disk unmounted" 
    sys.stdout.flush()

    if mbr:
        print "090 Installing bootloader to %s" % boot_part.device_name
        sys.stdout.flush()
        boot_part.install_bootloader()

        print "095 Installing MBR to %s" % target.device_name
        sys.stdout.flush()
        target.install_mbr()

        pass

    print "099 Unmounting ISO"
    unmount_iso_file(iso_file, iso_mount_point)
    sys.stdout.flush()
    print "100 Complete"
    sys.stdout.flush()
    pass

# --------------------------------------------------------------------------------
# File copying util
#

class node:
    def __init__(self, parent, name):
        self.total_size = 0
        self.file_size = 0
        self.parent = parent
        self.files = []
        self.dirs = []
        self.path = None
        self.name = name
        self.destination = None
        pass

    def get_full_path(self):
        if not self.path:
            self.path = os.path.join(self.parent.get_full_path(), self.name)
            pass
        return self.path

    def walk(self):
        path = self.get_full_path()
        for entry in os.listdir(path):
            entry_path = os.path.join(path, entry)
            if os.path.isfile(entry_path):
                self.file_size = self.file_size + os.path.getsize(entry_path)
                self.files.append(entry)
                pass
            elif os.path.isdir(entry_path):
                self.dirs.append(node(self, entry))
                pass
            pass
        for dir in self.dirs:
            dir.walk()
            pass
        pass

    def get_total_file_size(self):
        size = self.file_size
        for dir in self.dirs:
            size = size + dir.file_size
            pass
        return size


    def set_destination(self, destnode, walk):
        if self.destination != None:
            return
        self.destination = destnode
        self.destination.total_size = self.total_size
        self.destination.file_size = self.file_size
        self.destination.files = self.files
        if walk:
            for dir in self.dirs:
                partner = node(destnode, dir.name)
                self.destination.dirs.append(partner)
                dir.set_destination(partner, True)
                pass
            pass
        pass


    def print_plan(self, level):
        print "%s%s -> %s" % (indentstr[0:level*2], self.get_full_path(), self.destination.get_full_path())
        print "%sTotal size: %d" % (indentstr[0:level*2], self.file_size)
        for file in self.files:
            print "%s%s" % (indentstr[0:level*2], file)
            pass
        for dir in self.dirs:
            dir.print_plan(level+1)
            pass
        pass


    def get_destination_path(self, file):
        return os.path.join(self.get_full_path(), file)


    def generate_plan(self):
        plan = []
        src = self.get_full_path()
        dst = self.destination.get_full_path()
        plan.append(('dir', src, dst, 0))
        for file in self.files:
            srcfile = os.path.join(src, file)
            dstfile = self.destination.get_destination_path(file)
            plan.append(('copy', srcfile, dstfile, os.path.getsize(srcfile)))
            pass
        for dir in self.dirs:
            plan = plan + dir.generate_plan()
            pass
        return plan

    pass


class root_node(node):
    def __init__(self, path):
        self.total_size = 0
        self.file_size = 0
        self.parent = None
        self.files = []
        self.dirs = []
        self.path = path
        self.name = None
        self.destination = None
        pass
    

    def get_full_path(self):
        return self.path

    def print_plan(self, level):
        node.print_plan(self, level)
        print "Grand total: %d" % self.get_total_file_size()
        pass

    pass


class syslinux_node(node):
    def __init__(self, parent, name):
        self.total_size = 0
        self.file_size = 0
        self.parent = parent
        self.files = []
        self.dirs = []
        self.path = None
        self.name = name
        self.destination = None
        pass

    def get_destination_path(self, file):
        if file == "isolinux.cfg":
            return os.path.join(self.get_full_path(), "syslinux.cfg")
        elif file == "isolinux.bin":
            return os.path.join(self.get_full_path(), "syslinux.bin")
        return os.path.join(self.get_full_path(), file)

    pass

# --------------------------------------------------------------------------------
def mount_iso_file(iso_file, iso_mount_point):
    if not os.path.exists(iso_mount_point):
        os.mkdir(iso_mount_point)
        pass
    mount = subprocess.Popen(["mount", "-o", "loop", iso_file, iso_mount_point], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = mount.communicate()
    pass

def unmount_iso_file(iso_file, iso_mount_point):
    umount = subprocess.Popen(["umount", iso_mount_point], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = umount.communicate()
    os.rmdir(iso_mount_point)
    pass

# --------------------------------------------------------------------------------


def usage(args):
    print '''install-ubuntu.py [COMMANDS] [OPTIONS]
 COMMANDS:
  No argument: triage/installation
  --create-install-image [image-file]: creates the disk image
  --image-disk: Disk imaging over network
  --install-iserver: Install installation server
  --batch-install [image-file]: Installs disk image with batch
  --check-installation: Checks the installtion
  --update-grub, --finalize-disk: Runs disk finalization on local disk.
  --help: prints this message
  
 OPTIONS:
  --wait-for-disk: waits for the disk insertion. Used with --batch-install
     or --finalzie-disk. It waits for the disk to appear, and the command
     loops. This is convenient to keep the program continuously run to 
     install software.
  --addition-dir [path] : adds the files in path to the installation
  --addition-tar [tar-file]: expands the tar file into the installation
'''
    pass


if __name__ == "__main__":
    try:
        opts, args = getopt.getopt(sys.argv[1:], "", ["image-disk", "install-iserver", "batch-install=", "no-unique-host", "force-installation", "check-installation", "update-grub", "wait-for-disk", "finalize-disk", "create-install-image=", "addition=", "addition-dir=", "addition-tar=", "help", "gui", "gui-image-file=", "backend=", "install=", "usb-stick-install=", "target-disk=", "save-install-image=", "source-disk=", "live-triage", "live-triage-step-2", "secondary-gui"])
    except getopt.GetoptError, err:
        # print help information and exit:
        print str(err) # will print something like "option -a not recognized"
        sys.exit(2)
        pass

    if len(opts) == 0:
        # When no option, standard installation
        triage_install()
        sys.exit(0)
        pass

    cmd = None
    args = {}
    args["argv0"] = sys.argv[0]
    for opt, arg in opts:
        if opt == "--help":
            cmd = usage
        elif opt == "--image-disk":
            cmd = image_disk
        elif opt == "--install-iserver":
            cmd = install_iserver
        elif opt == "--batch-install":
            cmd = batch_install
            args["image-file"] = arg
        elif opt == "--check-installation":
            cmd = check_installation
        elif opt == "--force-installation":
            args["force-installation"] = True
        elif opt == "--no-unique-host":
            args["generate-host-name"] = False
            pass
        elif opt == "--wait-for-disk":
            args["wait-for-disk"] = True
            pass
        elif opt == "--update-grub" or opt == "--finalize-disk":
            cmd = finalize_wce_disk
            pass
        elif opt == "--create-install-image":
            cmd = create_install_image
            args["image-file"] = arg
            pass
        elif opt == "--save-install-image":
            cmd = save_install_image
            args["image-file"] = arg
            pass
        elif opt == "--source-disk":
            args["source-disk"] = arg
            pass
        elif opt == "--addition":
            args["addition"] = arg
            pass
        elif opt == "--addition-dir":
            args["addition-dir"] = arg
            pass
        elif opt == "--addition-tar":
            args["addition-tar"] = arg
            pass
        elif opt == "--gui":
            cmd = gui_install_image
            pass
        elif opt == "--gui-image-file":
            args["image-file"] = arg
            pass
        elif opt == "--backend":
            cmd = installer_backend
            args["image-file"] = arg
            pass
        elif opt == "--install":
            cmd = installer_backend
            args["image-file"] = arg
            pass
        elif opt == "--usb-stick-install":
            cmd = usb_stick_installer_backend
            args["iso-file"] = arg
            pass
        elif opt == "--target-disk":
            args["target-disk"] = arg
            pass
        elif opt == "--live-triage":
            cmd = live_triage
            pass
        elif opt == "--live-triage-step-2":
            cmd = live_triage_step2
            pass
        elif opt == "--secondary-gui":
            args["secondary-gui"] = True
            pass
        pass

    if cmd == batch_install:
        image_file = ""
        try:
            image_file = args["image-file"]
        except:
            pass
        if len(image_file) == 0:
            print "Batch install requires a image file specified"
            sys.exit(2)
        pass
    elif cmd == create_install_image:
        image_file = ""
        try:
            image_file = args["image-file"]
        except:
            pass
        if len(image_file) == 0:
            print "Create install install requires a image file specified."
            sys.exit(2)
        pass

    elif cmd == save_install_image:
        image_file = ""
        try:
            image_file = args["image-file"]
        except:
            pass
        if len(image_file) == 0:
            print "Create install install requires a image file specified."
            sys.exit(2)
        pass

    elif cmd == installer_backend:
        image_file = ""
        try:
            image_file = args["image-file"]
        except:
            pass
        if len(image_file) == 0:
            print "Installer backend requires a image file specified."
            sys.exit(2)
            pass
        target_disk = ""
        try:
            target_disk = args["target-disk"]
        except:
            pass
        if len(target_disk) == 0:
            print "Installer backend requires a target disk specified."
            sys.exit(2)
            pass
        pass

    cmd(args)
    sys.exit(0)
    pass
