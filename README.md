# serial_logger

SERIAL_LOGGER.PY - logs data received over a serial port, coming from a scale of type "Ohaus Defender 5000"
By fokke@bronsema.net, version 3 of February 2024
Usage: python serial_logger.py <serial port> <path of output file>

Features:
- reads data frames from a scale (tested with "Ohaus Defender 5000") and stores this in a csv-file on a USB stick; 
- Filename is based on the mac address of Pi (to distinguish logs from multiple instances of this logger) and the timestamp in te first data frame; 
- able to deal with removal of USB drive, will store data locally and copy file to USB stick once inserted;
- self update: if a file with the same name and with a newer version (see SCRIPTVERSION-paramater below) is found on the USB drive, this newer version will be installed and started;
- status output to a LED (red=error, green=ok, briefly blue=data frame received and stored);
- textual messages to an optional LCD-screen (16x2) which can be switched on/off by the script (controlled via LCD_PIN)
- Writes log information to stdout
 
One packet is about 100 chars @ (9600 Baud = 960 bytes/sec) => packet time is about 0.1 sec
Script needs to be run as root to be able to mount usb drives and access serial ports

Tested with a Raspberry Pi model B+ v1.2 running Debian Bookworm, Python 3.11. 

installation steps:
- install OS on an SD-card; 
- put SD in Pi, connect monitor and keyboard, power up, configure via menu, keyboard and user (e.g.: logger);
- login, select root: sudo su;
- apt update && sudo apt upgrade;
- create mount point for USB, for example: mkdir /media/logdata
- create temporary folder to store files when no usb drive is present: mkdir /root/serial_logger
- apt install pip (to be able to install additional Python modules)
- pip install pyserial psutil (needed to use the serial port and get the mac-address, execute as root because the script will run as root)
- optional: raspi-config: switch on ssh, set timezone, hostname, overclock, .. 
- optional: copy lines in rc.local to /etc to auto start the script when starting the Pi
- optional: connect power button and power led
- optional: copy the lines in /boot/config.txt to use the power on/power down button and power LED
- optional: raspi-config: sudo pip RPLCD smbus to use an external i2c display (do not switch on i2c in raspi-config).  
