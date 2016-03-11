#!/usr/bin/python
#
# Copyright (C) 2014 IBM Corporation and Others. All Rights Reserved.
#
# @author Steven R. Loomis <srl@icu-project.org>
#
# This tool slims down an ICU data (.dat) file according to a config file.
#
# See: http://bugs.icu-project.org/trac/ticket/10922
#
# Usage:
#  Use "-h" to get help options.

import sys
import shutil
# for utf-8
reload(sys)
sys.setdefaultencoding("utf-8")

import optparse
import os
import json
import re

endian=sys.byteorder

parser = optparse.OptionParser(usage="usage: mkdir tmp ; %prog -D ~/Downloads/icudt53l.dat -T tmp -F trim_en.json -O icudt53l.dat" )

parser.add_option("-P","--tool-path",
                    action="store",
                    dest="toolpath",
                    help="set the prefix directory for ICU tools")

parser.add_option("-D","--input-file",
                    action="store",
                    dest="datfile",
                    help="input data file (icudt__.dat)",
                    )  # required

parser.add_option("-F","--filter-file",
                    action="store",
                    dest="filterfile",
                    help="filter file (JSON format)",
                    )  # required

parser.add_option("-T","--tmp-dir",
                    action="store",
                    dest="tmpdir",
                    help="working directory.",
                    )  # required

parser.add_option("--delete-tmp",
                    action="count",
                    dest="deltmpdir",
                    help="delete working directory.",
                    default=0)

parser.add_option("-O","--outfile",
                    action="store",
                    dest="outfile",
                    help="outfile  (NOT a full path)",
                    )  # required

parser.add_option("-v","--verbose",
                    action="count",
                    default=0)

parser.add_option('-L',"--locales",
                  action="store",
                  dest="locales",
                  help="sets the 'locales.only' variable",
                  default=None)

parser.add_option('-e', '--endian', action='store', dest='endian', help='endian, big, little or host, your default is "{0!s}".'.format(endian), default=endian, metavar='endianness')

(options, args) = parser.parse_args()

optVars = vars(options)

for opt in [ "datfile", "filterfile", "tmpdir", "outfile" ]:
    if optVars[opt] is None:
        print "Missing required option: {0!s}".format(opt)
        sys.exit(1)

if options.verbose>0:
    print "Options: "+str(options)

if (os.path.isdir(options.tmpdir) and options.deltmpdir):
  if options.verbose>1:
    print "Deleting tmp dir {0!s}..".format((options.tmpdir))
  shutil.rmtree(options.tmpdir)

if not (os.path.isdir(options.tmpdir)):
    os.mkdir(options.tmpdir)
else:
    print "Please delete tmpdir {0!s} before beginning.".format(options.tmpdir)
    sys.exit(1)

if options.endian not in ("big","little","host"):
    print "Unknown endianness: {0!s}".format(options.endian)
    sys.exit(1)

if options.endian is "host":
    options.endian = endian

if not os.path.isdir(options.tmpdir):
    print "Error, tmpdir not a directory: {0!s}".format((options.tmpdir))
    sys.exit(1)

if not os.path.isfile(options.filterfile):
    print "Filterfile doesn't exist: {0!s}".format((options.filterfile))
    sys.exit(1)

if not os.path.isfile(options.datfile):
    print "Datfile doesn't exist: {0!s}".format((options.datfile))
    sys.exit(1)

if not options.datfile.endswith(".dat"):
    print "Datfile doesn't end with .dat: {0!s}".format((options.datfile))
    sys.exit(1)

outfile = os.path.join(options.tmpdir, options.outfile)

if os.path.isfile(outfile):
    print "Error, output file does exist: {0!s}".format((outfile))
    sys.exit(1)

if not options.outfile.endswith(".dat"):
    print "Outfile doesn't end with .dat: {0!s}".format((options.outfile))
    sys.exit(1)

dataname=options.outfile[0:-4]


## TODO: need to improve this. Quotes, etc.
def runcmd(tool, cmd, doContinue=False):
    if(options.toolpath):
        cmd = os.path.join(options.toolpath, tool) + " " + cmd
    else:
        cmd = tool + " " + cmd

    if(options.verbose>4):
        print "# " + cmd

    rc = os.system(cmd)
    if rc is not 0 and not doContinue:
        print "FAILED: {0!s}".format(cmd)
        sys.exit(1)
    return rc

## STEP 0 - read in json config
fi= open(options.filterfile, "rb")
config=json.load(fi)
fi.close()

if (options.locales):
  if not config.has_key("variables"):
    config["variables"] = {}
  if not config["variables"].has_key("locales"):
    config["variables"]["locales"] = {}
  config["variables"]["locales"]["only"] = options.locales.split(',')

if (options.verbose > 6):
    print config

if(config.has_key("comment")):
    print "{0!s}: {1!s}".format(options.filterfile, config["comment"])

## STEP 1 - copy the data file, swapping endianness
## The first letter of endian_letter will be 'b' or 'l' for big or little
endian_letter = options.endian[0]

runcmd("icupkg", "-t%s %s %s""" % (endian_letter, options.datfile, outfile))

## STEP 2 - get listing
listfile = os.path.join(options.tmpdir,"icudata.lst")
runcmd("icupkg", "-l %s > %s""" % (outfile, listfile))

fi = open(listfile, 'rb')
items = fi.readlines()
items = [items[i].strip() for i in range(len(items))]
fi.close()

itemset = set(items)

if (options.verbose>1):
    print "input file: {0:d} items".format((len(items)))

# list of all trees
trees = {}
RES_INDX = "res_index.res"
remove = None
# remove - always remove these
if config.has_key("remove"):
    remove = set(config["remove"])
else:
    remove = set()

# keep - always keep these
if config.has_key("keep"):
    keep = set(config["keep"])
else:
    keep = set()

def queueForRemoval(tree):
    global remove
    if not config.has_key("trees"):
        # no config
        return
    if not config["trees"].has_key(tree):
        return
    mytree = trees[tree]
    if(options.verbose>0):
        print "* {0!s}: {1:d} items".format(tree, len(mytree["locs"]))
    # do varible substitution for this tree here
    if type(config["trees"][tree]) == str or type(config["trees"][tree]) == unicode:
        treeStr = config["trees"][tree]
        if(options.verbose>5):
            print " Substituting ${0!s} for tree {1!s}".format(treeStr, tree)
        if(not config.has_key("variables") or not config["variables"].has_key(treeStr)):
            print " ERROR: no variable:  variables.{0!s} for tree {1!s}".format(treeStr, tree)
            sys.exit(1)
        config["trees"][tree] = config["variables"][treeStr]
    myconfig = config["trees"][tree]
    if(options.verbose>4):
        print " Config: {0!s}".format((myconfig))
    # Process this tree
    if(len(myconfig)==0 or len(mytree["locs"])==0):
        if(options.verbose>2):
            print " No processing for {0!s} - skipping".format((tree))
    else:
        only = None
        if myconfig.has_key("only"):
            only = set(myconfig["only"])
            if (len(only)==0) and (mytree["treeprefix"] != ""):
                thePool = "{0!s}pool.res".format((mytree["treeprefix"]))
                if (thePool in itemset):
                    if(options.verbose>0):
                        print "Removing {0!s} because tree {1!s} is empty.".format(thePool, tree)
                    remove.add(thePool)
        else:
            print "tree %s - no ONLY"
        for l in range(len(mytree["locs"])):
            loc = mytree["locs"][l]
            if (only is not None) and not loc in only:
                # REMOVE loc
                toRemove = "{0!s}{1!s}{2!s}".format(mytree["treeprefix"], loc, mytree["extension"])
                if(options.verbose>6):
                    print "Queueing for removal: {0!s}".format(toRemove)
                remove.add(toRemove)

def addTreeByType(tree, mytree):
    if(options.verbose>1):
        print "(considering {0!s}): {1!s}".format(tree, mytree)
    trees[tree] = mytree
    mytree["locs"]=[]
    for i in range(len(items)):
        item = items[i]
        if item.startswith(mytree["treeprefix"]) and item.endswith(mytree["extension"]):
            mytree["locs"].append(item[len(mytree["treeprefix"]):-4])
    # now, process
    queueForRemoval(tree)

addTreeByType("converters",{"treeprefix":"", "extension":".cnv"})
addTreeByType("stringprep",{"treeprefix":"", "extension":".spp"})
addTreeByType("translit",{"treeprefix":"translit/", "extension":".res"})
addTreeByType("brkfiles",{"treeprefix":"brkitr/", "extension":".brk"})
addTreeByType("brkdict",{"treeprefix":"brkitr/", "extension":"dict"})
addTreeByType("confusables",{"treeprefix":"", "extension":".cfu"})

for i in range(len(items)):
    item = items[i]
    if item.endswith(RES_INDX):
        treeprefix = item[0:item.rindex(RES_INDX)]
        tree = None
        if treeprefix == "":
            tree = "ROOT"
        else:
            tree = treeprefix[0:-1]
        if(options.verbose>6):
            print "procesing {0!s}".format((tree))
        trees[tree] = { "extension": ".res", "treeprefix": treeprefix, "hasIndex": True }
        # read in the resource list for the tree
        treelistfile = os.path.join(options.tmpdir,"{0!s}.lst".format(tree))
        runcmd("iculslocs", "-i {0!s} -N {1!s} -T {2!s} -l > {3!s}".format(outfile, dataname, tree, treelistfile))
        fi = open(treelistfile, 'rb')
        treeitems = fi.readlines()
        trees[tree]["locs"] = [treeitems[i].strip() for i in range(len(treeitems))]
        fi.close()
        if(not config.has_key("trees") or not config["trees"].has_key(tree)):
            print " Warning: filter file {0!s} does not mention trees.{1!s} - will be kept as-is".format(options.filterfile, tree)
        else:
            queueForRemoval(tree)

def removeList(count=0):
    # don't allow "keep" items to creep in here.
    global remove
    remove = remove - keep
    if(count > 10):
        print "Giving up - {0:d}th attempt at removal.".format(count)
        sys.exit(1)
    if(options.verbose>1):
        print "{0:d} items to remove - try #{1:d}".format(len(remove), count)
    if(len(remove)>0):
        oldcount = len(remove)
        hackerrfile=os.path.join(options.tmpdir, "REMOVE.err")
        removefile = os.path.join(options.tmpdir, "REMOVE.lst")
        fi = open(removefile, 'wb')
        for i in remove:
            print >>fi, i
        fi.close()
        rc = runcmd("icupkg","-r {0!s} {1!s} 2> {2!s}".format(removefile, outfile, hackerrfile),True)
        if rc is not 0:
            if(options.verbose>5):
                print "## Damage control, trying to parse stderr from icupkg.."
            fi = open(hackerrfile, 'rb')
            erritems = fi.readlines()
            fi.close()
            #Item zone/zh_Hant_TW.res depends on missing item zone/zh_Hant.res
            pat = re.compile("""^Item ([^ ]+) depends on missing item ([^ ]+).*""")
            for i in range(len(erritems)):
                line = erritems[i].strip()
                m = pat.match(line)
                if m:
                    toDelete = m.group(1)
                    if(options.verbose > 5):
                        print "<< {0!s} added to delete".format(toDelete)
                    remove.add(toDelete)
                else:
                    print "ERROR: could not match errline: {0!s}".format(line)
                    sys.exit(1)
            if(options.verbose > 5):
                print " now {0:d} items to remove".format(len(remove))
            if(oldcount == len(remove)):
                print " ERROR: could not add any mor eitems to remove. Fail."
                sys.exit(1)
            removeList(count+1)

# fire it up
removeList(1)

# now, fixup res_index, one at a time
for tree in trees:
    # skip trees that don't have res_index
    if not trees[tree].has_key("hasIndex"):
        continue
    treebunddir = options.tmpdir
    if(trees[tree]["treeprefix"]):
        treebunddir = os.path.join(treebunddir, trees[tree]["treeprefix"])
    if not (os.path.isdir(treebunddir)):
        os.mkdir(treebunddir)
    treebundres = os.path.join(treebunddir,RES_INDX)
    treebundtxt = "{0!s}.txt".format((treebundres[0:-4]))
    runcmd("iculslocs", "-i {0!s} -N {1!s} -T {2!s} -b {3!s}".format(outfile, dataname, tree, treebundtxt))
    runcmd("genrb","-d {0!s} -s {1!s} res_index.txt".format(treebunddir, treebunddir))
    runcmd("icupkg","-s {0!s} -a {1!s}{2!s} {3!s}".format(options.tmpdir, trees[tree]["treeprefix"], RES_INDX, outfile))
