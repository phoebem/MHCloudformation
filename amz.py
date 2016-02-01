#!env python

import subprocess 
import json
import shlex, subprocess
import getopt, sys
from string import Template
import time
from datetime import datetime
import sys, os, re
import logging
from InstanceController import *

logFormatter = logging.Formatter('%(asctime)-15s - %(name)s - %(levelname)s - %(message)s')
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
logger = logging.getLogger(__name__)
logger.addHandler(consoleHandler)
logger.setLevel(logging.DEBUG)
aws_access_key_id = None
aws_secret_access_key = None

# Spin up a new stack using template in ./templates 
#def gen_cluster(stackname, zone="us-east-1a", subnet="subnet-33a05318", security_groups="sg-208b9145\\\,sg-df869aba",engage_security_group="sg-208b9145\\\,sg-df869aba", prefix="provision", dryrun=False):
def gen_cluster(stackname,cloudformation_template, dryrun=False):
    params=[]   #"--parameters"]
    """
    params.append('ParameterKey={0},ParameterValue={1}'.format( "prefix", prefix))  
    params.append('ParameterKey={0},ParameterValue={1}'.format( "securitygroups", security_groups))  
    params.append('ParameterKey={0},ParameterValue={1}'.format( "engagesecuritygroups", engage_security_groups))  
    params.append('ParameterKey={0},ParameterValue={1}'.format( "subnet", subnet))  
    params.append('ParameterKey={0},ParameterValue={1}'.format( "zone", zone))  
    args = "--parameters " + ' '.join(params)
    """
    cloudformation_template = "file://"+ cloudformation_template
    if dryrun:
        command= "aws cloudformation validate-template --region us-east-1 --template-body {0}".format( cloudformation_template )
    else:
        command= "aws cloudformation create-stack --stack-name {0} --region us-east-1 --capabilities CAPABILITY_IAM --template-body {1}".format( stackname , cloudformation_template)
    logger.debug( command)
    args = shlex.split(command)
    try:
        output = subprocess.check_output( args, stderr=subprocess.STDOUT)	# python 2.7
    except:
        p2 = subprocess.Popen(args, stderr=subprocess.PIPE, stdout=subprocess.PIPE)	# python 2.6
        output = p2.communicate()[0]
       
    logger.info(output)
    #j = json.loads(output)

# Find cloudfront name from domain name
def cloudfront( domainname):
    command= "aws cloudfront list-distributions --region us-east-1"
    logger.debug( command)
    args = shlex.split(command)
    try:
        output = subprocess.check_output( args, stderr=subprocess.STDOUT)
    except:
        p2 = subprocess.Popen(args, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        output = p2.communicate()[0]
    logger.info(output)
    dist = json.loads( output) 
    cf= None
    for i in dist["DistributionList"]["Items"]:
        orig = i["Origins"]["Items"][0]["DomainName"]
        cf = i["DomainName"]
        logger.debug("{0} {1}".format( orig, cf ))
        if domainname == orig:
            logger.debug("found {0} {1}".format( orig, cf ))
            output = cf
    return cf
            
# Generate resources listing
def list_cluster(stackname):
    varsp ={}
    varsx ={}
    command= "aws cloudformation describe-stack-resources  --region us-east-1 --stack-name="+stackname
    args = shlex.split(command)
    try:
       output = subprocess.check_output( args, stderr=subprocess.STDOUT)
    except:
       p2 = subprocess.Popen(args, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
       output = p2.communicate()[0]
    try:
	    cluster = json.loads( output) 
	    logger.info("Cluster {0} created with the following instances".format( stackname ) )
	    for inst in cluster["StackResources"]:  # each instance in cluster
		tag = inst["LogicalResourceId"]
		name = inst["PhysicalResourceId"]
		status = inst["ResourceStatus"]
		logger.info("Instance: {0} - {1}".format( tag, status ))
		command= "aws cloudformation describe-stack-resources --region us-east-1 --stack-name="+str(name)
		args = shlex.split(command)
		try:
		    output = subprocess.check_output( args, stderr=subprocess.STDOUT)
		except:
		    p2 = subprocess.Popen(args, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
		    output = p2.communicate()[0]
		cluster1 = json.loads( output) 
		for inst1 in cluster1["StackResources"]:
		    logger.info("\t{0}:{1}".format( inst1["ResourceType"], inst1["PhysicalResourceId"] ) )
    except:
         logger.info("Stack {0} does not exist".format( stackname ) )

# Generate internal and external inventory files
def gen_inv(stackname, inventory_template, outputfile, outputfilex=None):
    varsp ={}
    #varsx ={}
    command= "aws cloudformation describe-stacks --region us-east-1 --stack-name="+stackname
    args = shlex.split(command)
    try:
        output = subprocess.check_output( args, stderr=subprocess.STDOUT)
    except:
        p2 = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = p2.communicate()[0]
    try:
	j = json.loads(output)
    except:
        logger.info("Stack {0} does not exist".format( stackname ) )
	return
    workers=[]
    workersx=[]
    pub = re.compile("(\w+)PublicIp")
    priv = re.compile("(\w+)PrivateIp")

    while True:  #j["Stacks"][0]["StackStatus"] != "CREATE_COMPLETE": 
        if j["Stacks"][0]["StackStatus"].startswith("ROLLBACK"): 
            logger.error( "Failed "+ j["Stacks"][0]["StackStatus"])
            exit(1)
        if j["Stacks"][0]["StackStatus"].startswith("DELETE"): 
            logger.error( "Deleted "+ j["Stacks"][0]["StackStatus"])
            exit(1)

        if j["Stacks"][0]["StackStatus"] == "CREATE_COMPLETE": 
            logger.info( "Cluster Output:")
            for i in j["Stacks"][0]["Outputs"]:
                name = i["OutputKey"]
                ip = i["OutputValue"]
                privkey = priv.match(name)
                pubkey  = pub.match(name)
                if name.startswith("workerPrivate"):
                    workers.append( ip +' mh_node_role="worker" mh_worker_maxload=4')
                elif name.startswith("workerPublic"):
                    workersx.append( ip +' mh_node_role="worker" mh_worker_maxload=4')
                elif privkey:
                   #varsp[ privkey.group(1)+"_ip" ] = ip
                   #varsx[ "private_" + privkey.group(1)+"_ip" ] = ip
                   varsp[ "private_" + privkey.group(1)+"_ip" ] = ip
                   logger.debug( "private {0}: {1}".format(privkey.group(1),ip))
                elif pubkey:
                   #varsx[ pubkey.group(1)+"_ip" ] = ip
                   #varsx[ "public_" + pubkey.group(1)+"_ip" ] = ip
                   varsp[ "public_" + pubkey.group(1)+"_ip" ] = ip
                   logger.debug( "public {0}: {1}".format(pubkey.group(1),ip))
                elif name.startswith("engagePublicDNS"):
                   varsp["public_engage_dns"] = ip
                   #varsx["public_engage_dns"] = ip
                   #varsx["cloudfront"] = cloudfront( ip )
                   logger.debug("engageDNS {0}: {1}".format(name,ip))
                else:
                   logger.debug( "{0}: {1}".format(name,ip))

            worker = "\n".join(workers)
            varsp["workers"] = worker
            logger.debug("workers {0}".format(varsp["workers"]))
            #varsx["workers"] = worker
            #print "{0}: {1}".format(varsp["workers"],varsx["workers"])

            inventory = open( inventory_template).read()
            t = Template(inventory)
            # Internal ips
            with open( outputfile, "w") as f:
                f.write( t.substitute(varsp) )
            logger.info("Generated " + outputfile )
            # External ips
            """
            with open( outputfilex, "w") as f:
                f.write( t.substitute(varsx) )
            print "Generated " + outputfile + " and " + outputfilex
            """
            break
        else:
            #print "Stack Not ready, Status= "+ j["Stacks"][0]["StackStatus"]
            sys.stdout.write('.')
            try:
                output = subprocess.check_output( args, stderr=subprocess.STDOUT)
            except:
                p2 = subprocess.Popen(args, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
                output = p2.communicate()[0]
            j = json.loads(output)


"""
    Generate a mapping from host to allocation ID for cloudformation
"""
def generate_eip_map_by_tagged_instances(prefix,dryrun ):
    c = InstanceController( dryrun=dryrun, region='us-east-1', aws_access_key_id = aws_access_key_id, aws_secret_access_key =aws_secret_access_key)
    # Find all the instances
    n=1;
    s = c.get_tagged_instances( tag= prefix+"*" )
    addresses = c.get_all_addresses()
    clause=['"none":   { "ip": "",      "eip": "none" }']
    for i in s:
        for addr in addresses:
            if i.ip_address == addr.public_ip:
                try:
                    if i.tags["Role"] == "worker":
                        name = "worker{0}".format(n)
                        n=n+1
                    elif i.tags["Role"] == "mysql":
                        name = "db"
                    else:
                        name =  i.tags["Role"]
                    clause.append('\n"%s": { "ip":"%s", "eip":"%s" }' % ( name, addr.public_ip, addr.allocation_id))
                except:
                    name = i.tags["Name"]
                    clause.append('\n"%s": { "ip":"%s", "eip":"%s" }' % ( name, addr.public_ip, addr.allocation_id))
    print('"ElasticIp": {')
    print( ",".join(clause))
    print('} ')

"""
    Release elastic ips from this cluster by prefix
    Also retag this cluster with a prefix and then stop the cluster
"""
def disassociate_tagged_instances(prefix, dryrun):
    c = InstanceController( dryrun=dryrun, region='us-east-1',aws_access_key_id =  aws_access_key_id , aws_secret_access_key =aws_secret_access_key)
    # Find all the instances
    mm = re.compile("build")
    s = c.get_tagged_instances( tag= prefix+"*" )
    for i in s:
        if mm.search(i.tags["Name"]):
             logger.debug("ignore "+ i.tags["Name"])
             s.remove(i)
        else:
             logger.debug("Remove EIP from "+ i.tags["Name"])
    now = datetime.now()
    dt = datetime.strftime( now, "%b%d")
    logger.info("Retag old cluster with prefix "+ "Remove_"+dt+"_")
    if dryrun:
        for i in s:
            logger.debug("Dryrun: retag old cluster "+ "Remove_"+dt+"_"+i.tags["Name"])
    else:
        c.append_tag_instances( s, "Name", "Remove_"+dt+"_")
    logger.info("Remove eip association and stop instance")
    if not dryrun:
        c.remove_instance_by_tagging( s, "remove" )

"""
    Create a new cluster with cloudformation template
"""
def create_newcluster(stackname, template, dryrun):
    instmap={ # Reference only
        # engage needs sg-e9de098d
        "dev": { "zone": "us-east-1a",
                   "subnet":"subnet-33a05318",
                   "security_groups":"sg-208b9145\\\,sg-df869aba",
                   "engage_security_groups":"sg-e9de098d\\\,sg-208b9145\\\,sg-df869aba"
                   },
        # engage need an extra group: sg-877120e3
        "stg": { "zone": "us-east-1b",
                   "subnet":"subnet-ae1296d9",
                   "security_groups":"sg-9fd629fb",
                   "engage_security_groups":"sg-877120e3\\\,sg-9fd629fb"
                   },
        # engage needs sg-4eb6612a
        "prd": { "zone": "us-east-1c",
                   "subnet":"subnet-33a05318",
                   "security_groups":"sg-e6945a82",
                   "engage_security_groups":"sg-e6945a82\\\,sg-4eb6612a"
                   },
       }
    logger.info("Generate new cluster")
    gen_cluster(stackname, template, dryrun=dryrun)

def usage():
    print "{0} -s[tack] stackname -p[refix] instance name prefix -e[env] [dev|stg|prd] -g[enerate]  -h[elp] -d(ryrun)".format( sys.argv[0] )
    print "\tStack name is name of the new mh stack - default is today's date MonDD"
    print "\tprefix name is prefix of the tag:Name of the instances for replacement,  eg: prdAWS"
    print "\tenv is [dev(xxx)|stg|prd] - dev is dev01, dev02, devAWS, etc- uses matching template in template dir"
    print "\tgenerates a map of private and public ip and the inventory file"
    print "\tinventory name is [env].hosts "
    print "\t- default is <env><prefix name>.hosts for internal and <env><prefix name>_ext.hosts for external access"
    print "\tPlease terminate replaced nodes"

def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], "a:k:de:hp:s:g", ["dryrun","env","help","prefix","stackname"])
    except getopt.GetoptError as err:
        # print help information and exit:
        print str(err) # will print something like "option -a not recognized"
        usage()
        sys.exit(2)
    now = datetime.now()
    dt = datetime.strftime( now, "%b%d")
    dryrun= False
    env = None
    stackname = dt
    prefix = "provision"     # chane to prdAWS
    inventory = None
    gen = False
    verbose = False
    num_nodes = 0   # 0 means shutdown all nodes

    for o, a in opts:
        if o == "-v":
            verbose = True
        elif o in ("-d" ,"--dryrun"):
            dryrun = True
        elif o == "-a":
            aws_access_key_id = a
        elif o == "-k":
            aws_secret_access_key = a
        elif o == "-g":
            gen = True
        elif o in ("-e" ,"--env"):
            env = a
        elif o in ("-i", "--inventory"):
            inventory = a
        elif o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ("-p", "--prefix"):
            prefix = a
        elif o in ("-s", "--stack"):
            stackname = a
        else:
            assert False, "unhandled option"

    if not inventory:
        inventory = prefix

    if gen: # generate a map for elasticIP replacement
        generate_eip_map_by_tagged_instances(prefix,dryrun)
        sys.exit()

    else:
        cloudformation_template = os.path.abspath(os.path.dirname(sys.argv[0]))+"/templates/cf_"+env
        inventory_template = os.path.abspath(os.path.dirname(sys.argv[0]))+"/templates/"+env+"-inv.template"

        assert(os.path.isfile(cloudformation_template))
        assert(os.path.isfile(inventory_template))

        logger.info( "Remove old stack")

        disassociate_tagged_instances(prefix, dryrun)        
        if not dryrun:
            time.sleep(30)  # aws needs time to release the eips - 
        logger.info( "Bring up new  stack {0} with prefix {1} in {2} env, generating template files {3}.hosts\n".format(stackname, prefix, env, inventory))
        create_newcluster(stackname, cloudformation_template, dryrun)
        logger.info("Wait for cluster to finish creation and generate inventory files - see https://console.aws.amazon.com/cloudformation/ for detailed events")
        

	# dryrun will generate files
        gen_inv(stackname, inventory_template, inventory+".hosts") #, inventory+"_ext.hosts")
        list_cluster(stackname)

if __name__ == "__main__":
   main()

