#!/usr/bin/python
## SERIAL_LOGGER.PY - logs data received over a serial port, coming from a scale of type "Ohaus Defender 5000"
# By fokke@bronsema.net, version 3 of February 2024
#
# Usage: python serial_logger.py <serial port> <path of output file>
#
# Features:
# - reads data frames from a scale (tested with "Ohaus Defender 5000") and stores this in a csv-file on a USB stick; 
# - Filename is based on the mac address of Pi (to distinguish logs from multiple instances of this logger) and the timestamp in the first data frame; 
# - able to deal with removal of USB drive, will store data locally and copy file to USB stick once inserted;
# - self update: if a file with the same name and with a newer version (see SCRIPTVERSION-paramater below) is found on the USB drive, 
#   this newer version will be installed and started;
# - status output to a LED (red=error, green=ok, briefly blue=data frame received and stored);
# - textual messages to an optional LCD-screen (16x2) which can be switched on/off by the script (controlled via LCD_PIN)
# - Writes log information to stdout
# 
# One packet is about 100 chars @ (9600 Baud = 960 bytes/sec) => packet time is about 0.1 sec
# Script needs to be run as root to be able to mount usb drives and access serial ports
#
# Tested with a Raspberry Pi model B+ v1.2 running Debian Bookworm, Python 3.11. 
#
# installation steps:
# - install OS on an SD-card; 
# - put SD in Pi, connect monitor and keyboard, power up, configure via menu, keyboard and user (e.g.: logger);
# - login, select root: sudo su;
# - apt update && sudo apt upgrade;
# - create mount point for USB, for example: mkdir /media/logdata
# - create temporary folder to store files when no usb drive is present: mkdir /root/serial_logger
# - apt install pip (to be able to install additional Python modules)
# - pip install pyserial psutil (needed to use the serial port and get the mac-address, execute as root because the script will run as root)
# - optional: raspi-config: switch on ssh, set timezone, hostname, overclock, .. 
# - optional: copy lines in rc.local to /etc to auto start the script when starting the Pi
# - optional: connect power button and power led
# - optional: copy the lines in /boot/config.txt to use the power on/power down button and power LED
# - optional: raspi-config: sudo pip RPLCD smbus to use an external i2c display (do not switch on i2c in raspi-config).  

import time
import RPi.GPIO as GPIO 
import signal
import serial
import sys
import os, subprocess, shutil
import psutil
from RPLCD.i2c import CharLCD       # see https://rplcd.readthedocs.io/en/stable/

# "constants":
LED_R = 17                  # pin of red led
LED_G = 27                  # pin of green led
LED_B = 22                  # pin of blue led
PACKET_TIMEOUT = 0.1        # timeout to wait before concluding a new packet was received. Also used for a short delay in the main loop.
SCRIPT_VERSION = "3.0"      # version of this script, used for determining if an updated version of the script is available.
SCRIPTID = "'serial_logger.py' v"+SCRIPT_VERSION+" by fokke@bronsema.net" # identification of this script, shown at init.
TMP_FOLDER = "/tmp/serial_logger" # temp folder of this program.  
LED_PERIOD = 500            # duration of blue receive-flash of LED in msec.
LCD_PIN = 25                # GPIO pin at which the LCD power is connected.

# global vars:
run = True                  # if true, keep on running. Script will stop when this becomes false.
serial_adaptor = None       # object with serial adaptor functions
writer = None               # object to deal with output file, USB stick
status_led = None           # object to deal with the status LED
lcd = None                  # LCD display


class SerialAdaptor:
# a class to deal with serial communication

    ser = None                  # serial port object
    serialport = ""             # name of serial port (read from command line)
    ser_status = False          # current status of serial port (true = present, false = removed)
    lcd = None


    def __init__(self, lcd, serialport):
    # constructor    
        self.serialport = serialport
        self.lcd = lcd
        

    def __del__(self):
    # destructor    
        self.ser.close()        
        print (f"Closed serial port {self.serialport}")
        

    def connect_to_serial (self):
    # (re)connects to the serial port and sets the ser-var
    # returns true or false if it succeeds or fails     
      
        try:
            self.ser = serial.Serial(
                    port=self.serialport, 
                    baudrate = 9600,
            #        parity=serial.PARITY_NONE,
            #        stopbits=serial.STOPBITS_ONE,
            #        bytesize=serial.EIGHTBITS,
                    timeout=PACKET_TIMEOUT     
            )  
            print (f"Opened serial port {self.serialport}")
            self.ser_status = True        
            self.lcd.write_lines ("Serial connected")
        except:
            print (f"Opening serial port {self.serialport} failed")
            time.sleep(0.5)   # a short delay before trying it again
            self.ser_status = False
            self.lcd.write_lines ("Connect serial")
              
        return self.ser_status
    

    def parse_msg (self, msg):
    # parses the received messages from serial
    # in: msg, the raw received message in the form of a list of lines of bytes (as read in by serial.readlines)
    # out: returns a dict containing the parsed information or "None" when an illegal msg was received
    
        print ("Received raw:", msg)

        if len(msg) != 5:
            print (f"Illegal message of {len(msg)} lines (should be 5)")
            return None
    
        # get the values from the lines:
        try:        
            parsed = {}
            parsed["date"] = msg[0].decode().strip()
            parsed["time"] = msg[1].decode().strip()
            parsed["typenr"] = msg[2].decode().strip()
    
            temp = msg[3].decode().strip().split(' ')
            temp = list(filter(None, temp)) # remove empty values from list
            parsed["weight1"] = temp[0]
            parsed["unit1"] = temp[1]

            temp = msg[4].decode().strip().split(' ')
            temp = list(filter(None, temp))
            parsed["weight2"] = temp[0]
            parsed["unit2"] = temp[1]
            parsed["result"] = temp[2]

            print ("Parsed into dict: ", parsed)
            return parsed
    
        except:
            print (f"Skipped this malformed message.")        
            return None
        

    def receive (self):       
    # sees if there is a data frame available and returns it in a csv-format
    # return None if no frame was available

        recv_data = None
        
        try:
            if (self.ser != None):
            # Ser is initialised
                recv_data = self.ser.readlines()   # read multiple lines with a timeout 
                if len(recv_data) == 0:
                    recv_data = None
            else:
                self.connect_to_serial ()   
        except:
        # error in serial port, reconnect
            print ("Error reading from serial.");
            self.ser.close()
            self.connect_to_serial ()
   
        if recv_data != None and len(recv_data) > 0:
        # msg received, try to parse it       
            print () # empty line
            recv_data = self.parse_msg (recv_data)            

        return recv_data            
    

class Writer:
# deals with writing to disk and (un)mounting the disk

    folder = None           # folder to write to without trailing '/', e.g. /media/usbdrive (indicated by user via command line, see init())
    filename = None         # name of the output file, determined by script 
    current_output = None   # current output folder (either a temporary file or a file on "folder")
    lcd = None


    def __init__ (self, lcd, folder):    
    # constructor
        self.folder = folder
        self.lcd = lcd
        self.umount_usb_drive()   # umount drive, could be mounted as RO


    def __del__ (self):
    # destructor 
        self.umount_usb_drive ()       
        

    def get_filename (self, data):
    # returns the filename excluding the path, based on the timestamp in the data and the mac address of this Pi

        global filename

        if (self.filename == None and data != None):
        # filename not determined yet and data is available -> determine file name based on mac address, date and time:
            try:
                self.filename = ""

                # get the mac_address to distinguish between Pi's in the logfile names:
                nic_eth0 = psutil.net_if_addrs()['eth0']
                for interface in nic_eth0:
                    if interface.family == 17:  # mac address
                        self.filename = interface.address.replace (":","")+"_"       # remove ':' from mac address
                                               
                temp = data["date"].split('/')
                self.filename += temp[2]+temp[1]+temp[0]
                self.filename += "-"+data["time"].replace(':','_')+".csv"
            
                print (f"New filename: {self.filename}")
            except:
                print ("Error determining new filename, input:")
                print (data)
                self.filename = None

        return self.filename
        

    def get_usb_drives (self):
    # returns a list of USB drives connected to the system
    # thanks to: https://stackoverflow.com/questions/2384290/better-way-to-script-usb-device-mount-in-linux    
       
        partitionsFile = open("/proc/partitions")
        lines = partitionsFile.readlines()[2:] #Skips the header lines
        drives = []

        for line in lines:
            words = [x.strip() for x in line.split()]
            minorNumber = int(words[1])
            deviceName = words[3]
            if minorNumber % 16 == 0:
                path = "/sys/class/block/" + deviceName
                if os.path.islink(path):
                    if os.path.realpath(path).find("/usb") > 0:
                        drives.append(f"/dev/{deviceName}1")

        return drives                    


    def is_mounted (self):
    # returns true if folder is mounted (in other words: if it is mentioned in the output of mount)

        out = str(subprocess.run("mount", capture_output = True).stdout)
        return self.folder in out


    def check_for_update (self, location):
    # checks if there is an update of this script @ location     
    # see if a file named SCRIPTNAME exists and reads the version from it
    # if the version is higher than the version of this script, overwrite this script, start it and stop this script
# tbd: run needed?
#        global run
    
        myname = os.path.basename(sys.argv[0])
    
        print (f"Checking for an update at {location}/{myname}")
    
        try:
            with open(location+"/"+myname, 'r') as file:
                data = file.read()
        except:
            print ("No update available, continuing with the script")
            return
    
        data = data.split ("SCRIPT_VERSION")[1].lstrip()  
    
        if data[0] == '=' : 
        # version is available, isolate it:
            new_version = data.splitlines()[0].split('"')[1] 
            print (f"Found version number in mounted file: {new_version}")

            if (new_version > SCRIPT_VERSION): 
                mypath=os.path.abspath(os.path.dirname(__file__))
                print (f"New version is higher than current version ({SCRIPT_VERSION}), installing new version to {mypath}/{myname}")
                try:
                    shutil.copyfile (location+"/"+myname, mypath+"/"+myname)
                except:
                    print("Copy failed, continuing")
                else:    
                    print ("New version copied, starting it and self-terminating")
                    self.lcd.write_lines ("Updated script", f"From {SCRIPT_VERSION} to {new_version}", 1)
                    
                    try:
                        os.execl (sys.executable, *([sys.executable]+sys.argv)) # call same script with same cmdline parameters
                        print ("This should never be shown")
                    except:
                        print ("Starting next process failed")
            else:
                print (f"Already at this version or better, keeping current version {SCRIPT_VERSION}")


    def mount_usb_drive (self, drive, location):
    # tries to mount the USB drive at the specified location
    
        print (f"Trying to mount {drive} at location {location}.")
        
        out = subprocess.run(["mount", drive, location], capture_output = True)
        if out.returncode == 0:
            print ("Mount OK")
            self.check_for_update (location)
            return True
        else:
            print (f"Mount ERROR, returned: ")
            print (out)
            return False


    def umount_usb_drive (self):
    # umounts the drive, returns true if it actually was unmounted    
# tbd: try .. except?
        if self.is_mounted ():
            out = subprocess.run(["umount", self.folder], capture_output = True)
            if out:
                print (f"Unmounted {self.folder}")
                return True
            else:    
                print (f"Unmount of {self.folder} failed, returned:")
                print (out)
    
        return False


    def mount_if_needed (self):
    # mounts the USB drive if needed and possible    

        # first see if any USB drives are connected:
        drives = self.get_usb_drives()
        if len (drives) == 0: 
        # no drive inserted, write output to temp and unmount the drive (which could still be mounted)   
            self.current_output = TMP_FOLDER
            if self.umount_usb_drive ():
            # the drive was still mounted, reset the file name    
                self.filename = None
        else:
        # a USB drive is present but possibly not mounted
            if self.is_mounted ():
            # it is mounted, write to it    
                self.current_output = self.folder
            else:
            # it is not mounted, but it is possible to mount

                # mount the usb drive:                
                out = self.mount_usb_drive (drives[0], self.folder)            
                if out:
                    # move the logfile(s) in temp to the usb drive:
                    for file in os.listdir (TMP_FOLDER):  
                        #if file.isfile ():
                        if file.endswith('.csv'):
                        # this is a .csv file, move it    
                            out = subprocess.run(["mv", TMP_FOLDER+"/"+file, self.folder], capture_output = True)    
                            if out:
                                print (f"Moved file {file} from {TMP_FOLDER} to {self.folder}")
                            else:    
                                print (f"Moving file {file} to {self.folder} failed. Result:")
                                print (out)
                        else:
                        # only copy the other files, give them a new name 
                            if self.filename == None:
                                new_name = self.folder+"/"+file
                            else:
                                new_name = self.folder+"/"+self.filename+"_"+file
                                
                            out = subprocess.run(["cp", TMP_FOLDER+"/"+file, new_name], capture_output = True)    
                            if out:
                                print (f"Copied file {file} from {TMP_FOLDER} to {new_name}")
                            else:    
                                print (f"Copying file {file} to {new_name} failed. Result:")
                                print (out)

                # mount succeeded, a new file is needed    
                    self.filename = None                
                    self.current_output = self.folder
                else:
                # mount failed :-(
                    self.current_output = TMP_FOLDER
 

    def write_data (self, data):
    # writes the data to the indicated file, deals with (not) present USB stick

        temp = ""
        output_to = "" 
        i = 0
        global folder, filename
        
        # now either the USB drive is ready or we write to the temp location.   
        filename = self.get_filename(data)
    
        # create output line:
        for field in data.values():
            if (i>0):
                temp += ';'
            temp += field
            i += 1
    
        # write it to the file:
        try:
            logfile = open(self.current_output+"/"+self.filename, "a") 
            logfile.write(temp+"\n")
            logfile.close()
            print (f"Wrote to {self.current_output}/{self.filename}: '{temp}'")
        except Exception as ex:
            print (f"Unable to write to file {self.current_output}/{self.filename}, data is lost. Exception:")
            print (ex)


class Status_LED:
    led_timer = 0               # timer for the blue receive-flash
    time_on = 0
    current_status = 255        # current script status (see get_status)    
    start_millis = None

    def __init__(self):
    # constructor; init the output pins and show a test sequence

        # set GPIO pins of the LEDs
        GPIO.setup ([LED_R, LED_G, LED_B], GPIO.OUT)
        print ("GPIO setup ok, showing test sequence")
    
        # show a test sequence on the LED at startup:
        self.setLed ([LED_R])
        time.sleep(1)
        self.setLed ([LED_G])
        time.sleep(1)    
        self.setLed ([LED_B])
        time.sleep(1)
        
        self.start_millis = int(time.time()*1000.0)
        print ("Test sequence complete")

        
    def __del__(self):
    # destructor, switch off the leds
        self.setLed([])   
        print ("Switched off LEDs")


    def get_millis(self):
    # returns the amount of msecs passed since creation of this object    
        return int(time.time()*1000.0) - self.start_millis

    
    def flash_led (self, pin, time):
    # switches on the LED@pin for time milliseconds
        self.led_timer = self.get_millis() + time
        self.setLed([pin])
        #print ("Flash start, timer = ",self.led_timer, "millis =",self.get_millis())
        

    def update(self, status):
    # updates the LED if needed
        
        if self.led_timer > 0 and self.get_millis() - self.led_timer > 0:
        # flash led is switched on and shall be switched off because of the timeout of led_timer
            self.led_timer = 0
            self.current_status = 255
            #print ("Flash end at millis = ", self.get_millis())
            
        if self.led_timer == 0:            
        # flash led is switched off, show regular status    
            if status != self.current_status:
            # an update is needed    
                if status == 0:
                    self.setLed([LED_G])
                else:
                    self.setLed([LED_R])


    def setLed (self, ledpins):
    # sets the LED to the indicated color (R/G/B)
    # ledpins is a list of pins to set low (=on)
    # use a list of ledpins, e.g. [LED_R], [LED_G], [LED_B], [LED_R, LED_G, LED_B], [] etc

        # first all LEDs off:
        GPIO.output ([LED_R, LED_B, LED_G], GPIO.HIGH)
    
        # then the correct LEDs on again:
        for pin in ledpins:
            GPIO.output (pin, GPIO.LOW)
                        

class LCD_logger:
# a class for the LCD display

    lcd = None

    def __init__(self):
    # constructor, show startup message

        # set power to the LCD screen, wait a short period for the screen to stabilise:
        GPIO.setup (LCD_PIN, GPIO.OUT)
        GPIO.output (LCD_PIN, GPIO.HIGH)
        time.sleep (0.1)

        try:
            # initialise the screen:
            self.lcd = CharLCD(i2c_expander='PCF8574', address=0x27, port=3, cols=16, rows=2)
        except:  
            print ("Geen LCD scherm gevonden")
            self.lcd = None
        else:            
            self.lcd.clear()
            self.lcd.write_string("Initialising\r\n")
            self.lcd.write_string("Version: "+SCRIPT_VERSION)   
            print ("LCD setup OK")


    def __del__(self):
    # destructor: show exit message, wait, shutdown the screen 
        
        if self.lcd != None:
            self.lcd.clear()
            self.write_lines("Script stopped", "", 1)       

        GPIO.output (LCD_PIN, GPIO.LOW)
        
        
    def write_data (self, data):
    # shows the measurement data on the lcd
        if self.lcd != None:
            self.lcd.clear()
            self.lcd.write_string(data["time"]+"\r\n")
            self.lcd.write_string(data["weight1"]+" kg")


    def write_lines (self, line1, line2="", wait=0):
    # writes the lines to the lcd, waits (blocks) for wait sec    
        if self.lcd != None:
            self.lcd.clear()
            self.lcd.write_string(line1)
            self.lcd.cursor_pos = (1, 0)
            self.lcd.write_string(line2)
            if wait > 0:
                time.sleep (wait)


def init ():
# initialises the status LED outputs and signal handler
# sets the serial port to read from and the folder to write to
# (serial port is initialised in the main loop)

    global serial_adaptor, writer, status_led, lcd

    print (f"Starting {SCRIPTID}")
    os.system("echo default-on>/sys/class/leds/pwr_led/trigger")   # tell the kernel to keep the power led on

    # parse command line parameters:
    if len(sys.argv) == 3:
        serialport = sys.argv[1]
        folder = sys.argv[2].rstrip("/") 
        print (f"Command line parameters parsed OK (serial={serialport}, output folder={folder})")
    else:
        print (f"Usage: {sys.argv[0]} <serial port> <output path>")
        exit(1)

    GPIO.setwarnings(False) 
    GPIO.setmode (GPIO.BCM)        
    
    # create the objects:
    lcd = LCD_logger ()
    serial_adaptor = SerialAdaptor(lcd, serialport)
    writer = Writer(lcd, folder)
    status_led = Status_LED ()
    
    # create TMP_FOLDER if it does not exist yet:
    if not os.path.exists(TMP_FOLDER):
        os.makedirs (TMP_FOLDER)
        print (f"Created temp folder {TMP_FOLDER}")
    
    # same for output folder:
    if not os.path.exists(folder):
        os.makedirs (folder)
        print (f"Created output folder {folder}")

    # set the signal handlers:
    signal.signal(signal.SIGINT, cleanup_function)
    signal.signal(signal.SIGTERM, cleanup_function)
    signal.signal(signal.SIGHUP, cleanup_function)
    print ("Signal handlers setup ok")

    print ("Init is finished")
     

def cleanup_function(signalnr, frame):
# program is ordered to terminate, signal handler

    global run

    try:
        os.system("echo heartbeat>/sys/class/leds/pwr_led/trigger")   # tell the kernel to start blinking the power LED
    except:
        print ("Heartbeat failed")
        
    run = False    
    print (f"Received signal {signalnr}, terminating script")


def get_status (serial_adaptor, writer):
# returns the current status of the script:
# - 0 if the serial port is opened and the output file is available (all OK)
# - 1 if the serial port is not ok
# - 2 if the serial port is ok but the output folder is not (i.e.: USB stick was removed from system)
# - 3 if both the serial port and the output are not ok
    
    retval = 0
    if not serial_adaptor.ser_status:
        retval += 1

    if not writer.is_mounted(): 
        retval += 2
        
    return retval
            

# main program:
init()

while run:
    recv_data = serial_adaptor.receive()  # read data from serial, will block for PACKET_TIMEOUT seconds
    writer.mount_if_needed()  # regularly check for a mounted usb drive
    
    if recv_data != None:
    # msg parsed OK, write it to disk and show blue light
        writer.write_data (recv_data)
        lcd.write_data (recv_data)
        status_led.flash_led (LED_B, LED_PERIOD)
     
    # update status led if needed:
    status_led.update(get_status(serial_adaptor, writer))

# terminate the program when "run" becomes False:     
del status_led
del writer
del serial_adaptor
del lcd
