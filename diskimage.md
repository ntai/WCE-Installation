Disk image
==========

## Disk image overview

WCE ubuntu disk image contains Ubuntu Linux LTE and WCE curated educational contents. Once deployed to disk, the disk is bootable on any Intel computers.

You need to setup a master computer for disk image. First, install Ubuntu, then install the educational content curated by WCE staff.
The process of setting up the master computer is not in this document's scope. The document describes the technical aspect of creating the disk image and loading the disk image to the computer.

The disk imaging process is similar to WCE triaging. The boot screen lets you choose the imaging instead of triage.
You cannot boot from the master computer's disk. You need to start the installer/triage image and run the installer script (install-ubuntu.py) with appropriate command options.

Once the script starts for disk imaging, the imaging does following steps 

1. Runs fsck to check the consistenc of file system
2. Shrinks the disk partition to be smallest possible
3. Creates the disk image
4. Compresses the disk image
5. Write the disk image to (network) file

To conveniently start the master computer using the installer, it's convenient and fast to set up the network boot.

## Disk imaging setup

In order to create a disk image, the process requires followings.
* DHCP server
* NFS4 file server
* A netboot server, or a installer disc.

For the imaging master computer, do not use slow computer. The computer needs to be very fast because the disk image is created by the master computer as well as it is compressed by the master computer. At least, the computer must be quad core.

Once the master is setup, you need to start the computer from the triage disk. 
