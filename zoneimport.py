#!/opt/local/bin/python

import pyrax
import sys
import re
import logging
import time

from os import listdir, rename
from os.path import isfile, join

# basedir contains the following:
#    DNS zones in basedir/var/named
#        With the assumption that zone files are named domain.tld.db
#    Destination for processed DNS zones in basedir/var/processed
#    Rackspace Cloud credentials in basedir/cloudcred
#    A log file is created at basedir/import-(current UTC timestamp).log
# IMPORTANT: Trailing slash is necessary
basedir = "/home/exampleuser/zonefiles/"

# domainemail is the contact email address with '.' for '@' and a trailing '.', used to generate the SOA records.
domainemail = 'it.example.com.'

# Set the Cloud identity credentials.
pyrax.set_setting("identity_type", "rackspace")
pyrax.set_credential_file(basedir + "cloudcred")
cdns = pyrax.cloud_dns

# Generate a string from the current UTC timestamp.
utcstamp = str(int(time.time()))

# Create the log file and set the logging configuration.
logging.basicConfig(filename=basedir + 'import-' + utcstamp + '.log', level=logging.INFO)

# Build the path to the bind files. Trailing slash required.
bindpath = basedir + "var/named/"

# Build the path to move the processed zone files to.
procpath = basedir + "var/processed/"

# nsregex is the regular expression used to find nameserver records in the zones.
nsregex = '\S+\s+[0-9]+\s+IN\s+NS\s+.*'

# soaregex is the regular expression used to find the old SOA records in zones and replace them with new records.
soaregex = '\S+\s+[0-9]+\s+IN\s+SOA\s+\S+\s+\S+\s+(\()?(\n)?\s+[0-9]+(.*\n)?\s+[0-9]+(.*\n)?\s+[0-9]+(.*\n)?\s+[0-9]+(.*\n)?\s+[0-9]+(.*\n)?(\s+\))?'

# Set the DNS API timeout higher (default is 5 seconds), because it tends to be sluggish at times.
cdns.set_timeout(60)

# Create a list of the zone files contained in basedir/var/named
zonefiles = [ f for f in listdir(bindpath) if isfile(join(bindpath,f)) ]

# This is the main zone file processing block, where the work is done.
for zonefile in zonefiles:
    # Assuming the zonefiles are named appropriately as domain.tld.db, strip off '.db' to get the domain name.
    domain = zonefile.rstrip(".db")
    # Log each domain as processing begins.
    logging.info('Processing:' + domain)
    # Open the zone file as bindfile and read it into data.
    with file(bindpath + zonefile) as bindfile:
        data = bindfile.read()
        # Create a valid $ORIGIN directive.
        # TODO: Test for existence of $ORIGIN before adding it unecessarily.
        origindata = "$ORIGIN " + domain + "\n" + data
        # Remove any nameserver records from the zone, because Cloud DNS will add them automatically.
        nsszone = re.sub(nsregex, '', origindata)
        try:
            # Generate a new SOA record with the correct source host and email address.
            newsoa = domain + '.	300	IN	SOA	' + 'dns1.stabletransit.com. ' + domainemail + ' ' + utcstamp + ' 21600 3600 1814400 300'
            # Confirm that the SOA record will be found to be replaced.
            if re.search(soaregex, nsszone) == None:
                # SOA record not found using soaregex: exit, logging failure of this this zone.
                raise Exception('SOA regex match not found')
            else:
                # SOA record found: replace it with the new SOA record.
                zone = re.sub(soaregex, newsoa, nsszone)
            # Import the domain into Cloud DNS. Any exception here will exit and log failure of this zone.
            dom = cdns.import_domain(zone)
            # Move the processed files out of the way, so they will be separated from failed zones, to ease troubleshooting.
            rename(bindpath + zonefile, procpath + zonefile)
            # Finally, log success for this zone.
            logging.info('Success:' + domain)
        except:
            # Log the specifics of any exceptions.
            logging.info('Error:' + domain + ":" + str(sys.exc_info()[1]))
