#!/usr/bin/env python

import sys
try:
	import psycopg2
except ImportError:
	print "No psycopg2!"
	sys.exit(1)

try:
	import jss
except ImportError:
	print "NO jss!"
	sys.exit(1)

import os
import json
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--dbprefs", help="Path to db prefs JSON file. Defaults to com.github.nmcspadden.prefs.json")
parser.add_argument("--jssprefs", help="Path to Python-JSS prefs plist.  Defaults to com.github.sheagcraig.python-jss.plist")
parser.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity to print status updates")

## Code taken from http://code.activatestate.com/recipes/577081-humanized-representation-of-a-number-of-bytes/
def GetHumanReadable(size, precision=2):
	suffixes=['KB','MB','GB','TB']
	suffixIndex = 0
	while size > 1024:
		suffixIndex += 1 #increment the index of the suffix
		size = size/1024.0 #apply the division
	return "%.*f %s"%(precision,size,suffixes[suffixIndex])

## Original code
def OpenPrefsFile(preferences_file):
	prefs = dict()
	try:
		with open(preferences_file) as json_file:
			prefs = json.load(json_file)
		return prefs
	except:
		print "Couldn't access prefs file with access info."
		sys.exit(1)

#Initialize the SQL table
def CreateCasperImportTable(conn):
	sql = """CREATE TABLE IF NOT EXISTS casperimport(id INT PRIMARY KEY NOT NULL, serial TEXT, name TEXT, model TEXT, ios_version TEXT, ipaddress TEXT, macaddress TEXT, bluetooth TEXT, capacity TEXT, username TEXT, email TEXT, asset_tag TEXT);"""
	cursor = conn.cursor()
	cursor.execute(sql)

## Update the data in the SQL table
def SubmitSQLForDevice(thisDevice, conn, j):
	device_name = thisDevice['device_name']
	device_username = thisDevice['username']
		
	sql = """DROP FUNCTION IF EXISTS merge_db(idVar INT, serialVar TEXT, nameVar TEXT, modelVar TEXT, ios_versionVar TEXT, ipaddressVar TEXT, macaddressVar TEXT, bluetoothVar TEXT, capacityVar TEXT, usernameVar TEXT, emailVar TEXT, asset_tagVar TEXT); CREATE FUNCTION merge_db(idVar INT, serialVar TEXT, nameVar TEXT, modelVar TEXT, ios_versionVar TEXT, ipaddressVar TEXT, macaddressVar TEXT, bluetoothVar TEXT, capacityVar TEXT, usernameVar TEXT, emailVar TEXT, asset_tagVar TEXT) RETURNS VOID AS 
$$
BEGIN
    LOOP
        -- first try to update the key
        UPDATE casperimport SET serial = serialVar, name = nameVar, model = modelVar, ios_Version = ios_versionVar, ipaddress = ipaddressVar, macaddress = macaddressVar, bluetooth = bluetoothVar, capacity = capacityVar, username = usernameVar, email = emailVar, asset_tag = asset_tagVar WHERE id = idVar;
        IF found THEN
            RETURN;
        END IF;
        -- not there, so try to insert the key
        -- if someone else inserts the same key concurrently,
        -- we could get a unique-key failure
        BEGIN
            INSERT INTO casperimport(id,serial,name,model,ios_version,ipaddress,macaddress,bluetooth,capacity,username,email,asset_tag) VALUES (idVar, serialVar, nameVar, modelVar, ios_versionVar, ipaddressVar, macaddressVar, bluetoothVar, capacityVar, usernameVar, emailVar, asset_tagVar);
            RETURN;
        EXCEPTION WHEN unique_violation THEN
            -- Do nothing, and loop to try the UPDATE again.
        END;
    END LOOP;
END;
$$
LANGUAGE plpgsql; """
	
	cursor = conn.cursor()
	cursor.execute(sql)
	
	sql = """SELECT merge_db(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);"""
	sql_values=[ thisDevice['id'], thisDevice['serial_number'], (device_name or u'').encode('unicode_escape').decode().encode('latin1'), thisDevice['modelDisplay'], j.MobileDevice(thisDevice['id']).findtext('general/os_version'), j.MobileDevice(thisDevice['id']).findtext('general/ip_address'), thisDevice['wifi_mac_address'], j.MobileDevice(thisDevice['id']).findtext('general/bluetooth_mac_address'), GetHumanReadable(int(j.MobileDevice(thisDevice['id']).findtext('general/capacity'))), (device_username or u'').encode('unicode_escape').decode().encode('latin1'), j.MobileDevice(thisDevice['id']).findtext('location/email_address'), j.MobileDevice(thisDevice['id']).findtext('location/asset_tag') ]
	
	cursor = conn.cursor()
	cursor.execute(sql, sql_values)
	cursor.close()

## Where the magic happens
def main():
	args = parser.parse_args()
	preferences_file = args.dbprefs or "com.github.nmcspadden.prefs.json"
	jssprefs_file = args.jssprefs or "com.github.sheagcraig.python-jss.plist"
	accessPreferences = OpenPrefsFile(preferences_file)
	if args.verbose > 0:
		print "Attempting to connect to Postgres Database..."
	try:
		conn = psycopg2.connect(host=accessPreferences['postgres_host'], dbname=accessPreferences['postgres_db'], user=accessPreferences['postgres_user'], password=accessPreferences['postgres_password'])
	except psycopg2.Error, e:
		print "Error %d: %s" % (e.args[0], e.args[1])
		sys.exit(1)

	if args.verbose > 0:
		print "Attempting to connect to JSS..."	
	try:
		jss_prefs = jss.JSSPrefs(jssprefs_file)
		j = jss.JSS(jss_prefs)
	except:
		print "Couldn't access JSS preferences file."
		sys.exit(1)
	
	if args.verbose > 0:
		print "Attempting to create database table..." 

	CreateCasperImportTable(conn)

	if args.verbose > 0:
		print "Attempting to access JSS device list..."

	deviceList = j.MobileDevice()

	if args.verbose > 0:
		print "Parsing device list and adding to database."

	for device in deviceList:
		SubmitSQLForDevice(device, conn, j)
	
	if args.verbose > 0:
		print "Committing database transactions..."

	conn.commit()

	if args.verbose > 0:
		print "Done."

	
#Time for magic to happen.
main()