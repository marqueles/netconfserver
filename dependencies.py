import sys
import subprocess

res=""
for e in sys.argv[1:]:
    if res=="":
        res=e
    else:
        aux=""
        x = min(len(e),len(res))
        for i in range(0,x):
            if e[i]==res[i]:
                aux=aux+e[i]
            else:
                break
        res=aux
#print "Shared root: \""+res+"\""

auxlist={}
for e in sys.argv[1:]:
    a=e.replace(res,"")
    if "/" in a: auxlist[a]="folder"
    else: auxlist[a]="element"

#print auxlist.keys()
elems=""
for e in auxlist.keys():
    name=""
    if auxlist[e]=="folder": name=e.split("/")[0]
    else: name=e
    findCMD = 'find . -name "*'+name+'*"'
    out = subprocess.Popen(findCMD,shell=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (stdout, stderr) = out.communicate()
    filelist = stdout.decode().split()
    for i in filelist:
        if ".yang" in i and i[2:] not in elems: elems=elems+" "+i[2:]

print elems

